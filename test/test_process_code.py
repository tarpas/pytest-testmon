#  -- coding:utf8 --
from _pytest import unittest

from test.test_human_coverage import TestmonCoverageTest

import pytest

from testmon_dev.process_code import Module, read_file_with_checksum, \
    block_list_list, file_has_lines, \
    get_indent_level, GAP_UNTIL_INDENT

try:
    from StringIO import StringIO as MemFile
except ImportError:
    from io import BytesIO as MemFile

from collections import namedtuple


def parse(source_code, file_name='a.py'):
    return Module(source_code=source_code, file_name=file_name).blocks


class TestReadSrc:

    def test_read_file_with_checksum(self):
        assert u'š' in read_file_with_checksum('test/samples/print1250r.py')[0]

    def test_read_empty_file_with_checksum(self):
        assert read_file_with_checksum('test/samples/empty.py')[0] == ''

    def test_read_2lines_file_with_checksum(self):
        assert read_file_with_checksum('test/samples/2lines.py')[0] == '# -*- coding: cp1250 -*-\n#2ndline\n'

    def test_module_with_1250(self):
        Module(None, 'test/samples/print1250r.py')

@pytest.mark.xfail
class TestSourceIntoBlocks(object):

    def test_empty(self):
        assert parse(source_code="") == []

    def test_syntax_error(self):
        parse(source_code="(")

    def test_simple(self):
        blocks = parse("""print('high')\nprint('low')""")
        assert len(blocks) == 1
        assert blocks[0].start == 1
        assert blocks[0].end == 2

    def test_2_blocks(self):
        blocks = parse(
            """
                print('left')
                def a():
                    print('right') """
        )
        assert len(blocks) == 2
        assert blocks[0].start == 4
        assert blocks[0].end == 4
        assert blocks[1].start == 2
        assert blocks[1].end == 4

    def test_change_one(self):
        orig = parse("""
                    print('left')

                    def a():
                        print('right')  """)

        changed = parse("""
                    print('left')

                    def a():
                        print('left')   """)

        assert (orig[0].start,
                orig[0].end,
                orig[0].checksum) != (changed[0].start,
                                      changed[0].end,
                                      changed[0].checksum)
        assert (orig[1].start,
                orig[1].end,
                orig[1].checksum) == (changed[1].start,
                                      changed[1].end,
                                      changed[1].checksum)

    def test_same_even_names_but_different_blocks(self):
        blocks = parse("""
                    print('left')

                    def a():
                        print(1)

                    def a():
                        print(1)    """)
        assert len(set([block.checksum for block in blocks])) == len(blocks)

    def test_same_but_different_blocks(self):
        blocks = parse("""
                    print('left')

                    def a():
                        print(1)

                    def b():
                        print(1)    """)
        assert len(set([block.checksum for block in blocks])) == len(blocks)


@pytest.mark.xfail
class TestchecksumCoverage(object):
    def test_miss_before(self):
        assert checksum_coverage([Block(2, 3, 101), GLOBAL_BLOCK, ], [1]) == ['1000', ]

    def test_hit_first(self):
        assert checksum_coverage([Block(2, 3, 102), GLOBAL_BLOCK], [2]) == ['1000', '102']

    def test_hit_first2(self):
        assert checksum_coverage([Block(2, 3, 102), Block(6, 7, 103), GLOBAL_BLOCK], [2]) == ['1000', '102']

    def test_hit_first3(self):
        assert checksum_coverage([Block(2, 3, 102), Block(6, 7, 103), GLOBAL_BLOCK], [6]) == ['1000', '103']

    def test_miss_after(self):
        assert checksum_coverage([GLOBAL_BLOCK, Block(1, 2, 103)], [3]) == ['1000', ]

    def test_hit_second(self):
        assert checksum_coverage([GLOBAL_BLOCK, Block(2, 3, 101), Block(5, 6, 102)], [5]) == ['1000', '102']

    def test_hit_second_twice(self):
        assert checksum_coverage([GLOBAL_BLOCK, Block(2, 3, 101), Block(4, 7, 102)], [5, 6]) == ['1000', '102']

    @pytest.mark.parametrize("lines", [[3, 5], [5, 3]])
    def test_hit_both(self, lines):
        assert checksum_coverage([GLOBAL_BLOCK, Block(2, 3, 101), Block(5, 6, 102)], lines) == ['1000', '101', '102']

    @pytest.mark.parametrize("lines", [[4, 7], [7, 4]])
    def test_miss_both(self, lines):
        assert checksum_coverage([GLOBAL_BLOCK, Block(2, 3, 101), Block(5, 6, 102)], lines) == ['1000', ]


