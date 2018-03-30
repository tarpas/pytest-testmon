import os
import sys

import pytest
import testmon.process_code
from test.coveragepy import coveragetest
from testmon.process_code import Module, checksum_coverage
from testmon.testmon_core import eval_variant, TestmonData as CoreTestmonData
from testmon.testmon_core import Testmon as CoreTestmon
from testmon.testmon_core import TestmonData as CoreTestmonData
from test.test_process_code import CodeSample

pytest_plugins = "pytester",


class TestVariant:

    def test_separation(self, testdir):
        testmon1_data = CoreTestmonData(testdir.tmpdir.strpath, variant='1')
        testmon1_data.node_data['node1'] = {'a.py': 1}
        testmon1_data.write_data()

        testmon2_data = CoreTestmonData(testdir.tmpdir.strpath, variant='2')
        testmon2_data.node_data['node1'] = {'a.py': 2}
        testmon2_data.write_data()

        testmon_check_data = CoreTestmonData(testdir.tmpdir.strpath, variant='1')
        assert testmon1_data.node_data['node1'] == {'a.py': 1}

    def test_header(self, testdir):
        testdir.makeini("""
                        [pytest]
                        run_variant_expression='1'
                        """)
        result = testdir.runpytest("-v", "--testmon")
        result.stdout.fnmatch_lines([
            "*testmon=True, *, run variant: 1*",
        ])

    def test_header_nonstr(self, testdir):
        testdir.makeini("""
                        [pytest]
                        run_variant_expression=int(1)
                        """)
        result = testdir.runpytest("-v", "--testmon")
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


def track_it(testdir, func):
    testmon = CoreTestmon(project_dirs=[testdir.tmpdir.strpath],
                          testmon_labels=set())
    testmon_data = CoreTestmonData(testdir.tmpdir.strpath)
    testmon_data.read_source()
    testmon.start()
    func()
    testmon.stop_and_save(testmon_data, testdir.tmpdir.strpath, 'testnode', [])
    return testmon_data._fetch_node_data()[0]['testnode']


