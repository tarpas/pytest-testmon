import os

import pkg_resources
import sys
import textwrap
import time
import pytest
import sqlite3

from testmon import db
from testmon.process_code import Module, encode_lines
from testmon.testmon_core import (
    eval_environment,
    DB_FILENAME,
    LIBRARIES_KEY,
    get_measured_relfiles,
    home_file,
)
from testmon.process_code import blob_to_checksums

from testmon.testmon_core import Testmon as CoreTestmon
from testmon.testmon_core import TestmonData as CoreTestmonData
from .test_process_code import CodeSample
from .coveragepy import coveragetest
from .test_core import CoreTestmonDataForTest

from threading import Thread, Condition

pytest_plugins = ("pytester",)

datafilename = os.environ.get("TESTMON_DATAFILE", DB_FILENAME)


def track_it(testdir, func):
    testmon = CoreTestmon(rootdir=testdir.tmpdir.strpath, testmon_labels=set())
    testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
    testmon.start()
    func()
    testmon.stop()
    measured_files = get_measured_relfiles(
        testmon_data.rootdir, testmon.cov, home_file("test_a.py::test_1")
    )
    nodedata = testmon_data.node_data_from_cov(measured_files)

    return nodedata


@pytest.fixture
def test_a(testdir):
    return testdir.makepyfile(
        test_a="""\
                def test_1():
                    print(1)
    """
    )


class TestPytestReportHeader:
    def test_nocollect(self, testdir, test_a):
        result = testdir.runpytest_inprocess("--testmon-nocollect")
        result.stdout.fnmatch_lines(
            [
                "*testmon: collection deactivated*",
            ]
        )

    def test_select(self, testdir, test_a):
        result = testdir.runpytest_inprocess("--testmon-noselect")
        result.stdout.fnmatch_lines(
            [
                "*testmon: selection deactivated*",
            ]
        )

    def test_no(self, testdir, test_a):
        result = testdir.runpytest_inprocess("--no-testmon")
        result.stdout.fnmatch_lines(
            [
                "*testmon: deactivated through --no-testmon*",
            ]
        )

    def test_deactivated_bc_coverage(self, testdir, test_a):

        result = testdir.run("coverage", "run", "-m", "pytest", "--testmon")
        result.stdout.fnmatch_lines(
            [
                "*testmon: collection automatically deactivated because it's not compatible with coverage.py*",
            ]
        )

    def test_active_newdb(self, testdir, test_a):
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*testmon: new DB, environment: default",
            ]
        )

    def test_active_deselect(self, testdir, test_a):
        testdir.runpytest_inprocess("--testmon")
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*testmon: changed files: 0, skipping collection of 1 files*",
            ]
        )

    def test_nocollect_deselect(self, testdir, test_a):
        testdir.runpytest_inprocess("--testmon")
        result = testdir.runpytest_inprocess("--testmon-nocollect")
        result.stdout.fnmatch_lines(
            [
                "*testmon: collection deactivated, changed files: 0, skipping collection of 1 files*",
            ]
        )


class TestVariant:
    def test_separation(self, testdir):
        td1 = CoreTestmonDataForTest("", environment="1")
        td1.write("test_a.py::test_1", {"test_a.py": encode_lines([])})

        td2 = CoreTestmonDataForTest("", environment="2")
        td2.write("test_a.py::test_2", {"test_a.py": encode_lines([])})

        td3 = CoreTestmonData("", environment="2")
        assert set(td3.all_nodes) == {"test_a.py::test_2"}

    def test_header(self, testdir):
        testdir.makeini(
            """
                        [pytest]
                        environment_expression='1'
                        """
        )
        result = testdir.runpytest_inprocess("-v", "--testmon")
        result.stdout.fnmatch_lines(
            [
                "*testmon: new DB, environment: 1*",
            ]
        )

    def test_header_nonstr(self, testdir):
        testdir.makeini(
            """
                        [pytest]
                        environment_expression=int(1)
                        """
        )
        result = testdir.runpytest_inprocess("-v", "--testmon")
        result.stdout.fnmatch_lines(
            [
                "*testmon: new DB, environment: 1*",
            ]
        )

    def test_empty(self, testdir):
        config = testdir.parseconfigure()
        assert eval_environment(config.getini("environment_expression")) == ""

    def test_environment_md5(self, testdir, monkeypatch):
        testdir.makeini(
            """
                        [pytest]
                        environment_expression=md5('TEST')
                        """
        )
        config = testdir.parseconfigure()
        assert (
            eval_environment(config.getini("environment_expression"))
            == "033bd94b1168d7e4f0d644c3c95e35bf"
        )

    def test_env(self, testdir, monkeypatch):
        monkeypatch.setenv("TEST_V", "JUST_A_TEST")
        testdir.makeini(
            """
                        [pytest]
                        environment_expression=os.environ.get('TEST_V')
                        """
        )
        config = testdir.parseconfigure()
        assert (
            eval_environment(config.getini("environment_expression")) == "JUST_A_TEST"
        )

    def test_nonsense(self, testdir):
        testdir.makeini(
            """
                        [pytest]
                        environment_expression=nonsense
                        """
        )
        config = testdir.parseconfigure()
        assert "NameError" in eval_environment(config.getini("environment_expression"))

    def test_complex(self, testdir, monkeypatch):
        monkeypatch.setenv("TEST_V", "JUST_A_TEST")
        testdir.makeini(
            """
                        [pytest]
                        environment_expression="_".join([x + ":" + os.environ[x] for x in os.environ if x == 'TEST_V'])
                        """
        )
        config = testdir.parseconfigure()
        assert (
            eval_environment(config.getini("environment_expression"))
            == "TEST_V:JUST_A_TEST"
        )


