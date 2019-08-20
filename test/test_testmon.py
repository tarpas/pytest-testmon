import os
import sys
import textwrap
from multiprocessing import Queue, Process
import pytest

from test.coveragepy import coveragetest
from testmon_dev.process_code import Module
from testmon_dev.testmon_core import eval_variant, NodesData
from testmon_dev.testmon_core import Testmon as CoreTestmon, TestmonData
from testmon_dev.testmon_core import TestmonData as CoreTestmonData
from test.test_process_code import CodeSample
from testmon_dev.pytest_testmon import PLUGIN_NAME, READONLY_OPTION

pytest_plugins = "pytester",

datafilename = os.environ.get('TESTMON_DATAFILE', '.testmondata')


def _track_it(queue, testdir, func):
    testmon = CoreTestmon(project_dirs=[testdir.tmpdir.strpath],
                          testmon_labels=set())
    testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
    testmon_data.read_source()
    testmon.start()
    func()
    testmon.stop_and_save(testmon_data, testdir.tmpdir.strpath, 'testnode', {})

    queue.put(testmon_data._fetch_node_data()[0]['testnode'])


def track_it(testdir, func):
    queue = Queue()
    p = Process(target=_track_it, args=(queue, testdir, func))
    p.start()
    p.join()
    return queue.get()


class TestVariant:

    def test_separation(self, testdir):
        testmon1_data = CoreTestmonData(testdir.tmpdir.strpath, variant='1')
        testmon1_data.node_data['node1'] = {'a.py': 1}
        testmon1_data.write_common_data()
        testmon2_data = CoreTestmonData(testdir.tmpdir.strpath, variant='2')
        testmon2_data.node_data['node1'] = {'a.py': 2}
        testmon2_data.write_common_data()
        testmon_check_data = CoreTestmonData(testdir.tmpdir.strpath, variant='1')
        assert testmon1_data.node_data['node1'] == NodesData({'a.py': 1})

    def test_header(self, testdir):
        testdir.makeini("""
                        [pytest]
                        run_variant_expression='1'
                        """)
        result = testdir.runpytest_subprocess("-v", f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*testmon=True, *, run variant: 1*",
        ])

    def test_header_nonstr(self, testdir):
        testdir.makeini("""
                        [pytest]
                        run_variant_expression=int(1)
                        """)
        result = testdir.runpytest_subprocess("-v", f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*testmon=True, *, run variant: 1*",
        ])

    def test_empty(self, testdir):
        config = testdir.parseconfigure()
        assert eval_variant(config.getini('run_variant_expression')) == ''

    def test_run_variant_md5(self, testdir, monkeypatch):
        testdir.makeini("""
                        [pytest]
                        run_variant_expression=md5('TEST')
                        """)
        config = testdir.parseconfigure()
        assert eval_variant(config.getini('run_variant_expression')) == '033bd94b1168d7e4f0d644c3c95e35bf'

    def test_env(self, testdir, monkeypatch):
        monkeypatch.setenv('TEST_V', 'JUST_A_TEST')
        testdir.makeini("""
                        [pytest]
                        run_variant_expression=os.environ.get('TEST_V')
                        """)
        config = testdir.parseconfigure()
        assert eval_variant(config.getini('run_variant_expression')) == 'JUST_A_TEST'

    def test_nonsense(self, testdir):
        testdir.makeini("""
                        [pytest]
                        run_variant_expression=nonsense
                        """)
        config = testdir.parseconfigure()
        assert 'NameError' in eval_variant(config.getini('run_variant_expression'))

    def test_complex(self, testdir, monkeypatch):
        "Test that ``os`` is available in list comprehensions."
        monkeypatch.setenv('TEST_V', 'JUST_A_TEST')
        testdir.makeini("""
                        [pytest]
                        run_variant_expression="_".join([x + ":" + os.environ[x] for x in os.environ if x == 'TEST_V'])
                        """)
        config = testdir.parseconfigure()
        assert eval_variant(config.getini('run_variant_expression')) == 'TEST_V:JUST_A_TEST'