class CodeSample():
    def __init__(self, source_code, expected_coverage=None, possible_lines=None):
        self.source_code = source_code
        self.expected_coverage = expected_coverage or {}
        self.possible_lines = possible_lines or []


code_samples = {
    1: CodeSample("""\
        def add(a, b):
            return a + b
    
        assert add(1, 2) == 3
            """,
                  [1, 2, 4]),

    2: CodeSample("""\
        def add(a, b):
            return a + b
            
        def subtract(a, b):
            return a - b

        assert add(1, 2) == 3
            """,
                  [1, 2, 4, 7]),
    '3': CodeSample("""\
        class A(object):
            def add(self, a, b):
                return a + b
        """,
                    [1, 2]),
    '3b': CodeSample("""\
        class A(object):
            def add(self, a, b):
                return a - b
        """,
                     [1, 2]),
    'classes': CodeSample("""\
        class A(object):
            def add(self, a, b):
                return a + b
            def subtract(self, a, b):
                return a - b
        """,
                          [1, 2, 4]),

    'classes_b': CodeSample("""\
        class A(object):
            def add(self, a, b):
                return a + b
            def subtract(self, a, b):
                return a - b - 1
        """,
                            [1, 2, 4]),
    'classes_c': CodeSample("""\
        class A(object):
            def add1(self, a, b):
                return a + b
            def subtract(self, a, b):
                return a - b
        """,
                            [1, 2, 4]),
}

@pytest.mark.xfail
class TestModule(object):
    def test_base_diff(self):
        blocks1 = parse("""\
            a = 1


            def identity(ob):
                return ob


            @identity
            def method(st):
                return 1


            class Klass(object):
                pass


            for i in range(1):
                pass                """)

        blocks2 = parse("""\
            a = 1


            def identity(ob):
                return ob


            @identity
            def method(st):
                return 5


            class Klass(object):
                pass


            for i in range(1):
                pass                """)

        assert blocks1[0] == blocks2[0]
        assert blocks1[2] == blocks2[2]
        assert blocks1[1] != blocks2[1]

    def test_covdata_intersects_deps(self):
        def checksum(code_sample):
            module = Module(code_sample.source_code, 'a.py')
            covdata = code_sample.expected_coverage
            return checksum_coverage(module.blocks, covdata)

        assert checksum(code_samples[1])[1] == checksum(code_samples[2])[1]

    def test_3(self):
        module1 = Module(code_samples['3'].source_code)
        module2 = Module(code_samples['3b'].source_code)

        assert len(module1.blocks) == len(module2.blocks) == 2
        assert module1.blocks[0] != module2.blocks[0]
        assert module1.blocks[1] == module2.blocks[1]

    def test_classes(self):
        module1 = Module(code_samples['classes'].source_code)
        module2 = Module(code_samples['classes_b'].source_code)

        assert len(module1.blocks) == len(module2.blocks) == 3
        assert module1.blocks[0] == module2.blocks[0]
        assert module1.blocks[1] != module2.blocks[1]
        assert module1.blocks[2] == module2.blocks[2]

    def test_classes_header(self):
        module1 = Module(code_samples['classes'].source_code)
        module2 = Module(code_samples['classes_c'].source_code)

        assert len(module1.blocks) == len(module2.blocks) == 3
        b1 = module1.blocks[0]
        b2 = module2.blocks[0]
        assert (b1.start,
                b1.end,
                b1.checksum) == (b2.start,
                                 b2.end,
                                 b2.checksum)
        assert (b1.name) != (b2.name)
        assert module1.blocks[1] == module2.blocks[1]
        assert module1.blocks[2] != module2.blocks[2]


