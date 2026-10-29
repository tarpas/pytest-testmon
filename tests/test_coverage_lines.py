"""Which source lines coverage.py reports as executed for small sample modules, and the
fingerprint testmon derives from them. These are assumptions about coverage.py that the
method-checksum algorithm relies on, not tests of testmon's own logic.

Until 2026 this file was test_human_coverage.py: in 2018 testmon switched to the line set
coverage.py shows in its reports ("coverage for humans": blank lines, else:/finally: lines,
continuation lines) and ported coverage.py's own statement tests to check per-line fingerprints.
That line algorithm was replaced by the AST/method-checksum one in 2021 and those tests were
deactivated by renaming their classes, then deleted; the two assumption tests here are what remains.
"""

from tests.coveragepy.coveragetest import CoverageTest
from tests.test_testmon import CodeSample
from testmon.process_code import (
    Module,
    create_fingerprint,
)
import textwrap
from coverage import coverage
import sys
from os.path import abspath


class TestmonCoverageTest(CoverageTest):
    def write_and_run(self, text):
        modname = self.get_module_name()
        filename = self.make_file(modname + ".py", text)
        # Start up coverage.py.
        cov = coverage()
        cov.erase()
        self.start_import_stop(cov, modname)
        # Clean up our side effects
        del sys.modules[modname]
        coverage_lines = cov.get_data().lines(abspath(modname + ".py"))
        return coverage_lines, filename

    def check_construct_fingerprints(self, text, liness=None, fingerprints=None):
        text = textwrap.dedent(text)

        coverage_lines, _ = self.write_and_run(text)

        m = Module(source_code=text)

        passed = False
        for lines in liness:
            passed = (sorted(coverage_lines) == lines) or passed
        assert passed, "None of the provided liness matches actual coverage"
        if fingerprints:
            assert create_fingerprint(m, lines) == fingerprints


class TestCoverageAndFingeprintsAssumptions(TestmonCoverageTest):
    def test_pass_1st_position(self):
        # pass is "not covered" if there are statements afterwards
        self.check_construct_fingerprints(
            """\
            a = 1
            def b():
                pass
                1
            b()
            """,
            [[1, 2, 4, 5], [1, 2, 3, 4, 5]],
        )


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


class TestCoverageAssumptions(TestmonCoverageTest):
    def test_easy(self):
        for name, mod_cov in code_samples.items():
            if mod_cov.expected_coverage:
                coverage_lines, _ = self.write_and_run(mod_cov.source_code)
                assert sorted(coverage_lines) == mod_cov.expected_coverage, (
                    "This is for code_sample['{}']".format(name)
                )
