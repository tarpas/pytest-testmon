#  -- coding:utf8 --
import ast

import pytest

from test.test_human_coverage import TestmonCoverageTest
from testmon_dev.process_code import Module, read_file_with_checksum, \
    file_has_lines, \
    get_indent_level, GAP_MARKS, create_fingerprints, function_lines

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


class TestNewModule(object):

    def test_create_nonempty_lines(self):
        1
        m = Module("""\
                    1

                    2
            """)
        assert m.full_lines == ['1', '2']


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


b = namedtuple('FakeBlock', 'start end')


def create_fingerprint_helper(afile, coverage):
    module = Module("\n".join(afile))
    return create_fingerprints(module.lines, module.special_blocks, coverage)


class TestSpecialBlocks():

    def test_decorator(self):
        m = Module("""\
                @abs
                def f1():
                    pass
        """)
        assert m.special_blocks == {3: 3}


class TestBlockList():

    def test_simple_everything(self):
        afile = ['def a():', ' b', ]
        assert create_fingerprint_helper(afile, {1, 2}) == ['def a():', ' b']

    def test_gap_mark_eof(self):
        afile = ['def a():', ' b', ]
        assert create_fingerprint_helper(afile, {1}) == ['def a():', GAP_MARKS[0]]

    def test_gap_mark(self):
        afile = ['def a():', ' b', 'c']
        assert create_fingerprint_helper(afile, {1, 3}) == ['def a():', GAP_MARKS[0], 'c']

    def test_empty_lines(self):
        afile = ['def a():', ' b', '', 'c']
        assert create_fingerprint_helper(afile, {1, 4}) == ['def a():', GAP_MARKS[0], 'c']

    @pytest.mark.xfail  # no ifs yet
    def test_empty_line_after_gap(self):
        afile = ['def a():', ' if False:', '  c=1', ' d=1']
        assert create_fingerprint_helper(afile, {1, 2, 4}) == ['def a():', ' if False:', GAP_MARKS[1], ' d=1']

    @pytest.mark.xfail  # no exceptions in block yet
    def test_block_list_list_no_method(self):
        afile = ['a', 'b', 'c']
        assert create_fingerprint_helper(afile, {1, 2}) == ['a', 'b', GAP_MARKS[-1]]

    def test_indentation_spaces_count(self):
        assert get_indent_level('    a  b  ') == 4
        assert get_indent_level('  \ta  b  ') == 8
        assert get_indent_level('\t  a  b  ') == 10
        assert get_indent_level('  \t  a  b  ') == 10
        assert get_indent_level('\ta  b  ') == 8
        assert get_indent_level('\t\ta  b  ') == 16
        assert get_indent_level('') == 0


class TestFileHasLines():

    def test_doesnthave1(self):
        assert file_has_lines([], [1]) is False

    def test_doesnthave2(self):
        assert file_has_lines(['1'], ['2']) is False

    def test_mismatch3(self):
        assert file_has_lines(['1', '2'], ['1']) is False

    def test_identical(self):
        assert file_has_lines(['1'], ['1'])

    def test_1line_dedent(self):
        assert file_has_lines(['def a():', ' 2', '3'], ['def a():', GAP_MARKS[0], '3'])

    def test_2line_dedent(self):
        assert file_has_lines(['def a():', ' 2', ' 2.5', '3'], ['def a():', GAP_MARKS[0], '3'])

    def test_double_dedent(self):
        assert file_has_lines(['def a():', '  def b():', '    1', '  2', ], ['def a():', GAP_MARKS[0]])

    def test_double_dedent_with_remainder(self):
        assert file_has_lines(['def a():', '  def b():', '    1', '  2', '3'], ['def a():', GAP_MARKS[0], '3'])

    def test_indent_eof1(self):
        assert file_has_lines(['def a():', ' 2'], ['def a():', GAP_MARKS[0]])

    def test_indent_eof2(self):
        assert file_has_lines(['raise Exception()', 'print(1)'], ['raise Exception()', GAP_MARKS[-1]])


class TestCoverageAssumptions(TestmonCoverageTest):

    def test_easy(self):
        for name, mod_cov in code_samples.items():
            if mod_cov.expected_coverage:
                coverage_lines, _ = self.write_and_run(mod_cov.source_code)
                assert sorted(coverage_lines) == mod_cov.expected_coverage, "This is for code_sample['{}']".format(name)
