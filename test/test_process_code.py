#  -- coding:utf8 --
from test.coveragepy.coveragetest import CoverageTest

import pytest

from test.test_testmon import CodeSample
from testmon.process_code import Block, Module, checksum_coverage, read_file_with_checksum, create_emental, \
    block_list_list, file_has_lines, DoesntHaveException, END_OF_FILE_MARK, the_rest_after

try:
    from StringIO import StringIO as MemFile
except ImportError:
    from io import BytesIO as MemFile

from collections import namedtuple
from pytest import raises


def parse(source_code, file_name='a.py'):
    return Module(source_code=source_code, filename=file_name).blocks


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


code_samples = {
    1: CodeSample("""\
        def add(a, b):
            return a + b
    
        assert add(1, 2) == 3
            """,
                  {1, 2, 4}),

    2: CodeSample("""\
        def add(a, b):
            return a + b
            
        def subtract(a, b):
            return a - b

        assert add(1, 2) == 3
            """,
                  {1, 2, 4, 7}),
    '3': CodeSample("""\
        class A(object):
            def add(self, a, b):
                return a + b
        """,
                    {1, 2}),
    '3b': CodeSample("""\
        class A(object):
            def add(self, a, b):
                return a - b
        """,
                     {1, 2}),
    'classes': CodeSample("""\
        class A(object):
            def add(self, a, b):
                return a + b
            def subtract(self, a, b):
                return a - b
        """,
                          {1, 2, 4}),

    'classes_b': CodeSample("""\
        class A(object):
            def add(self, a, b):
                return a + b
            def subtract(self, a, b):
                return a - b - 1
        """,
                            {1, 2, 4}),
    'classes_c': CodeSample("""\
        class A(object):
            def add1(self, a, b):
                return a + b
            def subtract(self, a, b):
                return a - b
        """,
                            {1, 2, 4}),
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
        afile = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j']
        assert block_list_list(afile, {1, 3, 4, 5, 9, 10}) == [['a', 'b'], ['b', 'c', 'd', 'e', 'f'], ['h', 'i', 'j', END_OF_FILE_MARK]]

    def test_block_list_list_simple(self):
        afile = ['a', 'b', ]
        assert block_list_list(afile, {2}) == [['a', 'b', END_OF_FILE_MARK], ]

    def test_block_1_block(self):
        afile = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j']
        assert block_list_list(afile, {1, 2, 4, 6, 7}) == [['a', 'b', 'c'], ['c', 'd', 'e'], ['e', 'f', 'g', 'h']]

    def test_ignore_empty(self):
        afile = ['a', '\n', 'b', 'c', 'd', 'e']
        assert block_list_list(afile, {1, 3, 5, 6}) == [['a', 'b', 'c'], ['c', 'd', 'e', END_OF_FILE_MARK]]

    def test_empty(self):
        assert block_list_list(["a", ], []) == []

    def test_empty_empty(self):
        assert block_list_list([], []) == []

    def test_1_3(self):
        assert block_list_list(['a', 'b', 'c'], [1, 3]) == [['a', 'b'], ['b', 'c', END_OF_FILE_MARK]]

    def test_1_34(self):
        assert block_list_list(['a', 'b', 'c', 'd'], [1, 3, 4]) == [['a', 'b'], ['b', 'c', 'd', END_OF_FILE_MARK]]
        pass


class TestFileHasLines():

    def test_rest1(self):
        with raises(DoesntHaveException):
            the_rest_after([], [1])

    def test_rest2(self):
        with raises(DoesntHaveException):
            the_rest_after([1], [2])

    def test_rest3(self):
        assert the_rest_after([1], [1]) == [1]

    def test_rest4(self):
        assert the_rest_after([1, 2, 3], [2]) == [2, 3]

    def test_matches(self):
        required_fingerprints = [['2'], ['1', '0']]
        file_fingerprints = ['2', 'a', 'b', '1', '0']

        assert file_has_lines(file_fingerprints, required_fingerprints)

    def test_one_couple(self):
        required_fingerprints = [['1', '0']]
        file_fingerprints = ['2', 'a', 'b', '1', '0']
        assert file_has_lines(file_fingerprints, required_fingerprints)

    def test_two_singles(self):
        required_fingerprints = [['1'], ['3']]
        file_fingerprints = ['0', '1', '2', '3', '4']

        assert file_has_lines(file_fingerprints, required_fingerprints)

    def test_one_doesnt(self):
        fingerprints = [['2'], ['1', '7']]
        filep = ['0', '1', '2', '3', '4']

        assert file_has_lines(filep, fingerprints) is False


class TestCoverageAssumptions(CoverageTest):

    def test_easy(self):
        mod_cov = code_samples[2]
        self.tm_check_coverage(mod_cov.source_code,
                               tm_lines=mod_cov.expected_coverage,
                               msg="This is for code_sample['{}']".format(2))