class TestmonDeselect(object):
    def test_dont_readcoveragerc(self, testdir):
        p = testdir.tmpdir.join('.coveragerc')
        p.write("[")
        testdir.makepyfile(test_a="""
            def test_add():
                pass
        """)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )

    def test_simple_change(self, testdir):
        testdir.makepyfile(test_a="""
            def test_add():
                assert 1 + 2 == 3
                    """)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*1 passed*",
        ])

        test_a = testdir.makepyfile(test_a="""
            def test_add():
                assert 1 + 2 + 3 == 6
                    """)
        test_a.setmtime(1424880935)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*passed*",
        ])

    def test_simple_change_1_of_2(self, testdir):
        testdir.makepyfile(test_a="""
            def test_add():
                assert 1 + 2 == 3
            
            def test_2():
                assert True
                    """)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*2 passed*",
        ])

        test_a = testdir.makepyfile(test_a="""
            def test_add():
                assert 1 + 2 + 3 == 6
                            
            def test_2():
                assert True

                    """)
        test_a.setmtime(1424880935)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*1 passed, 1 deselected*",
        ])

    def test_simple_change_1_of_2_with_decorator(self, testdir):
        testdir.makepyfile(test_a="""
            import pytest

            @pytest.mark.one
            def test_add():
                assert 1 + 2 == 3

            def test_2():
                assert True
                    """)

        result = testdir.runpytest(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*2 passed*",
        ])

        test_a = testdir.makepyfile(test_a="""
            import pytest

            @pytest.mark.one
            def test_add():
                assert 1 + 2 + 3 == 6

            def test_2():
                assert True

                    """)
        test_a.setmtime(1424880935)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*1 passed, 1 deselected*",
        ])

    def test_not_running_after_failure(self, testdir):
        tf = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """, )

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.assert_outcomes(1, 0, 0)

        sys.modules.pop('test_a', None)

        tf = testdir.makepyfile(test_a="""
            def test_add():
                1/0
        """, )
        tf.setmtime(1424880936)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")
        result.assert_outcomes(0, 0, 1)
        sys.modules.pop('test_a', None)

        tf = testdir.makepyfile(test_a="""
            def test_add():
                blas
        """, )
        tf.setmtime(1424880937)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")
        result.assert_outcomes(0, 0, 1)

        sys.modules.pop('test_a', None)

        tf = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """, )
        tf.setmtime(1424880938)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")
        result.assert_outcomes(1, 0, 0)
        sys.modules.pop('test_a', None)

    def test_fantom_failure(self, testdir):
        testdir.makepyfile(test_a="""
            def test_add():
                1/0
        """, )
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")

        tf = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """, )
        tf.setmtime(1)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")
        result.assert_outcomes(0, 0, 0)

    def test_skipped(self, testdir):
        testdir.makepyfile(test_a="""
            import pytest
            @pytest.mark.skip
            def test_add():
                1/0
        """, )
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")
        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
        testmon_data.read_data()
        assert testmon_data.node_data['test_a.py::test_add']['test_a.py']

    def test_skipped_starting_line2(self, testdir):
        testdir.makepyfile(test_a="""
            #line not in AST
            import pytest
            @pytest.mark.skip
            def test_add():
                1/0
        """, )
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")
        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
        testmon_data.read_data()
        assert testmon_data.node_data['test_a.py::test_add']['test_a.py']

    def test_skipped_under_dir(self, testdir):
        subdir = testdir.mkdir("tests")

        tf = subdir.join("test_a.py")
        tf.write(textwrap.dedent("""
            import pytest
            @pytest.mark.skip
            def test_add():
                1/0
        """, ))
        tf.setmtime(1)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v", "tests")

        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
        testmon_data.read_data()

        fname = os.path.sep.join(['tests', 'test_a.py'])
        assert testmon_data.node_data['tests/test_a.py::test_add'][fname]

    def test_wrong_result_processing(self, testdir):
        tf = testdir.makepyfile(test_a="""
            def test_add():
                1/0
        """, )
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")
        testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
        testmon_data.read_data()
        assert len(testmon_data.reports['test_a.py::test_add']) == 3

        tf = testdir.makepyfile(test_a="""
            import pytest
            @pytest.mark.skip
            def test_add():
                1/0/0
        """, )
        tf.setmtime(1)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")

        testmon_data.read_data()
        assert len(testmon_data.reports['test_a.py::test_add']) == 2

        tf = testdir.makepyfile(test_a="""
            import pytest
            def test_add():
                1/0
        """, )
        tf.setmtime(2)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")

        testmon_data.read_data()
        assert len(testmon_data.reports['test_a.py::test_add']) == 3

    def test_tlf(self, testdir):
        testdir.makepyfile(test_a="""
            def test_add():
                1/0
        """, )
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v")
        result.stdout.fnmatch_lines([
            "*1 failed, 1 deselected*",
        ])

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "-v", f"--{PLUGIN_NAME}-tlf")
        result.stdout.fnmatch_lines([
            "*1 failed in*",
        ])

    def test_easy(self, testdir):
        testdir.makepyfile(test_a="""
            def test_add():
                assert add(1, 2) == 3

            def add(a, b):
                return a + b
        """)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "--tb=long", "-v")
        result.stdout.fnmatch_lines([
            "*test_a.py::test_add PASSED*",
        ])

    def test_interrupted(self, testdir):
        testdir.makepyfile(test_a="""
             def test_1():
                 1

             def test_2():
                 2
         """)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")

        tf = testdir.makepyfile(test_a="""
             def test_1():
                 raise KeyboardInterrupt

             def test_2():
                 3
         """)
        os.utime(datafilename, (1800000000, 1800000000))
        tf.setmtime(1800000000)

        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )

        # interrupted run shouldn't save .testmondata
        assert 1800000000 == os.path.getmtime(datafilename)

    def test_outcomes_exit(self, testdir):
        testdir.makepyfile(test_a="""
             def test_1():
                 1

             def test_2():
                 2
         """)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")

        tf = testdir.makepyfile(test_a="""
             def test_1():
                 import pytest
                 pytest.exit("pytest_exit")

             def test_2():
                 3
         """)
        os.utime(datafilename, (1800000000, 1800000000))
        tf.setmtime(1800000000)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        # interrupted run shouldn't save .testmondata
        assert 1800000000 == os.path.getmtime(datafilename)

    def test_nonfunc_class(self, testdir, monkeypatch):
        cs1 = CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_two(self):
                    print("2")
        """)

        cs2 = CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_twob(self):
                    print("2")
        """)
        Module(cs2.source_code)

        test_a = testdir.makepyfile(test_a=cs1.source_code)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", "test_a.py::TestA::test_one", )
        result.stdout.fnmatch_lines([
            "*1 passed*",
        ])

        testdir.makepyfile(test_a=cs2.source_code)
        test_a.setmtime(1424880935)
        result = testdir.runpytest_subprocess("-v", f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*2 passed*",
        ])

    def test_strange_argparse_handling(self, testdir):
        cs1 = CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_two(self):
                    print("2")
        """)

        testdir.makepyfile(test_a=cs1.source_code)
        result = testdir.runpytest_subprocess("-v", f"--{PLUGIN_NAME}", "test_a.py::TestA::test_one")
        result.stdout.fnmatch_lines([
            "*1 passed*",
        ])

    def test_nonfunc_class_2(self, testdir):
        testdir.parseconfigure()
        cs2 = CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_twob(self):
                    print("2")
        """)
        testdir.makepyfile(test_a=cs2.source_code)

        result = testdir.runpytest_subprocess("-vv", "--collectonly", f"--{PLUGIN_NAME}", )
        result.stdout.fnmatch_lines([
            "*test_one*",
        ])

    def test_new(self, testdir):
        a = testdir.makepyfile(a="""
            def add(a, b):
                a = a
                return a + b

            def subtract(a, b):
                return a - b
        """)

        testdir.makepyfile(b="""
            def divide(a, b):
                return a // b

            def multiply(a, b):
                return a * b
        """)

        testdir.makepyfile(test_a="""
            from a import add, subtract
            import time

            def test_add():
                assert add(1, 2) == 3

            def test_subtract():
                assert subtract(1, 2) == -1
                    """)

        testdir.makepyfile(test_b="""
            import unittest

            from b import multiply, divide

            class TestB(unittest.TestCase):
                def test_multiply(self):
                    self.assertEqual(multiply(1, 2), 2)

                def test_divide(self):
                    self.assertEqual(divide(1, 2), 0)
        """)

        testdir.makepyfile(test_ab="""
            from a import add
            from b import multiply
            def test_add_and_multiply():
                assert add(2, 3) == 5
                assert multiply(2, 3) == 6
        """)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        result.stdout.fnmatch_lines([
            "*5 passed*",
        ])
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*collected 0 items*",
        ])
        a.setmtime(1424880935)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*5 deselected*",
        ])

    def test_newr(self, testdir):
        a = testdir.makepyfile(a="""
            def add(a, b):
                a = a
                return a + b

            def subtract(a, b):
                return a - b
        """)

        testdir.makepyfile(b="""
            def divide(a, b):
                return a // b

            def multiply(a, b):
                return a * b
        """)

        testdir.makepyfile(a_test="""
            from a import add, subtract
            import time

            def test_add():
                assert add(1, 2) == 3

            def test_subtract():
                assert subtract(1, 2) == -1
                    """)

        testdir.makepyfile(b_test="""
            import unittest

            from b import multiply, divide

            class TestB(unittest.TestCase):
                def test_multiply(self):
                    self.assertEqual(multiply(1, 2), 2)

                def test_divide(self):
                    self.assertEqual(divide(1, 2), 0)
        """)

        testdir.makepyfile(ab_test="""
            from a import add
            from b import multiply
            def test_add_and_multiply():
                assert add(2, 3) == 5
                assert multiply(2, 3) == 6
        """)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        result.stdout.fnmatch_lines([
            "*5 passed*",
        ])
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*collected 0 items*",
        ])
        a.setmtime(1424880935)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines([
            "*5 deselected*",
        ])

    def test_new2(self, testdir):
        a = testdir.makepyfile(a="""
            def add(a, b):
                return a + b
        """)

        testdir.makepyfile(test_a="""
            from a import add

            def test_add():
                assert add(1, 2) == 3
                    """)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        result.stdout.fnmatch_lines([
            "*1 passed*",
        ])

        a = testdir.makepyfile(a="""
            def add(a, b):
                return a + b + 0
        """)
        a.setmtime(1424880935)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        result.stdout.fnmatch_lines([
            "*passed*",
        ])

    def test_zero_lines_touched(self, testdir):
        testdir.makepyfile(test_c="""
            import unittest

            class TestA(unittest.TestCase):
                @unittest.skip('')
                def test_add(self):
                    pass
        """)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        result.stdout.fnmatch_lines([
            "*1 skipped*",
        ])

    def test_changed_data_version(self, testdir, monkeypatch):
        testdir.makepyfile(test_pass="""
            def test_pass():
                pass
        """)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        assert result.ret == 0

        # Now change the data version and check py.test then refuses to run
        monkeypatch.setattr(TestmonData, 'DATA_VERSION', TestmonData.DATA_VERSION + 1)
        result = testdir.runpytest(f"--{PLUGIN_NAME}")

        assert result.ret != 0
        result.stderr.fnmatch_lines([
            "*The stored data file *{} version ({}) is not compatible with current version ({}).*".format(
                datafilename,
                TestmonData.DATA_VERSION - 1,
                TestmonData.DATA_VERSION),
        ])

    def test_dependent_testmodule(self, testdir):
        testdir.makepyfile(test_a="""
            def test_1():
                pass
        """)
        testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                pass
        """)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        assert result.ret == 0

        testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                pass
                pass
        """)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        assert result.ret == 0
        result.stdout.fnmatch_lines(["*1 passed, 1 deselected*", ])

    def test_track_pytest_equal(self, testdir, monkeypatch):
        a = testdir.makepyfile(test_a="""\
        def test_1():
            a=1
        """)

        def func():
            testdir.runpytest("test_a.py")

        deps = track_it(testdir, func)
        assert {os.path.relpath(a.strpath, testdir.tmpdir.strpath): ['def test_1():', '    a=1']} == deps

    @pytest.mark.skip
    def test_testmon_recursive(self, testdir, monkeypatch):
        a = testdir.makepyfile(test_a="""\
        def test_1():
            a=1
        """)

        def func():
            testdir.runpytest_subprocess("test_a.py", f"--{PLUGIN_NAME}", "--capture=no")

        deps = track_it(testdir, func)
        # os.environ.pop('COVERAGE_TEST_TRACER', None)

        assert {os.path.relpath(a.strpath, testdir.tmpdir.strpath): [['def test_1():', '    a=1']]} == deps

    def test_run_dissapearing(self, testdir):
        a = testdir.makepyfile(a="""\
            import sys
            import os
            with open('b.py', 'w') as f:
                f.write("print('printing from b.py')")
            sys.path.append('.')
            import b
            os.remove('b.py')
        """)

        def f():
            coveragetest.import_local_file('a')

        deps = track_it(testdir, f)
        assert os.path.relpath(a.strpath, testdir.tmpdir.strpath) in deps
        assert len(deps) == 1

    def test_report_roundtrip(self, testdir):
        class PlugRereport:
            def pytest_runtest_protocol(self, item, nextitem):
                hook = getattr(item.ihook, 'pytest_runtest_logreport')
                # hook(report=)
                return True

        testdir.makepyfile("""
        def test_a():
            raise Exception('exception from test_a')
        """)

        result = testdir.runpytest_inprocess("-s", "-v", plugins=[PlugRereport()], )

        result.stdout.fnmatch_lines(["*no tests ran*", ])

    def test_dependent_testmodule2(self, testdir):
        testdir.makepyfile(test_a="""
            def test_1():
                pass
        """)
        testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                pass
        """)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        assert result.ret == 0

        testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                pass
                pass
        """)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        assert result.ret == 0
        result.stdout.fnmatch_lines(["*1 passed, 1 deselected*", ])

    def test_dependent_testmodule_failures_accumulating(self, testdir):
        testdir.makepyfile(test_a="""
            def test_1():
                pass
        """)
        testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                test_a.test_1()
                raise Exception()
        """)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.assert_outcomes(1, 0, 1)

        tf = testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                pass
        """)
        tf.setmtime(1)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", f"--{PLUGIN_NAME}-tlf")
        assert result.ret == 0
        result.assert_outcomes(1, 0, 0)

        result.stdout.fnmatch_lines(["*1 passed, 1 deselected*", ])

    def test_dependent_testmodule_collect_ignore_error(self, testdir):
        testdir.makepyfile(test_a="""
            def test_1():
                pass

            def a():
                pass
        """)
        testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                test_a.a()
                pass
                        """)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")

        tf = testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                test_a.a()
                pass
                pass
        """)
        tf.setmtime(1)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.stdout.fnmatch_lines(["*1 passed, 1 deselected*", ])

    def test_collection_not_abort(self, testdir):
        testdir.makepyfile(test_collection_not_abort="""
            def test_1():
                1

            def test_2():
                assert False
                """)

        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")

        tf = testdir.makepyfile(test_collection_not_abort="""
            def test_1():
                2

            def test_2():
                assert False
        """)
        tf.setmtime(1)

        result = testdir.runpytest_subprocess("-v", f"--{PLUGIN_NAME}")

        result.stdout.fnmatch_lines(["*test_collection_not_abort.py::test_2 FAILED*", ])

    def test_failures_storage_retrieve(self, testdir):
        testdir.makepyfile(test_a="""
            import pytest

            @pytest.fixture
            def error():
                raise Exception()

            def test_b(error):
                assert 1        
        """)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.assert_outcomes(passed=0, skipped=0, failed=0, error=1)

        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}")
        result.assert_outcomes(passed=0, skipped=0, failed=0, error=1)
        result.stdout.fnmatch_lines(["*1 error*", ])


class TestLineAlgEssentialProblems:

    def test_add_line_at_beginning(self, testdir):
        testdir.makepyfile(test_a="""
            def test_a():
                assert 1 + 2 == 3
        """)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        testdir.makepyfile(test_a="""
            def test_a():
                1/0
                assert 1 + 2 == 3
        """)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        result.stdout.fnmatch_lines([
            "*1 failed*",
        ])

    def test_add_line_at_end(self, testdir):
        testdir.makepyfile(test_a="""
                   def test_a():
                       assert 1 + 2 == 3
               """)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        testdir.makepyfile(test_a="""
                   def test_a():
                       assert 1 + 2 == 3
                       1/0
                """)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        result.stdout.fnmatch_lines([
            "*1 failed*",
        ])

    def test_remove_method_definition(self, testdir):
        testdir.makepyfile(test_a="""
                           def test_1():
                               assert 1 + 2 == 3

                           def test_2():
                               assert 2 + 2 == 4
                       """)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        testdir.makepyfile(test_a="""
                           def test_1():
                               assert 1 + 2 == 3

                               assert 2 + 2 == 4
                        """)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        result.stdout.fnmatch_lines([
            "*1 passed*",
        ])


class TestPrioritization:

    def test_module_level(self, testdir):
        testdir.makepyfile(test_a="""
                            import time
                            def test_a():
                                time.sleep(0.5)
                        """)
        testdir.makepyfile(test_b="""
                            import time
                            def test_b():
                                time.sleep(0.1)
                        """)

        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        a = testdir.makepyfile(test_a="""
                            import time
                            def test_a():
                                a=1
                        """)
        b = testdir.makepyfile(test_b="""
                            import time
                            def test_b():
                                b=1
                        """)
        a.setmtime(1424880935)
        b.setmtime(1424880935)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}-{READONLY_OPTION}")
        result.stdout.fnmatch_lines([
            "test_b.py*",
            "test_a.py*",
        ])

    def test_class_level(self, testdir):
        testdir.makepyfile(test_m="""
                            import time
                            class TestA:
                                def test_a(self):
                                    time.sleep(0.5)
                            
                            class TestB:
                                def test_b(self):
                                    time.sleep(0.1)            
                        """)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        m = testdir.makepyfile(test_m="""
                            import time
                            class TestA:
                                def test_a(self):
                                    a=1

                            class TestB:
                                def test_b(self):
                                    b=1
                        """)
        m.setmtime(1424880935)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}-{READONLY_OPTION}", "-v")
        result.stdout.fnmatch_lines([
            "*TestB*",
            "*TestA*",
        ])

    def test_node_level(self, testdir):
        testdir.makepyfile(test_m="""
                            import time
                            def test_a():
                                time.sleep(0.5)

                            def test_b():
                                time.sleep(0.1)            
                        """)
        testdir.runpytest_subprocess(f"--{PLUGIN_NAME}", )
        m = testdir.makepyfile(test_m="""
                            def test_a():
                                a=1
                                
                            def test_b():
                                b=1            
                        """)
        m.setmtime(1424880935)
        result = testdir.runpytest_subprocess(f"--{PLUGIN_NAME}-{READONLY_OPTION}", "-v")
        result.stdout.fnmatch_lines([
            "*test_b*",
            "*test_a*",
        ])


class TestXdist(object):

    def test_xdist_4(self, testdir):
        pytest.importorskip("xdist")
        testdir.makepyfile(test_a="""
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
            """)

        testdir.runpytest_subprocess("test_a.py::test_0", f"--{PLUGIN_NAME}")  # xdist is not supported on the first run
        result = testdir.runpytest_subprocess("test_a.py", f"--{PLUGIN_NAME}", "-n 4", "-v")
        result.stdout.fnmatch_lines([
            "*testmon=True, *",
            "*PASSED test_a.py::test_1[a0*"
        ])
