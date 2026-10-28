#  -- coding:utf8 --
from pathlib import Path
from subprocess import run

import pytest

from testmon.process_code import (
    Module,
    read_source_sha,
    match_fingerprint_source,
    create_fingerprint_source,
    get_source_sha,
    noncached_get_files_shas,
)
from testmon.testmon_core import SourceTree

try:
    from StringIO import StringIO as MemFile
except ImportError:
    from io import BytesIO as MemFile  # noqa: F401

pytest_plugins = ("pytester",)


def git(*args):
    """Run git in the current directory and fail loudly if it fails."""
    return run(["git", *args], check=True, capture_output=True)


def git_init():
    """A repo with an identity, so commits work on machines without a global git config."""
    git("init", "-b", "main")
    git("config", "user.name", "testmon tests")
    git("config", "user.email", "tests@testmon.org")


class TestCreateAndMatchFingerprintRoundtrip:
    def test_minimal_module(self):
        fingerprint = create_fingerprint_source(
            """\
            print("a") # <
            """,
            {1},  # covered line numbers, also marked in the source.
        )
        assert (
            # this is used for deselection (before execution)
            # if fingerprint doesn't match test must be re-executed
            # otherwise next source file is checked against it's
            # fingerprint
            match_fingerprint_source(
                """\
                                                print("changed")
                                                """,
                fingerprint,
            )
            is False
        )

    def test_nonexecuted(self):
        fingerprint = create_fingerprint_source(
            """\
            print("a") # !
            """,
            {},  # module not executed at all
        )
        assert match_fingerprint_source(
            """\
            print("anything_should_match")
            """,
            fingerprint,
        )

    def test_module_level_change(self):
        fingerprint = create_fingerprint_source(
            """\
            print("a")    # <
            def test_1(): # <
                print(1)  # <
            """,
            {1, 2, 3},  # covered line numbers, also marked in the source.
        )
        assert (
            match_fingerprint_source(
                """\
                                                    print("changed")
                                                    def test_1():
                                                        print(1)
                                                    """,
                fingerprint,
            )
            is False
        )

    def test_method_change_unexecuted1(self):
        fingerprint = create_fingerprint_source(
            """\
            def test_1(): # <
                print(1)  # !
            def test_2(): # <
                print(2)  # <
            """,
            {1, 3, 4},  # covered line numbers, also marked in the source.
        )
        assert match_fingerprint_source(
            """\
            def test_1():
                whatever
            def test_2():
                print(2)
            """,
            fingerprint,
        )

    def test_method_change_unexecuted2(self):
        fingerprint = create_fingerprint_source(
            """\
            def test_1(): # <
                print(1)  # <
            def test_2(): # <
                print(2)  # !
            """,
            {1, 2, 3},  # covered line numbers, also marked in the source
        )
        assert match_fingerprint_source(
            """\
            def test_1():
                print(1)
            def test_2():
                whatever
            """,
            fingerprint,
        )

    def test_method_name_executed(self):
        fingerprint = create_fingerprint_source(
            """\
            def test_1(): # <
                print(1)  # <
            def test_2(): # <
                print(2)  # !
            """,
            {1, 2, 3},  # covered line numbers, also marked in the source
        )
        assert (
            match_fingerprint_source(
                """\
                                                    def test_changed():
                                                        print(1)
                                                    def test_2():
                                                        print(2)
                                                    """,
                fingerprint,
            )
            is False
        )

    def test_method_body_executed(self):
        fingerprint = create_fingerprint_source(
            """\
            def test_1(): # <
                print(1)  # <
            def test_2(): # <
                print(2)  # !
            """,
            {1, 2, 3},  # covered line numbers, also marked in the source
        )
        assert (
            match_fingerprint_source(
                """\
                                                    def test_1():
                                                        print("changed")
                                                    def test_2():
                                                        print(2)
                                                    """,
                fingerprint,
            )
            is False
        )

    def test_module_level_change2(self):
        fingerprint = create_fingerprint_source(
            """\
            def test_1(): # <
                print(1)  # !
            def test_2(): # <
                print(2)  # !
            """,
            {1, 3},  # covered line numbers, also marked in the source
        )
        assert match_fingerprint_source(
            """\
                def test_1():
                    print("changed")
                def test_2():
                    print("changed")
                """,
            fingerprint,
        )

    def test_method_name_unexecuted(self):
        # TODO introduce a different level of "change" because
        # a change in definition of method which hasn't been executed
        # is much less relevant then other changes. match_fingerprint should
        # return a ratio of match not just True/False
        fingerprint = create_fingerprint_source(
            """\
            def test_1(): # <
                print(1)  # <
            def test_2(): # <
                print(2)  # !
            """,
            {1, 2, 3},
        )
        assert (
            match_fingerprint_source(
                """\
                                                            def test_1():
                                                                print(1)
                                                            def test_changed():
                                                                print(2)
                                                    """,
                fingerprint,
            )
            is False
        )

    def test_doctest_same(self):
        fingerprint = create_fingerprint_source(
            """\
                >>> 1
                1
            """,
            {1},
            ext="txt",
        )
        assert match_fingerprint_source(
            """\
                >>> 1
                1
            """,
            fingerprint,
            ext="txt",
        )

    def test_doctest_different(self):
        fingerprint = create_fingerprint_source(
            """\
                >>> 1
                1
            """,
            {1},
            ext="txt",
        )
        assert not match_fingerprint_source(
            """\
                >>> 2
                2
            """,
            fingerprint,
            ext="txt",
        )