b = namedtuple('FakeBlock', 'start end')


class TestBlockList():

    def test_simple_everything(self):
        afile = ['def a():', ' b', ]
        assert block_list_list(afile, {1, 2}) == ['def a():', ' b']

    def test_gap_mark_eof(self):
        afile = ['def a():', ' b', ]
        assert block_list_list(afile, {1}) == ['def a():', GAP_UNTIL_INDENT, -1]

    def test_gap_mark(self):
        afile = ['def a():', ' b', 'c']
        assert block_list_list(afile, {1}) == ['def a():', GAP_UNTIL_INDENT, 0, 'c']

    def test_empty_lines(self):
        afile = ['def a():', ' b', '', 'c']
        assert block_list_list(afile, {1}) == ['def a():', GAP_UNTIL_INDENT, 0, 'c']

    @pytest.mark.xfail
    def test_empty_line_after_gap(self):
        afile = ['def a():', ' if False:', '  c=1', ' d=1']
        assert block_list_list(afile, {1, 2, 4}) == ['def a():', ' if False:', GAP_UNTIL_INDENT, 1, ' d=1']

    @pytest.mark.xfail
    def test_block_list_list_no_method(self):
        afile = ['a', 'b', 'c']
        assert block_list_list(afile, {1, 2}) == ['a', 'b', GAP_UNTIL_INDENT, -1]

    def test_indentation_spaces_count(self):
        assert get_indent_level('    a  b  ') == 4
        assert get_indent_level('  \ta  b  ') == 8
        assert get_indent_level('\t  a  b  ') == 10
        assert get_indent_level('  \t  a  b  ') == 10
        assert get_indent_level('\ta  b  ') == 8
        assert get_indent_level('\t\ta  b  ') == 16
        assert get_indent_level('') == 0


GAP_UNTIL_DEDENT = '-1GAP'
INDENTED_GAP = '0GAP'


class TestFileHasLines():
    def test_remove_empty_lines(self):
        required_fingerprints = ['m', ' 1', ' 2']
        file_fingerprints = ['', 'm', '     ', ' 1', ' ', '', ' 2']

        assert file_has_lines(file_fingerprints, required_fingerprints) is True

    def test_doesnthave1(self):
        assert file_has_lines([], [1]) is False

    def test_doesnthave2(self):
        assert file_has_lines(['1'], ['2']) is False

    def test_mismatch3(self):
        assert file_has_lines(['1', '2'], ['1']) is False

    def test_identical(self):
        assert file_has_lines(['1'], ['1'])

    def test_1line_dedent(self):
        assert file_has_lines(['def a():', ' 2', '3'], ['def a():', GAP_UNTIL_INDENT, 0, '3'])

    def test_2line_dedent(self):
        assert file_has_lines(['def a():', ' 2', ' 2.5', '3'], ['def a():', GAP_UNTIL_INDENT, 0, '3'])

    def test_double_dedent(self):
        assert file_has_lines(['def a():', '  def b():', '    1', '  2', ], ['def a():', GAP_UNTIL_INDENT, 0])

    def test_indent_eof(self):
        assert file_has_lines(['def a():', ' 2'], ['def a():', GAP_UNTIL_INDENT, -1])


class TestCoverageAssumptions(TestmonCoverageTest):

    def test_easy(self):
        for name, mod_cov in code_samples.items():
            if mod_cov.expected_coverage:
                coverage_lines, _ = self.write_and_run(mod_cov.source_code)
                assert sorted(coverage_lines) == mod_cov.expected_coverage, "This is for code_sample['{}']".format(name)
