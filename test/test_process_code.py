import pytest
import os

from testmon.process_code import (
    Module,
    read_file_with_checksum,
    file_has_lines,
    get_indent_level,
    GAP_MARKS,
    create_fingerprints,
    gap_marks_until,
    cover_subindented_multilines,
    encode_lines,
)

try:
    from StringIO import StringIO as MemFile
except ImportError:
    from io import BytesIO as MemFile

from collections import namedtuple


class TestReadSrc:
    def prepend_samples_dir(self, name):
        return os.path.join(os.path.dirname(__file__), "samples", name)

    def test_read_file_with_checksum(self):
        assert (
            u"š"
            in read_file_with_checksum(self.prepend_samples_dir("print1250r.py"))[0]
        )

    def test_read_empty_file_with_checksum(self):
        code, checksum = read_file_with_checksum(self.prepend_samples_dir("empty.py"))
        assert code == ""
        assert checksum == "da39a3ee5e6b4b0d3255bfef95601890afd80709"

    def test_read_nonexistent_file_with_checksum(self):
        assert read_file_with_checksum(self.prepend_samples_dir("notexist.py")) == (
            None,
            None,
        )

    def test_read_2lines_file_with_checksum(self):
        assert (
            read_file_with_checksum(self.prepend_samples_dir("2lines.py"))[0]
            == "# -*- coding: cp1250 -*-\n# 2ndline\n"
        )

    def test_module_with_1250(self):
        Module(None, self.prepend_samples_dir("print1250r.py"))


class TestNewModule(object):
    def test_create_nonempty_lines(self):
        1
        m = Module(
            """\
                    1

                    2
            """
        )
        assert m.full_lines == ["1", "2"]


class CodeSample:
    def __init__(self, source_code, expected_coverage=None, possible_lines=None):
        self.source_code = source_code
        self.expected_coverage = expected_coverage or {}
        self.possible_lines = possible_lines or []


code_samples = {
    1: CodeSample(
        """\
        def add(a, b):
            return a + b
    
        assert add(1, 2) == 3
            """,
        [1, 2, 4],
    ),
    2: CodeSample(
        """\
        def add(a, b):
            return a + b
            
        def subtract(a, b):
            return a - b

        assert add(1, 2) == 3
            """,
        [1, 2, 4, 7],
    ),
    "3": CodeSample(
        """\
        class A(object):
            def add(self, a, b):
                return a + b
        """,
        [1, 2],
    ),
    "3b": CodeSample(
        """\
        class A(object):
            def add(self, a, b):
                return a - b
        """,
        [1, 2],
    ),
    "classes": CodeSample(
        """\
        class A(object):
            def add(self, a, b):
                return a + b
            def subtract(self, a, b):
                return a - b
        """,
        [1, 2, 4],
    ),
    "classes_b": CodeSample(
        """\
        class A(object):
            def add(self, a, b):
                return a + b
            def subtract(self, a, b):
                return a - b - 1
        """,
        [1, 2, 4],
    ),
    "classes_c": CodeSample(
        """\
        class A(object):
            def add1(self, a, b):
                return a + b
            def subtract(self, a, b):
                return a - b
        """,
        [1, 2, 4],
    ),
}

b = namedtuple("FakeBlock", "start end")


def create_fingerprint_helper(afile, coverage):
    module = Module("\n".join(afile))
    return create_fingerprints(module.lines, module.special_blocks, coverage)


class TestSpecialBlocks:
    def test_decorator(self):
        m = Module(
            """\
                @abs
                def f1():
                    pass
        """
        )
        assert m.special_blocks == {3: 3}


class TestCoverSubindentedMutlilines:
    def test_simple(self):
        assert cover_subindented_multilines(["def", " 1", "2", " 3"], 1, 4, 0) == [
            "2",
            GAP_MARKS[0],
        ]

    def test_end_of_block(self):
        assert cover_subindented_multilines(["def", " 1", "2", "3"], 1, 4, 0) == [
            "2",
            "3",
            GAP_MARKS[0],
        ]

    def test_no_multiline(self):
        assert cover_subindented_multilines([" 1", " 2"], 0, 2, 0) == []


class TestGapMarksUntil:
    def test_simple(self):
        assert gap_marks_until(["  a"], 0, 1) == ([GAP_MARKS[1]], 1)

    def test_eof(self):
        assert (
            gap_marks_until(
                [
                    " a",
                ],
                1,
                2,
            )
            == ([GAP_MARKS[0]], 2)
        )

    def test_multiline(self):
        assert gap_marks_until([" 1", "2", " 3"], 0, 3) == (
            [GAP_MARKS[0], "2", GAP_MARKS[0]],
            3,
        )