SAMPLESDIR = Path(__file__).parent / "samples"


class TestReadSrc:
    def test_read_file_with_fsha(self, testdir):
        content = '# -*- coding: cp1250 -*-\n\nprint("š")\n'
        test_file = Path(testdir.tmpdir) / "print1250r.py"
        test_file.write_bytes(content.encode("cp1250"))

        source, _ = read_source_sha(test_file)
        assert "š" in source

    def test_read_file_with_fsha_1250(self, testdir):
        content = '# -*- coding: cp1250 -*-\n\nprint("š")\n'
        test_file = Path(testdir.tmpdir) / "print1250r.py"
        test_file.write_bytes(content.encode("cp1250"))

        _, fsha = read_source_sha(test_file)
        assert fsha == "e352deab2c4ee837f17e62ce1eadfeb898e76747"

    def test_read_empty_file_with_fsha(self):
        assert read_source_sha(SAMPLESDIR / "empty.py") == (
            "",
            "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        )

    def test_read_nonexistent_file_with_fsha(self):
        assert read_source_sha(SAMPLESDIR / "notexist.py") == (
            None,
            None,
        )

    def test_read_file_with_fsha_no_newline_eof(self):
        _, fsha = read_source_sha(SAMPLESDIR / "no_newline_eof.py")
        assert fsha == "2ec482d52166df7d06bbb35c9f609520b370e498"

    def test_read_file_with_CR_NL(self, testdir):
        # Create a file with CR+CR+NL line endings (as in the original sample file)
        content = "def fction():\r\r\n    return 0\r\r\n\r\r\n\r\r\n# eof\r\r\n"
        test_file = Path(testdir.tmpdir) / "slash_r_n_file.py"
        test_file.write_bytes(content.encode("utf-8"))

        _, fsha = read_source_sha(test_file)
        assert fsha == "fdc00c4cb4c9620aa04f768706aab7fc29f68883"

    @pytest.mark.parametrize("ext", [".py", ".p y"])
    def test_sha_git_file(self, testdir, ext):
        testdir.makefile(
            ext=ext,
            file="""
            pass

        """,
        )
        git_init()
        git("add", f"file{ext}")

        source, fsha = get_source_sha(testdir.tmpdir.strpath, f"file{ext}")
        assert fsha == "fc80254b619d488138a43632b617124a3d324702"
        assert source is None

    def test_sha_git_file_commit(self, testdir):
        testdir.makepyfile(
            filename="""
            pass

        """
        )
        git_init()
        git("add", "filename.py")
        git("commit", "-m", "Reasonable commit message")
        source, fsha = get_source_sha(testdir.tmpdir.strpath, "filename.py")
        assert fsha == "fc80254b619d488138a43632b617124a3d324702"
        assert source is None

    def test_sha_git_change(self, testdir):
        testdir.makepyfile(filename=" ")
        git_init()
        git("add", "filename.py")
        testdir.makepyfile(
            filename="""
            pass

        """
        )

        source, fsha = get_source_sha(testdir.tmpdir.strpath, "filename.py")
        assert fsha == "fc80254b619d488138a43632b617124a3d324702"
        assert source is not None

    def test_sha_non_git_file(self, testdir):
        # This file will not be recognized as git file because it's not in a git repo
        # sha will be calculated manually
        content = '# -*- coding: cp1250 -*-\n\nprint("š")\n'
        test_file = Path(testdir.tmpdir) / "print1250r.py"
        test_file.write_bytes(content.encode("cp1250"))

        source, fsha = get_source_sha(testdir.tmpdir.strpath, "print1250r.py")
        assert fsha == "e352deab2c4ee837f17e62ce1eadfeb898e76747"
        assert source is not None


class TestCodeToBlocks:
    def test_simple_function(self):
        m = Module(
            """\
                def add(a, b):
                    return a + b

                assert add(1, 2) == 3"""
        )
        assert sorted([(b.start, b.end) for b in m.blocks]) == [
            (1, 4),
            (2, 3),
        ]

    def test_two_functions(self):
        m = Module(
            """\
                def add(a, b):
                    return a + b

                def subtract(a, b):
                    return a - b

                assert add(1, 2) == 3
            """
        )
        assert sorted([(b.start, b.end) for b in m.blocks]) == [
            (1, 7),
            (2, 3),
            (5, 6),
        ]

    def test_class_with_one_method(self):
        m = Module(
            """\
            class A(object):
                def add(self, a, b):
                    return a + b
            """
        )
        assert sorted([(b.start, b.end) for b in m.blocks]) == [
            (1, 3),
            (3, 3),
        ]

    def test_class_with_one_method_modified(self):
        m = Module(
            """\
            class A(object):
                def add(self, a, b):
                    return a - b"""
        )
        assert sorted([(b.start, b.end) for b in m.blocks]) == [
            (1, 3),
            (3, 3),
        ]

    def test_class_with_two_methods(self):
        m = Module(
            """\
            class A(object):
                def add(self, a, b):
                    return a + b
                def subtract(self, a, b):
                    return a - b"""
        )
        assert sorted([(b.start, b.end) for b in m.blocks]) == [
            (1, 5),
            (3, 3),
            (5, 5),
        ]

    def test_class_with_two_methods_one_modified(self):
        m = Module(
            """\
                class A(object):
                    def add(self, a, b):
                        return a + b
                    def subtract(self, a, b):
                        return a - b - 1
                        """
        )
        assert sorted([(b.start, b.end) for b in m.blocks]) == [
            (1, 5),
            (3, 3),
            (5, 5),
        ]

    def test_class_with_renamed_method(self):
        m = Module(
            """\
                class A(object):
                    def add1(self, a, b):
                        return a + b
                    def subtract(self, a, b):
                        return a - b"""
        )
        assert sorted([(b.start, b.end) for b in m.blocks]) == [
            (1, 5),
            (3, 3),
            (5, 5),
        ]

    def test_match_case(self):
        m = Module(
            """
            def f(a):
                match a:
                    case 23:
                        def b():
                            print("23")
                    case 46:
                        def b():
                            print("46")
            """
        )
        assert sorted([(b.start, b.end) for b in m.blocks]) == [
            (2, 9),
            (3, 9),
            (6, 6),
            (9, 9),
        ]


class TestModule:
    def test_read_source(self, testdir):
        testdir.makepyfile(
            a="""
            pass

        """
        )
        git_init()
        git("add", "a.py")
        git("commit", "-m", "Reasonable commit message")
        module = SourceTree("").get_file("a.py")
        assert "pass" in module.source_code


def test_noncached_get_files_shas(testdir):
    git_init()
    testdir.makepyfile(test_file="def test(): pass")
    git("add", ".")
    git("commit", "-m", "Initial commit")

    assert isinstance(noncached_get_files_shas(testdir.tmpdir.strpath), dict)


class TestReadSrcNonAsciiFsha:
    """The computed file sha must equal git's blob hash for non-ASCII files too.

    get_source_sha prefers the real git hash of tracked files, and both hashes
    go into the same database column, so the fallback computation must agree
    with git for any content (see test_sha_git_file). For a multi-byte
    encoding (UTF-8) it only does when the blob header carries the byte
    length, not the decoded string length.
    """

    def test_read_nonascii_utf8_file_matches_git(self, testdir):
        content = 'x = "caf\u00e9"\n'
        test_file = Path(testdir.tmpdir) / "nonascii.py"
        test_file.write_bytes(content.encode("utf-8"))

        _, fsha = read_source_sha(test_file)
        git_sha = run(
            ["git", "hash-object", str(test_file)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert fsha == git_sha