class TestmonDeselect(object):
    def test_dont_readcoveragerc(self, testdir):
        p = testdir.tmpdir.join(".coveragerc")
        p.write("[")
        testdir.makepyfile(
            test_a="""
            def test_add():
                pass
        """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )

    def test_simple_change(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_add():
                assert 1 + 2 == 3
                    """
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )

        test_a = testdir.makepyfile(
            test_a="""
            def test_add():
                assert 1 + 2 + 3 == 6
                    """
        )
        test_a.setmtime(1424880935)

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*passed*",
            ]
        )

    def test_simple_change_1_of_2(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_add():
                assert 1 + 2 == 3
            
            def test_2():
                assert True
                    """
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*2 passed*",
            ]
        )

        test_a = testdir.makepyfile(
            test_a="""
            def test_add():
                assert 1 + 2 + 3 == 6
                            
            def test_2():
                assert True

                    """
        )
        test_a.setmtime(1424880935)

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 passed, 1 deselected*",
            ]
        )

    def test_re_executing_failed(self, testdir):
        testdir.makepyfile(
            test_a="""
            import os
            
            def test_file(): # test that on first run fails, but on second one passes
                if os.path.exists('check'): # if file exists then pass the test
                    assert True
                else: # otherwise create the file and fail the test
                    open('check', 'a').close()
                    assert False
                    """
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 failed*",
            ]
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 deselected*",
            ]
        )

    def test_simple_change_1_of_2_with_decorator(self, testdir):
        testdir.makepyfile(
            test_a="""
            import pytest

            @pytest.mark.skipif('False')
            def test_add():
                assert 1 + 2 == 3

            def test_2():
                assert True
                    """
        )

        result = testdir.runpytest("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*2 passed*",
            ]
        )

        time.sleep(0.1)
        test_a = testdir.makepyfile(
            test_a="""
            import pytest

            @pytest.mark.skipif('False')
            def test_add():
                assert 1 + 2 + 3 == 6

            def test_2():
                assert True
                    """
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 passed, 1 deselected*",
            ]
        )

    def test_not_running_after_failure(self, testdir):
        tf = testdir.makepyfile(
            test_a="""
            def test_add():
                pass
        """,
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.assert_outcomes(1, 0, 0)

        sys.modules.pop("test_a", None)

        tf = testdir.makepyfile(
            test_a="""
            def test_add():
                1/0
        """,
        )
        tf.setmtime(1424880936)
        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.assert_outcomes(0, 0, 1)
        sys.modules.pop("test_a", None)

        tf = testdir.makepyfile(
            test_a="""
            def test_add():
                blas
        """,
        )
        tf.setmtime(1424880937)
        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.assert_outcomes(0, 0, 1)

        sys.modules.pop("test_a", None)

        tf = testdir.makepyfile(
            test_a="""
            def test_add():
                pass
        """,
        )
        tf.setmtime(1424880938)
        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.assert_outcomes(1, 0, 0)
        sys.modules.pop("test_a", None)

    def test_fantom_failure(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_add():
                1/0
        """,
        )
        testdir.runpytest_inprocess("--testmon", "-v")

        tf = testdir.makepyfile(
            test_a="""
            def test_add():
                pass
        """,
        )
        tf.setmtime(1)
        testdir.runpytest_inprocess("--testmon", "-v")

        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.assert_outcomes(0, 0, 0)

    def test_skipped(self, testdir):
        testdir.makepyfile(
            test_a="""
            import pytest
            @pytest.mark.skip
            def test_add():
                1/0
        """,
        )
        testdir.runpytest_inprocess("--testmon", "-v")
        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
        assert "test_a.py::test_add" in testmon_data.all_nodes

    def test_skipped_starting_line2(self, testdir):
        testdir.makepyfile(
            test_a="""
            #line not in AST
            import pytest
            @pytest.mark.skip
            def test_add():
                1/0
        """,
        )
        testdir.runpytest_inprocess("--testmon", "-v")
        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
        assert "test_a.py::test_add" in testmon_data.all_nodes

    def test_skipped_under_dir(self, testdir):
        subdir = testdir.mkdir("tests")

        tf = subdir.join("test_a.py")
        tf.write(
            textwrap.dedent(
                """
            import pytest
            @pytest.mark.skip
            def test_add():
                1/0
        """,
            )
        )
        tf.setmtime(1)
        testdir.runpytest_inprocess("--testmon", "-v", "tests")

        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)

        fname = os.path.sep.join(["tests", "test_a.py"])
        assert "tests/test_a.py::test_add" in testmon_data.all_nodes
        assert fname in testmon_data.all_files

    def test_wrong_result_processing(self, testdir):
        tf = testdir.makepyfile(
            test_a="""
            def test_add():
                1/0
        """,
        )
        testdir.runpytest_inprocess("--testmon", "-v")
        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
        assert testmon_data.all_nodes["test_a.py::test_add"]["failed"]
        assert testmon_data.all_nodes["test_a.py::test_add"]["durations"]["setup"]
        assert testmon_data.all_nodes["test_a.py::test_add"]["durations"]["call"]
        assert testmon_data.all_nodes["test_a.py::test_add"]["durations"]["teardown"]

        tf = testdir.makepyfile(
            test_a="""
            import pytest
            @pytest.mark.skip
            def test_add():
                1/0/0
        """,
        )
        tf.setmtime(1)
        testdir.runpytest_inprocess("--testmon", "-v")

        testmon_data.close_connection()
        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
        assert testmon_data.all_nodes["test_a.py::test_add"]["durations"]["setup"]
        assert testmon_data.all_nodes["test_a.py::test_add"]["durations"]["call"] == 0
        assert testmon_data.all_nodes["test_a.py::test_add"]["durations"]["teardown"]

        tf = testdir.makepyfile(
            test_a="""
            import pytest
            def test_add():
                1/0
        """,
        )
        tf.setmtime(2)
        testdir.runpytest_inprocess("--testmon", "-v")

        testmon_data.close_connection()
        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
        assert testmon_data.all_nodes["test_a.py::test_add"]["durations"]["setup"]
        assert testmon_data.all_nodes["test_a.py::test_add"]["durations"]["call"]
        assert testmon_data.all_nodes["test_a.py::test_add"]["durations"]["teardown"]

    def test_lf(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_add():
                1/0
        """,
        )
        testdir.runpytest_inprocess("--testmon", "-v")

        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.stdout.fnmatch_lines(
            [
                "*1 failed*",
            ]
        )

        result = testdir.runpytest_inprocess("--testmon", "-v", "--lf")
        result.stdout.fnmatch_lines(
            [
                "*selection automatically deactivated because --lf was used*",
                "*1 failed in*",
            ]
        )

    def test_easy(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_add():
                assert add(1, 2) == 3

            def add(a, b):
                return a + b
        """
        )
        result = testdir.runpytest_inprocess("--testmon", "--tb=long", "-v")
        result.stdout.fnmatch_lines(
            [
                "*test_a.py::test_add PASSED*",
            ]
        )
        testmon_data = CoreTestmonData(
            testdir.tmpdir.strpath,
            libraries=", ".join(sorted(str(p) for p in pkg_resources.working_set)),
        )
        testmon_data.determine_stable()
        assert testmon_data.all_files == {"test_a.py", LIBRARIES_KEY}
        assert testmon_data.unstable_files == set()
        assert testmon_data.stable_files == {"test_a.py", LIBRARIES_KEY}
        assert bool(testmon_data.libraries_miss) == False

    def test_libraries(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_add():
                assert True
        """
        )
        testdir.runpytest_inprocess("--testmon")

        tmdata_with_dummy_libraries = CoreTestmonData(rootdir="", libraries=", ")
        tmdata_with_dummy_libraries.determine_stable()
        assert tmdata_with_dummy_libraries.all_files == {
            "/libraries_checksum_testmon_name",
            "test_a.py",
        }
        assert tmdata_with_dummy_libraries.unstable_nodeids == {"test_a.py::test_add"}
        assert tmdata_with_dummy_libraries.unstable_files == {"test_a.py"}
        assert bool(tmdata_with_dummy_libraries.libraries_miss) == True

    def test_interrupted(self, test_a, testdir):
        testdir.runpytest_inprocess("--testmon")

        tf = testdir.makepyfile(
            test_a="""
            def test_1():
                raise KeyboardInterrupt
         """
        )
        os.utime(datafilename, (1800000000, 1800000000))
        tf.setmtime(1800000000)

        testdir.runpytest_subprocess(
            "--testmon",
        )

        assert 1800000000 == os.path.getmtime(datafilename)

    def test_interrupted01(self, testdir):
        testdir.makepyfile(
            test_a="""
                import time
                def test_1():
                    time.sleep(0.05)
                
                def test_2():
                    time.sleep(0.10)

                def test_3():
                    time.sleep(0.15)
        """
        )
        testdir.runpytest_inprocess("--testmon")

        tf = testdir.makepyfile(
            test_a="""
                import time
                def test_1():
                    time.sleep(0.015)
                
                def test_2():
                    raise KeyboardInterrupt

                def test_3():
                    time.sleep(0.035)
         """
        )
        td = CoreTestmonData(testdir.tmpdir.strpath)
        td.determine_stable()
        assert td.unstable_nodeids == {
            "test_a.py::test_1",
            "test_a.py::test_2",
            "test_a.py::test_3",
        }

        result = testdir.runpytest_subprocess("--testmon", "-v")
        result.stdout.fnmatch_lines(["*test_a.py::test_1 PASSED*"])
        result.stdout.no_fnmatch_line("*test_a.py::test_2 PASSED*")

        td.determine_stable()
        assert td.unstable_nodeids == {"test_a.py::test_2", "test_a.py::test_3"}

    def test_outcomes_exit(self, test_a, testdir):
        testdir.runpytest_inprocess("--testmon")

        tf = testdir.makepyfile(
            test_a="""
             def test_1():
                 import pytest
                 pytest.exit("pytest_exit")
         """
        )
        os.utime(datafilename, (1800000000, 1800000000))
        tf.setmtime(1800000000)
        testdir.runpytest_inprocess(
            "--testmon",
        )
        assert 1800000000 == os.path.getmtime(datafilename)

    def test_nonfunc_class(self, testdir, monkeypatch):
        cs1 = CodeSample(
            """\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_two(self):
                    print("2")
        """
        )

        cs2 = CodeSample(
            """\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_twob(self):
                    print("2")
        """
        )
        Module(cs2.source_code)

        test_a = testdir.makepyfile(test_a=cs1.source_code)
        result = testdir.runpytest_inprocess("--testmon", "test_a.py::TestA::test_one")
        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )

        testdir.makepyfile(test_a=cs2.source_code)
        test_a.setmtime(1424880935)
        result = testdir.runpytest_inprocess("-v", "--testmon")
        result.stdout.fnmatch_lines(
            [
                "*2 passed*",
            ]
        )

    def test_strange_argparse_handling(self, testdir):
        cs1 = CodeSample(
            """\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_two(self):
                    print("2")
        """
        )

        testdir.makepyfile(test_a=cs1.source_code)
        result = testdir.runpytest_inprocess(
            "-v", "--testmon", "test_a.py::TestA::test_one"
        )
        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )

    def test_nonfunc_class_2(self, testdir):
        testdir.parseconfigure()
        cs2 = CodeSample(
            """\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_twob(self):
                    print("2")
        """
        )
        testdir.makepyfile(test_a=cs2.source_code)

        result = testdir.runpytest_inprocess(
            "-vv",
            "--collectonly",
            "--testmon",
        )
        result.stdout.fnmatch_lines(
            [
                "*test_one*",
            ]
        )

    def test_new(self, testdir):
        a = testdir.makepyfile(
            a="""
            def add(a, b):
                a = a
                return a + b

            def subtract(a, b):
                return a - b
        """
        )

        testdir.makepyfile(
            b="""
            def divide(a, b):
                return a // b

            def multiply(a, b):
                return a * b
        """
        )

        testdir.makepyfile(
            test_a="""
            from a import add, subtract
            import time

            def test_add():
                assert add(1, 2) == 3

            def test_subtract():
                assert subtract(1, 2) == -1
                    """
        )

        testdir.makepyfile(
            test_b="""
            import unittest

            from b import multiply, divide

            class TestB(unittest.TestCase):
                def test_multiply(self):
                    self.assertEqual(multiply(1, 2), 2)

                def test_divide(self):
                    self.assertEqual(divide(1, 2), 0)
        """
        )
        testdir.makepyfile(
            test_ab="""
            from a import add
            from b import multiply
            def test_add_and_multiply():
                assert add(2, 3) == 5
                assert multiply(2, 3) == 6
        """
        )
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*5 passed*",
            ]
        )
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*collected 0 items*",
            ]
        )
        a.setmtime(1424880935)
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*5 deselected*",
            ]
        )

    def test_remove_lib(self, testdir):
        lib = testdir.makepyfile(
            lib="""
            def a():
                return 1
        """
        )

        testdir.makepyfile(
            test_a="""
            try:
                from lib import a
            except:
                pass

            def test_a():
                
                assert a() == 1
                """
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.assert_outcomes(1, 0, 0)
        time.sleep(0.01)
        lib.remove()
        result = testdir.runpytest_inprocess("--testmon")
        result.assert_outcomes(0, 0, 1)

    def test_newr(self, testdir):
        a = testdir.makepyfile(
            a="""
            def add(a, b):
                a = a
                return a + b

            def subtract(a, b):
                return a - b
        """
        )

        testdir.makepyfile(
            b="""
            def divide(a, b):
                return a // b

            def multiply(a, b):
                return a * b
        """
        )

        testdir.makepyfile(
            a_test="""
            from a import add, subtract
            import time

            def test_add():
                assert add(1, 2) == 3

            def test_subtract():
                assert subtract(1, 2) == -1
                    """
        )

        testdir.makepyfile(
            b_test="""
            import unittest

            from b import multiply, divide

            class TestB(unittest.TestCase):
                def test_multiply(self):
                    self.assertEqual(multiply(1, 2), 2)

                def test_divide(self):
                    self.assertEqual(divide(1, 2), 0)
        """
        )

        testdir.makepyfile(
            ab_test="""
            from a import add
            from b import multiply
            def test_add_and_multiply():
                assert add(2, 3) == 5
                assert multiply(2, 3) == 6
        """
        )
        result = testdir.runpytest_inprocess(
            "--testmon",
        )
        result.stdout.fnmatch_lines(
            [
                "*5 passed*",
            ]
        )
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*collected 0 items*",
            ]
        )
        a.setmtime(1424880935)
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*5 deselected*",
            ]
        )

    def test_new2(self, testdir):
        a = testdir.makepyfile(
            a="""
            def add(a, b):
                return a + b
        """
        )

        testdir.makepyfile(
            test_a="""
            from a import add

            def test_add():
                assert add(1, 2) == 3
                    """
        )

        result = testdir.runpytest_inprocess(
            "--testmon",
        )
        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )

        a = testdir.makepyfile(
            a="""
            def add(a, b):
                return a + b + 0
        """
        )
        a.setmtime(1424880935)
        result = testdir.runpytest_inprocess(
            "--testmon",
        )
        result.stdout.fnmatch_lines(
            [
                "*passed*",
            ]
        )

    def test_zero_lines_touched(self, testdir):
        testdir.makepyfile(
            test_c="""
            import unittest

            class TestA(unittest.TestCase):
                @unittest.skip('')
                def test_add(self):
                    pass
        """
        )
        result = testdir.runpytest_inprocess(
            "--testmon",
        )
        result.stdout.fnmatch_lines(
            [
                "*1 skipped*",
            ]
        )

    def test_changed_data_version(self, testdir, monkeypatch):
        testdir.makepyfile(
            test_pass="""
            def test_pass():
                pass
        """
        )
        result = testdir.runpytest_inprocess("--testmon")
        assert result.ret == 0

        monkeypatch.setattr(db, "DATA_VERSION", db.DATA_VERSION + 1)
        result = testdir.runpytest("--testmon")

        assert result.ret != 0
        result.stderr.fnmatch_lines(
            [
                "*The stored data file *{} version ({}) is not compatible with current version ({}).*".format(
                    datafilename,
                    db.DATA_VERSION - 1,
                    db.DATA_VERSION,
                ),
            ]
        )

    def test_dependent_testmodule(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass
        """
        )
        testdir.makepyfile(
            test_b="""
            import test_a
            def test_2():
                pass
        """
        )

        result = testdir.runpytest_inprocess("--testmon")
        assert result.ret == 0

        testdir.makepyfile(
            test_b="""
            import test_a
            def test_2():
                pass
                pass
        """
        )

        result = testdir.runpytest_inprocess("--testmon")
        assert result.ret == 0
        result.stdout.fnmatch_lines(
            [
                "*1 passed, 1 deselected*",
            ]
        )

    def test_track_pytest_equal(self, testdir, monkeypatch):
        a = testdir.makepyfile(
            test_a="""\
        def test_1():
            a=1
        """
        )

        def func():
            testdir.runpytest("test_a.py")

        deps = track_it(testdir, func)
        assert {
            os.path.relpath(a.strpath, testdir.tmpdir.strpath): encode_lines(
                ["def test_1():", "    a=1"]
            )
        } == deps

    def test_run_dissapearing(self, testdir):
        a = testdir.makepyfile(
            test_a="""\
            import sys
            import os
            with open('b73003.py', 'w') as f:
                f.write("print('printing from b73003.py')")
            sys.path.append('.')
            import b73003
            os.remove('b73003.py')
        """
        )

        def f():
            coveragetest.import_local_file("test_a")

        deps = track_it(testdir, f)
        assert os.path.relpath(a.strpath, testdir.tmpdir.strpath) in deps
        assert len(deps) == 1

    def test_report_roundtrip(self, testdir):
        class PlugRereport:
            def pytest_runtest_protocol(self, item, nextitem):
                hook = getattr(item.ihook, "pytest_runtest_logreport")
                return True

        testdir.makepyfile(
            """
        def test_a():
            raise Exception('exception from test_a')
        """
        )

        result = testdir.runpytest_inprocess(
            "-s",
            "-v",
            plugins=[PlugRereport()],
        )

        result.stdout.fnmatch_lines(
            [
                "*no tests ran*",
            ]
        )

    def test_dependent_testmodule2(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass
        """
        )
        testdir.makepyfile(
            test_b="""
            import test_a
            def test_2():
                pass
        """
        )

        result = testdir.runpytest_inprocess("--testmon")
        assert result.ret == 0

        testdir.makepyfile(
            test_b="""
            import test_a
            def test_2():
                pass
                pass
        """
        )

        result = testdir.runpytest_inprocess("--testmon")
        assert result.ret == 0
        result.stdout.fnmatch_lines(
            [
                "*1 passed, 1 deselected*",
            ]
        )

    def test_dependent_testmodule_failures_accumulating(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass
        """
        )
        testdir.makepyfile(
            test_b="""
            import test_a
            def test_2():
                test_a.test_1()
                raise Exception()
        """
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.assert_outcomes(1, 0, 1)

        tf = testdir.makepyfile(
            test_b="""
            import test_a
            def test_2():
                pass
        """
        )
        tf.setmtime(1)
        result = testdir.runpytest_inprocess("--testmon-forceselect", "--lf")
        assert result.ret == 0
        result.assert_outcomes(1, 0, 0)

        result.stdout.fnmatch_lines(
            [
                "*1 passed, 1 deselected*",
            ]
        )

    def test_dependent_testmodule_collect_ignore_error(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass

            def a():
                pass
        """
        )
        testdir.makepyfile(
            test_b="""
            import test_a
            def test_2():
                test_a.a()
                pass
                        """
        )
        testdir.runpytest_inprocess("--testmon")

        tf = testdir.makepyfile(
            test_b="""
            import test_a
            def test_2():
                test_a.a()
                pass
                pass
        """
        )
        tf.setmtime(1)
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 passed, 1 deselected*",
            ]
        )

    def test_collection_not_abort(self, testdir):
        testdir.makepyfile(
            test_collection_not_abort="""
            def test_1():
                1

            def test_2():
                assert False
                """
        )

        testdir.runpytest_inprocess("--testmon")

        tf = testdir.makepyfile(
            test_collection_not_abort="""
            def test_1():
                2

            def test_2():
                assert False
        """
        )
        tf.setmtime(1)

        result = testdir.runpytest_inprocess("-v", "--testmon")

        result.stdout.fnmatch_lines(
            [
                "*test_collection_not_abort.py::test_2 FAILED*",
            ]
        )

    def test_failures_storage_retrieve(self, testdir):
        testdir.makepyfile(
            test_a="""
            import pytest

            @pytest.fixture
            def error():
                raise Exception()

            def test_b(error):
                assert 1        
        """
        )

        result = testdir.runpytest_inprocess("--testmon")
        result.assert_outcomes(0, 0, 0, 1)

        result = testdir.runpytest_inprocess("--testmon")
        result.assert_outcomes(0, 0, 0, 1)
        result.stdout.fnmatch_lines(
            [
                "*1 error*",
            ]
        )

    def test_syntax_error(self, testdir):
        testdir.makepyfile(
            test_a="""\
            def test_1():
                pass
        """
        )
        testdir.runpytest_inprocess("--testmon")

        testdir.makepyfile(
            test_a="""\
            def test_1():
                1 = 2
        """
        )
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(["*ERROR collecting test_a.py*"])

    def test_update_mtimes(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass
            def test_2():
                pass        
        """
        )
        testdir.runpytest_inprocess("--testmon")
        testdir.makepyfile(
            test_a="""
            def test_1():
                a=1
                pass
            def test_2():
                pass        
        """
        )
        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*changed files: test_a.py*",
            ]
        )

        result = testdir.runpytest_inprocess("--testmon-nocollect")
        result.stdout.fnmatch_lines(
            [
                "*changed files: 0*",
            ]
        )


class TestPytestCollectionPhase:
    def test_sync_after_collectionerror(self, testdir):
        testdir.makepyfile(
            test_a="""
                def test_0():
                    pass
                
                def test_2():
                    pass
            """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )
        testdir.makepyfile(
            test_a="""
                def test_0():
                    pass
                
                def test_2():
                    try: # This is wrong syntax and will cause collection error.
            """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )
        testdir.makepyfile(
            test_a="""
                def test_0():
                    pass
                
                def test_2():
                    print(1)
            """
        )
        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.stdout.fnmatch_lines(
            [
                "*test_2 PASSED*",
            ]
        )


while_running_condition = Condition()


class TestmonCollect:
    @pytest.mark.xfail
    def test_change_while_running_no_data(self, testdir):
        def make_second_version(condition):
            with condition:
                condition.wait()
                t = testdir.makepyfile(test_a=test_template.replace("$r", "2 == 3"))
                t.setmtime(2640053809)

        test_template = """
                from test import test_testmon

                with test_testmon.while_running_condition:
                    test_testmon.while_running_condition.notify()

                def test_1():
                    assert $r
            """

        testdir.makepyfile(test_a=test_template.replace("$r", "1 == 1"))
        thread = Thread(target=make_second_version, args=(while_running_condition,))
        thread.start()
        testdir.runpytest_inprocess(
            "--testmon",
        )
        thread.join()

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 failed*",
            ]
        )

    def test_change_while_running_with_data(self, testdir):
        def make_third_version(condition):
            with condition:
                condition.wait()
                t = testdir.makepyfile(test_a=test_template.replace("$r", "2 == 3"))
                t.setmtime(2640053809)

        test_template = """
                    from test import test_testmon

                    with test_testmon.while_running_condition:
                        test_testmon.while_running_condition.notify()

                    def test_1():
                        assert $r
                """

        testdir.makepyfile(test_a=test_template.replace("$r", "1 == 1"))

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )

        file = testdir.makepyfile(test_a=test_template.replace("$r", "2 == 2"))
        file.setmtime(2640044809)

        thread = Thread(target=make_third_version, args=(while_running_condition,))
        thread.start()

        result = testdir.runpytest_inprocess("--testmon")

        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )

        thread.join()

        result = testdir.runpytest_inprocess("--testmon")
        result.stdout.fnmatch_lines(
            [
                "*1 failed*",
            ]
        )

    def test_failed_setup_phase(self, testdir):
        testdir.makepyfile(
            fixture="""
                import pytest

                @pytest.fixture
                def fixturetest():
                    raise Exception("from fixture")
        """,
            test_a="""
            from fixture import fixturetest
            def test_1(fixturetest):
                pass
        """,
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )
        td = CoreTestmonData(testdir.tmpdir.strpath)
        assert td.all_files == {"fixture.py", LIBRARIES_KEY, "test_a.py"}

    def test_remove_dependent_file(self, testdir):
        testdir.makepyfile(
            lib="""
                def oneminus(a):
                    return a - 1
        """,
            test_a="""
                from lib import oneminus
                def test_1():
                    oneminus(1)
        """,
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )
        f = testdir.makepyfile(
            test_a="""
            def test_1():
                pass
        """
        )
        f.setmtime(12345)
        testdir.runpytest_inprocess(
            "--testmon",
        )
        td = CoreTestmonData(testdir.tmpdir.strpath)
        assert td.all_files == {"test_a.py", LIBRARIES_KEY}

    def test_pytest_k_deselect(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass
            def test_2():
                pass        
        """
        )
        testdir.runpytest_inprocess("--testmon", "-k test_1")
        time.sleep(0.1)
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass
            def test_2():
                print()        
        """
        )
        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.stdout.fnmatch_lines(
            [
                "*test_2 PASSED*",
            ]
        )

    def test_pytest_argument_deselect(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass
            def test_2():
                pass        
        """
        )

        testdir.runpytest_inprocess("--testmon", "test_a.py::test_1")
        time.sleep(0.1)
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass
            def test_2():
                print()        
        """
        )
        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.stdout.fnmatch_lines(
            [
                "*test_2 PASSED*",
            ]
        )

    def test_external_deselect_garbage(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_1():
                pass
            def test_2():
                pass        
        """
        )
        testdir.runpytest_inprocess("--testmon")
        time.sleep(0.1)
        testdir.makepyfile(
            test_a="""
            def test_1():
                print()
            def test_2():
                print(2)        
        """
        )
        testdir.runpytest_inprocess("--testmon", "-v", "-k test_1")
        time.sleep(0.1)
        testdir.makepyfile(
            test_a="""
            def test_1():
                print()
            def test_2():
                print()        
        """
        )

        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.stdout.fnmatch_lines(
            [
                "*test_2 PASSED*",
            ]
        )

    def test_dont_collect_doc_test(self, testdir):
        testdir.maketxtfile(
            test_doc="""
                >>> 1
                1
            """
        )
        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )
        result = testdir.runpytest_inprocess("--testmon", "-v")
        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )

    def test_dogfooding_allowed(self, testdir):
        testdir.makepyfile(
            test_a="""
            pytest_plugins = "pytester",
            def test_nested_test(testdir):
                testdir.makepyfile(
                    test_nested='''
                    def test_1():
                        assert True
                '''
                )
                result = testdir.runpytest_inprocess("-v", "--testmon")
                result.assert_outcomes(1, 0, 0)
        """
        )

        result = testdir.runpytest_inprocess("-v", "--testmon")
        result.assert_outcomes(1, 0, 0)