class TestCreateFingerprints:
    def test_simple_everything(self):
        afile = [
            "def a():",
            " b",
        ]
        assert create_fingerprint_helper(afile, {2}) == ["def a():", " b"]

    def test_two_methods(self):
        afile = ["def a():", "  pass", "def b():", "  pass"]
        assert create_fingerprint_helper(afile, coverage={4}) == [
            "def a():",
            "1GAP",
            "def b():",
            "  pass",
        ]

    def test_gap_mark_eof(self):
        afile = [
            "def a():",
            " b",
        ]
        assert create_fingerprint_helper(afile, {1}) == ["def a():", GAP_MARKS[0]]

    def test_gap_mark(self):
        afile = ["def a():", " b", "c"]
        assert create_fingerprint_helper(afile, {1, 3}) == [
            "def a():",
            GAP_MARKS[0],
            "c",
        ]

    def test_empty_lines(self):
        afile = ["def a():", " b", "", "c"]
        assert create_fingerprint_helper(afile, {1, 4}) == [
            "def a():",
            GAP_MARKS[0],
            "c",
        ]

    def test_multiline_gap_no_indent(self):
        afile = ["def a():", " a=[", "1,", "2", " ]", "3"]
        fingerprints = ["def a():", GAP_MARKS[0], "1,", "2", GAP_MARKS[0], "3"]
        assert create_fingerprint_helper(afile, {1, 6}) == fingerprints

    def test_multiline_double_blank(self):
        afile = ["def a():", " a=[", "1", " ]", "", "", "3"]
        fingerprints = ["def a():", GAP_MARKS[0], "1", GAP_MARKS[0], "3"]
        assert create_fingerprint_helper(afile, {}) == fingerprints

    def test_decorator_in_class(self):
        afile = [
            "import pytest",
            "class TestA:",
            "  def a():",
            "    pass",
            "  @pytest.mark.xfail",
            "  def test_b():",
            "    pass",
        ]
        fingerprints = [
            "import pytest",
            "class TestA:",
            "  def a():",
            "3GAP",
            "  @pytest.mark.xfail",
            "  def test_b():",
            "3GAP",
        ]
        assert create_fingerprint_helper(afile, {}) == fingerprints

    @pytest.mark.xfail
    def test_empty_line_after_gap(self):
        afile = ["def a():", " if False:", "  c=1", " d=1"]
        assert create_fingerprint_helper(afile, {1, 2, 4}) == [
            "def a():",
            " if False:",
            GAP_MARKS[1],
            " d=1",
        ]

    @pytest.mark.xfail
    def test_block_list_list_no_method(self):
        afile = ["a", "b", "c"]
        assert create_fingerprint_helper(afile, {1, 2}) == ["a", "b", GAP_MARKS[-1]]

    def test_indentation_spaces_count(self):
        assert get_indent_level("    a  b  ") == 4
        assert get_indent_level("  \ta  b  ") == 8
        assert get_indent_level("\t  a  b  ") == 10
        assert get_indent_level("  \t  a  b  ") == 10
        assert get_indent_level("\ta  b  ") == 8
        assert get_indent_level("\t\ta  b  ") == 16
        assert get_indent_level("") == 0


class TestFileHasLines:
    def test_doesnthave1(self):
        lines = []
        assert file_has_lines(lines, [1]) is False

    def test_doesnthave2(self):
        lines = ["1"]
        assert file_has_lines(lines, ["2"]) is False

    def test_mismatch3(self):
        lines = ["1", "2"]
        assert file_has_lines(lines, ["1"]) is False

    def test_identical(self):
        lines = ["1"]
        fingerprints = ["1"]
        assert file_has_lines(lines, encode_lines(fingerprints))

    def test_1line_dedent(self):
        lines = ["def a():", " 2", "3"]
        fingerprints = ["def a():", GAP_MARKS[0], "3"]
        assert file_has_lines(lines, encode_lines(fingerprints))

    def test_2line_dedent(self):
        lines = ["def a():", " 2", " 2.5", "3"]
        fingerprints = ["def a():", GAP_MARKS[0], "3"]
        assert file_has_lines(lines, encode_lines(fingerprints))

    def test_double_dedent(self):
        lines = [
            "def a():",
            "  def b():",
            "    1",
            "  2",
        ]
        fingerprints = ["def a():", GAP_MARKS[0]]
        assert file_has_lines(lines, encode_lines(fingerprints))

    def test_double_dedent_with_remainder(self):
        lines = ["def a():", "  def b():", "    1", "  2", "3"]
        fingerprints = ["def a():", GAP_MARKS[0], "3"]
        assert file_has_lines(lines, encode_lines(fingerprints))

    def test_indent_eof1(self):
        lines = ["def a():", " 2"]
        fingerprints = ["def a():", GAP_MARKS[0]]
        assert file_has_lines(lines, encode_lines(fingerprints))

    def test_indent_eof2(self):
        lines = ["raise Exception()", "print(1)"]
        fingerprints = ["raise Exception()", GAP_MARKS[-1]]
        assert file_has_lines(lines, encode_lines(fingerprints))
