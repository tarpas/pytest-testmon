#  -- coding:utf8 --
from _pytest import unittest

from test.test_human_coverage import TestmonCoverageTest

import pytest

from testmon_dev.process_code import Block, Module, checksum_coverage, read_file_with_checksum, create_emental, \
    block_list_list, file_has_lines, DoesntHaveException, END_OF_FILE_MARK, match_fingerprints, \
    get_indent_spaces_count, GAP_MARK

try:
    from StringIO import StringIO as MemFile
except ImportError:
    from io import BytesIO as MemFile

from collections import namedtuple
from pytest import raises


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
        code_repr = Module(None, 'test/samples/print1250r.py').blocks[0].code
        assert "Str('\\xc5\\xa1')" in code_repr or "Str('š')" in Module(None, 'test/samples/print1250r.py').blocks[
            0].code


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


GLOBAL_BLOCK = Block(1, 8, 1000)


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


class TestEmentalTests():

    def test_create_emental(self):
        assert create_emental([b(2, 2), b(6, 8), b(1, 10)]) == set((1, 3, 4, 5, 9, 10))

    def test_block_list_list(self):
        afile = ['a', ' b', ' c', 'd', ' e', 'f', '  g', '  h', '    i', '  j']
        assert block_list_list(afile, {2, 3, 7, 8, 10}) == [['a', ' b', ' c'], ['f', '  g', '  h', GAP_MARK, '  j'], ]

    def test_block_list_list_simple(self):
        afile = ['a', '  b', ]
        assert block_list_list(afile, {2}) == [['a', '  b'], ]

    def test_block_list_list_no_method(self):
        afile = ['a', 'b', 'c']
        assert block_list_list(afile, {1, 2}) == [['a', 'b', ], ]

    def test_block_list_list_gap(self):
        afile = ['a', ' b', '  c', ' d']
        assert block_list_list(afile, {2, 4}) == [['a', ' b', GAP_MARK, ' d'], ]

    def test_block_block_not_cov_method(self):
        afile = ['a', 'b', 'm1', ' d', 'm2', '  f', '   g', '  h', 'm3', ' j']
        assert block_list_list(afile, {4, 6, 7, 8}) == [['m1', ' d'], ['m2', '  f', '   g', '  h']]

    def test_block_block_not_cov_method2(self):
        afile = ['a', 'b', 'm1', ' d', 'm2', '  f', '   g', '  h', 'm3', ' j']
        assert block_list_list(afile, {4, 10}) == [['m1', ' d'], ['m3', ' j']]

    def test_ignore_empty(self):
        afile = ['a', '\taa', '\n', 'b', ' c', '  d', '   e']
        assert block_list_list(afile, {2, 3, 5, 6, 7}) == [['a', '\taa'], ['b', ' c', '  d', '   e']]

    def test_ignore_empty2(self):
        afile = ['\n', '\n', 'a', '   b', '   c']
        assert block_list_list(afile, {1, 2, 4, 5}) == [['a', '   b', '   c', ]]

    def test_empty(self):
        assert block_list_list(["a", ], []) == []

    def test_empty_empty(self):
        assert block_list_list([], []) == []

    def test_1_3(self):
        assert block_list_list(['a', ' b', 'c'], [1, 3]) == [['a', GAP_MARK, 'c']]

    def test_1_34(self):
        print(block_list_list(['0', ' a', '  b', 'c', 'd'], [2, 4, 5]))
        assert block_list_list(['0', ' a', '  b', 'c', 'd'], [2, 4, 5]) == [['0', ' a', GAP_MARK], ['c', 'd']]

    def test_mutliline_no_indent(self):
        afile = ['c', ' m', '  1.1', '1.2', '1.3']
        multiline = {3: 3, 4: 3, 5: 3}
        assert block_list_list(afile, [3, 4, 5], multiline) == [[' m', '  1.1', '1.2', '1.3']]

    def test_block_end_with_more_indents(self):
        afile = ['m', ' 1', '  2', 't1', ' 1', 't2', ' 1']
        assert block_list_list(afile, [2, 3, 7]) == [['m', ' 1', '  2'], ['t2', ' 1']]

    def test_block_end_with_more_indents2(self):
        afile = ['m', ' 1', '  2', 't1', ' 1']
        assert block_list_list(afile, [2, 3, 5]) == [['m', ' 1', '  2'], ['t1', ' 1']]

    def test_class_and_global_method_with_more_indents(self):
        afile = ['gm', ' 1', '  2', 'c', ' cm', '  1']
        assert block_list_list(afile, [2, 3, 6]) == [['gm', ' 1', '  2'], [' cm', '  1']]

    def test_end_of_block_gap(self):
        afile = ['m1', ' 1', ' 2', '  g', 'm2', ' 1']
        assert [['m1', ' 1', ' 2', GAP_MARK]] == block_list_list(afile, [2, 3])

    def test_empty_line_after_gap(self):
        afile = ['m1', ' 1', '  g1', '  g2', '', ' 2']
        assert block_list_list(afile, [2, 5, 6]) == [['m1', ' 1', GAP_MARK, ' 2']]

    def test_two_empty_lines_after_gap(self):
        afile = ['m1', ' 1', '  g1', '  g2', '', '', ' 2']
        assert  [['m1', ' 1', GAP_MARK, ' 2']] == block_list_list(afile, [2, 5, 6, 7])

    def test_indentation_spaces_count(self):
        assert get_indent_spaces_count('    a  b  ') == 4
        assert get_indent_spaces_count('  \ta  b  ') == 8
        assert get_indent_spaces_count('\t  a  b  ') == 10
        assert get_indent_spaces_count('  \t  a  b  ') == 10
        assert get_indent_spaces_count('\ta  b  ') == 8
        assert get_indent_spaces_count('\t\ta  b  ') == 16


GAP_UNTIL_DEDENT = '-1GAP'
INDETED_GAP = '0GAP'


class TestTheRestAfter():

    def test_doesnthave1(self):
        with raises(DoesntHaveException):
            match_fingerprints([], [1])

    def test_doesnthave2(self):
        with raises(DoesntHaveException):
            match_fingerprints([1], [2])

    def test_identical(self):
        assert match_fingerprints(['1'], ['1']) == []

    def test_1line_dedent(self):
        assert match_fingerprints(['1', ' 2', '3'], ['1', INDETED_GAP, '3']) == []

    def test_2line_dedent(self):
        assert match_fingerprints(['1', ' 2', ' 2.5', '3'], ['1', INDETED_GAP, '3']) == []

    def test_gap_until_dedent(self):
        assert match_fingerprints(['1', ' 2', ' 3', '4'], ['1', ' 2', GAP_UNTIL_DEDENT, '4']) == []

    def test_eof_i(self):
        assert match_fingerprints(['1', '2', '3'], ['1', GAP_UNTIL_DEDENT]) == []

    def test_eof_d(self):
        assert match_fingerprints(['1', ' 2'], ['1', INDETED_GAP]) == []


class TestFileHasLines():
    def test_remove_empty_lines(self):
        required_fingerprints = [['m', ' 1', ' 2']]
        file_fingerprints = ['', 'm', '     ', ' 1', ' ', '', ' 2']

        assert file_has_lines(file_fingerprints, required_fingerprints) is True


class TestCoverageAssumptions(TestmonCoverageTest):

    def test_easy(self):
        for name, mod_cov in code_samples.items():
            if mod_cov.expected_coverage:
                coverage_lines, _ = self.write_and_run(mod_cov.source_code)
                assert sorted(coverage_lines) == mod_cov.expected_coverage, "This is for code_sample['{}']".format(name)