class TestLineAlgEssentialProblems:
    def test_add_line_at_beginning(self, testdir):
        testdir.makepyfile(
            test_a="""
            def test_a():
                assert 1 + 2 == 3
        """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )
        testdir.makepyfile(
            test_a="""
            def test_a():
                1/0
                assert 1 + 2 == 3
        """
        )
        result = testdir.runpytest_inprocess(
            "--testmon",
        )
        result.stdout.fnmatch_lines(
            [
                "*1 failed*",
            ]
        )

    def test_add_line_at_end(self, testdir):
        testdir.makepyfile(
            test_a="""
                   def test_a():
                       assert 1 + 2 == 3
               """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )
        testdir.makepyfile(
            test_a="""
                   def test_a():
                       assert 1 + 2 == 3
                       1/0
                """
        )
        result = testdir.runpytest_inprocess(
            "--testmon",
        )
        result.stdout.fnmatch_lines(
            [
                "*1 failed*",
            ]
        )

    def test_remove_method_definition(self, testdir):
        testdir.makepyfile(
            test_a="""
                           def test_1():
                               assert 1 + 2 == 3

                           def test_2():
                               assert 2 + 2 == 4
                       """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )
        testdir.makepyfile(
            test_a="""
                           def test_1():
                               assert 1 + 2 == 3

                               assert 2 + 2 == 4
                        """
        )
        result = testdir.runpytest_inprocess(
            "--testmon",
        )
        result.stdout.fnmatch_lines(
            [
                "*1 passed*",
            ]
        )