class TestmonDeselect(object):
    def test_dont_readcoveragerc(self, testdir):
        p = testdir.tmpdir.join('.coveragerc')
        p.write("[")
        testdir.makepyfile(test_a="""
            def test_add():
                pass
        """)
        testdir.inline_run(["--testmon", ])

    def test_not_running_after_failure(self, testdir):
        tf = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """, )
        reprec = testdir.inline_run("--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (1, 0, 0), res
        sys.modules.pop('test_a', None)

        tf = testdir.makepyfile(test_a="""
            def test_add():
                1/0
        """, )
        tf.setmtime(1424880936)
        reprec = testdir.inline_run("--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (0, 0, 1), res
        sys.modules.pop('test_a', None)

        tf = testdir.makepyfile(test_a="""
            def test_add():
                blas
        """, )
        tf.setmtime(1424880937)
        reprec = testdir.inline_run("--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (0, 0, 1), res
        sys.modules.pop('test_a', None)

        tf = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """, )
        tf.setmtime(1424880938)
        reprec = testdir.inline_run("--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (1, 0, 0), res
        sys.modules.pop('test_a', None)

    def test_fantom_failure(self, testdir):
        testdir.makepyfile(test_a="""
            def test_add():
                1/0
        """, )
        testdir.inline_run("--testmon", "-v")

        tf = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """, )
        tf.setmtime(1)
        testdir.inline_run("--testmon", "-v")

        reprec = testdir.inline_run("--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (0, 0, 0), res

    def test_tlf(self, testdir):
        testdir.makepyfile(test_a="""
            def test_add():
                1/0
        """, )
        testdir.inline_run("--testmon", "-v")

        result = testdir.runpytest("--testmon", "-v")
        result.stdout.fnmatch_lines([
            "*1 failed, 1 deselected*",
        ])

        result = testdir.runpytest("--testmon", "-v", "--tlf")
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
        result = testdir.runpytest("--testmon", "--tb=long", "-v")
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
        testdir.runpytest("--testmon")

        tf = testdir.makepyfile(test_a="""
             def test_1():
                 raise KeyboardInterrupt

             def test_2():
                 3
         """)
        os.utime('.testmondata', (1800000000, 1800000000))
        tf.setmtime(1800000000)
        try:
            testdir.runpytest("--testmon", )
        except:
            pass
        assert 1800000000 == os.path.getmtime('.testmondata')  # interrupted run shouldn't save .testmondata

    def test_nonfunc_class(self, testdir, monkeypatch):
        """"
        """
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
        result = testdir.runpytest("--testmon", "test_a.py::TestA::test_one", )
        result.stdout.fnmatch_lines([
            "*1 passed*",
        ])

        testdir.makepyfile(test_a=cs2.source_code)
        test_a.setmtime(1424880935)
        result = testdir.runpytest("-v", "--collectonly", "--testmon")
        result.stdout.fnmatch_lines([
            "*test_one*",
        ])

    def test_strange_argparse_handling(self, testdir):
        """"
        """
        cs1 = CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")

                def test_two(self):
                    print("2")
        """)

        testdir.makepyfile(test_a=cs1.source_code)
        result = testdir.runpytest("-v", "--testmon", "test_a.py::TestA::test_one")
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

        result = testdir.runpytest("-vv", "--collectonly", "--testmon", )
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
        result = testdir.runpytest("--testmon", )
        result.stdout.fnmatch_lines([
            "*5 passed*",
        ])
        result = testdir.runpytest("--testmon")
        result.stdout.fnmatch_lines([
            "*collected 0 items*",
        ])
        a.setmtime(1424880935)
        result = testdir.runpytest("--testmon")
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
        result = testdir.runpytest("--testmon", )
        result.stdout.fnmatch_lines([
            "*5 passed*",
        ])
        result = testdir.runpytest("--testmon")
        result.stdout.fnmatch_lines([
            "*collected 0 items*",
        ])
        a.setmtime(1424880935)
        result = testdir.runpytest("--testmon")
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

        result = testdir.runpytest("--testmon", )
        result.stdout.fnmatch_lines([
            "*1 passed*",
        ])

        a = testdir.makepyfile(a="""
            def add(a, b):
                return a + b + 0
        """)
        a.setmtime(1424880935)
        result = testdir.runpytest("--testmon", )
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
        result = testdir.runpytest("--testmon", )
        result.stdout.fnmatch_lines([
            "*1 skipped*",
        ])

    def test_changed_data_version(self, testdir, monkeypatch):
        testdir.makepyfile(test_pass="""
            def test_pass():
                pass
        """)
        result = testdir.runpytest("--testmon")
        assert result.ret == 0

        # Now change the data version and check py.test then refuses to run
        from testmon.testmon_core import TestmonData
        monkeypatch.setattr(TestmonData, 'DATA_VERSION', TestmonData.DATA_VERSION + 1)

        result = testdir.runpytest("--testmon")
        monkeypatch.setattr(TestmonData, 'DATA_VERSION', TestmonData.DATA_VERSION - 1)
        assert result.ret != 0
        result.stderr.fnmatch_lines([
            "*The stored data file *.testmondata version (2) is not compatible with current version (3).*",
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

        result = testdir.runpytest("--testmon")
        assert result.ret == 0

        testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                pass
                pass
        """)

        result = testdir.runpytest("--testmon")
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

        assert {os.path.relpath(a.strpath, testdir.tmpdir.strpath):
                    checksum_coverage(Module(file_name=a.strpath).blocks, [2])} == deps

    @pytest.mark.xfail
    def test_testmon_recursive(self, testdir, monkeypatch):
        a = testdir.makepyfile(test_a="""\
        def test_1():
            a=1
        """)

        def func():
            testdir.runpytest("test_a.py", "--testmon", "--capture=no")

        deps = track_it(testdir, func)
        # os.environ.pop('COVERAGE_TEST_TRACER', None)

        assert {os.path.abspath(a.strpath):
                    checksum_coverage(Module(file_name=a.strpath).blocks, [2])} == deps

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

        del sys.modules['a']

    def test_report_roundtrip(self, testdir):
        class PlugWrite:
            def pytest_runtest_logreport(self, report):
                global global_reports
                global_reports.append(report)

        class PlugRereport:
            def pytest_runtest_protocol(self, item, nextitem):
                hook = getattr(item.ihook, 'pytest_runtest_logreport')
                for g in global_reports:
                    hook(report=g)
                return True

        testdir.makepyfile("""
        def test_a():
            raise Exception('exception from test_a')
        """)

        testdir.runpytest_inprocess(plugins=[PlugWrite()])

        testdir.makepyfile("""
        def test_a():
            pass
        """)

        result = testdir.runpytest_inprocess(plugins=[PlugRereport()])

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

        result = testdir.runpytest("--testmon")
        assert result.ret == 0

        testdir.makepyfile(test_b="""
            import test_a
            def test_2():
                pass
                pass
        """)

        result = testdir.runpytest("--testmon")
        assert result.ret == 0
        result.stdout.fnmatch_lines(["*1 passed, 1 deselected*", ])

    def test_collection_not_abort(self, testdir):
        testdir.makepyfile(test_collection_not_abort="""
            def test_1():
                1

            def test_2():
                assert False
                """)

        testdir.runpytest("--testmon")

        tf = testdir.makepyfile(test_collection_not_abort="""
            def test_1():
                2

            def test_2():
                assert False
        """)
        tf.setmtime(1)

        result = testdir.runpytest("-v", "--testmon")

        result.stdout.fnmatch_lines(["*test_collection_not_abort.py::test_2 FAILED*", ])


class TestXdist(object):

    def test_xdist_4(self, testdir):
        pytest.importorskip("xdist")
        testdir.makepyfile(test_a="""\
            import pytest
            @pytest.mark.parametrize("a", [
                                    ("test0", ),
                                    ("test1", ),
                                    ("test2", ),
                                    ("test3", )
    ])
            def test_1(a):
                print(a)
            """)

        result = testdir.runpytest("test_a.py", "--testmon", "-n 4", "-v")
        result.stdout.fnmatch_lines([
            "*testmon=True, *",
            "*PASSED test_a.py::test_1[a0*"
        ])


def get_modules(hashes):
    return hashes


if __name__ == '__main__':
    pytest.main()