class TestPrioritization:
    def test_module_level(self, testdir):
        testdir.makepyfile(
            test_a="""
                            import time
                            def test_a():
                                time.sleep(0.5)
                        """
        )
        testdir.makepyfile(
            test_b="""
                            import time
                            def test_b():
                                time.sleep(0.1)
                        """
        )

        testdir.runpytest_inprocess(
            "--testmon",
        )
        a = testdir.makepyfile(
            test_a="""
                            import time
                            def test_a():
                                a=1
                        """
        )
        b = testdir.makepyfile(
            test_b="""
                            import time
                            def test_b():
                                b=1
                        """
        )
        a.setmtime(1424880935)
        b.setmtime(1424880935)
        result = testdir.runpytest_inprocess("--testmon-nocollect")
        result.stdout.fnmatch_lines(
            [
                "test_b.py*",
                "test_a.py*",
            ]
        )

    def test_class_level(self, testdir):
        testdir.makepyfile(
            test_m="""
                            import time
                            class TestA:
                                def test_a(self):
                                    time.sleep(0.5)
                            
                            class TestB:
                                def test_b(self):
                                    time.sleep(0.1)            
                        """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )
        m = testdir.makepyfile(
            test_m="""
                            import time
                            class TestA:
                                def test_a(self):
                                    a=1

                            class TestB:
                                def test_b(self):
                                    b=1
                        """
        )
        m.setmtime(1424880935)
        result = testdir.runpytest_inprocess("--testmon-nocollect", "-v")
        result.stdout.fnmatch_lines(
            [
                "*TestB*",
                "*TestA*",
            ]
        )

    def test_node_level(self, testdir):
        testdir.makepyfile(
            test_m="""
                            import time
                            def test_a():
                                time.sleep(0.5)

                            def test_b():
                                time.sleep(0.1)            
                        """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )
        m = testdir.makepyfile(
            test_m="""
                            def test_a():
                                a=1
                                
                            def test_b():
                                b=1            
                        """
        )
        m.setmtime(1424880935)
        result = testdir.runpytest_inprocess("--testmon-nocollect", "-v")
        result.stdout.fnmatch_lines(
            [
                "*test_b*",
                "*test_a*",
            ]
        )

    def test_report_failed_stable_last(self, testdir):
        testdir.makepyfile(
            test_m="""
                           def test_a():
                               assert False

                           def test_b():
                               b = 1             
                       """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )

        testdir.makepyfile(
            test_m="""
                           def test_a():
                               assert False

                           def test_b():
                               b = 2             
                       """
        )
        result = testdir.runpytest_inprocess("--testmon-nocollect", "-v")
        result.stdout.fnmatch_lines(
            [
                "*test_b PASSED*",
                "*test_a FAILED*",
            ]
        )

    def test_interrupted2(self, testdir):
        testdir.makepyfile(
            test_m="""
                import time     
                def test_a():
                   time.sleep(0.05)

                def test_b():
                   time.sleep(0.10)             

                def test_c():
                   time.sleep(0.15)             
                       """
        )
        testdir.runpytest_inprocess(
            "--testmon",
        )

        testdir.makepyfile(
            test_m="""
                import time     
                def test_a():
                   time.sleep(0.051)

                def test_b():
                   raise KeyboardInterrupt             

                def test_c():
                   time.sleep(0.151)             
               
                       """
        )

        result = testdir.runpytest_subprocess("--testmon", "-v", "--full-trace")

        testdir.makepyfile(
            test_m="""
                import time     
                def test_a():
                   time.sleep(0.051)
                
                def test_b():
                   time.sleep(0.102)             

                def test_c():
                   time.sleep(0.152)             
                       """
        )
        result = testdir.runpytest_inprocess("--testmon", "-v")

        result.stdout.no_fnmatch_line("*test_a PASSED*")

        result.stdout.fnmatch_lines(
            [
                "*test_b PASSED*",
                "*test_c PASSED*",
            ]
        )


class TestXdist(object):
    def test_xdist_4(self, testdir):
        pytest.importorskip("xdist")
        testdir.makepyfile(
            test_a="""
            import pytest
            def test_0():
                1
                
            @pytest.mark.parametrize("a", [
                                    ("test0", ),
                                    ("test1", ),
                                    ("test2", ),
                                    ("test3", )
            ])
            def test_1(a):
                print(a)
            """
        )

        testdir.runpytest_inprocess("test_a.py::test_0", "--testmon", "-v")
        time.sleep(0.1)
        result = testdir.runpytest_inprocess("test_a.py", "--testmon", "-n 4", "-v")
        result.stdout.fnmatch_lines(
            [
                "*deactivated, execution with xdist is not supported*",
            ]
        )
