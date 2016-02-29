import os
import sys

import pytest
from test.coveragepy import coveragetest
from testmon.process_code import Module, checksum_coverage
from testmon.testmon_core import eval_variant
from testmon.testmon_core import Testmon as CoreTestmon
from testmon.testmon_core import TestmonData as CoreTestmonData
from test.test_process_code import CodeSample

pytest_plugins = "pytester",


def test_run_variant_header(testdir):
    testdir.makeini("""
                    [pytest]
                    run_variant_expression='1'
                    """)
    result = testdir.runpytest("-v", "--testmon")
    result.stdout.fnmatch_lines([
        "*testmon=True, *, run variant: 1*",
    ])


def test_run_variant_header_nonstr(testdir):
    testdir.makeini("""
                    [pytest]
                    run_variant_expression=int(1)
                    """)
    result = testdir.runpytest("-v", "--testmon")
    result.stdout.fnmatch_lines([
        "*testmon=True, *, run variant: 1*",
    ])


def test_run_variant_empty(testdir):
    config = testdir.parseconfigure()
    assert eval_variant(config.getini('run_variant_expression')) == ''


def test_run_variant_env(testdir, monkeypatch):
    monkeypatch.setenv('TEST_V', 'JUST_A_TEST')
    testdir.makeini("""
                    [pytest]
                    run_variant_expression=os.environ.get('TEST_V')
                    """)
    config = testdir.parseconfigure()
    assert eval_variant(config.getini('run_variant_expression')) == 'JUST_A_TEST'

def test_run_variant_nonsense(testdir):
    testdir.makeini("""
                    [pytest]
                    run_variant_expression=nonsense
                    """)
    config = testdir.parseconfigure()
    assert 'NameError' in eval_variant(config.getini('run_variant_expression'))

def test_run_variant_complex(testdir, monkeypatch):
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
    testmon.start()
    func()
    testmon.stop_and_save(testmon_data, testdir.tmpdir.strpath, 'testnode')
    return testmon_data.node_data['testnode']


def test_subprocesss(testdir, monkeypatch):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
    a = testdir.makepyfile(test_a="""\
    def test_1():
        a=1
    """)
    def func():
        testdir.runpytest("test_a.py")

    deps = track_it(testdir, func)

    assert {os.path.abspath(a.strpath):
                checksum_coverage(Module(file_name=a.strpath).blocks, [2])} == deps

@pytest.mark.xfail
def test_subprocess_recursive(testdir, monkeypatch):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
    #os.environ['COVERAGE_TEST_TRACER']='py'
    a = testdir.makepyfile(test_a="""\
    def test_1():
        a=1
    """)
    def func():
        testdir.runpytest("test_a.py", "--testmon", "--capture=no")

    deps = track_it(testdir, func)
    #os.environ.pop('COVERAGE_TEST_TRACER', None)

    assert {os.path.abspath(a.strpath):
                checksum_coverage(Module(file_name=a.strpath).blocks, [2])} == deps


def test_run_dissapearing(testdir):
    testdir.makeini("""
                [pytest]
                run_variants=1
                """)

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

    deps=track_it(testdir, f)
    assert a.strpath in deps
    assert len(deps) == 1

    del sys.modules['a']

class TestmonDeselect(object):

    def test_dont_readcoveragerc(self, testdir, monkeypatch):
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
        p = testdir.tmpdir.join('.coveragerc')
        p.write("[")
        testdir.makepyfile(test_a="""
            def test_add():
                pass
        """)
        testdir.inline_run(["--testmon", ])

    def test_not_running_after_failure(self, testdir, monkeypatch):
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
        pass
        tf = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """,)
        reprec = testdir.inline_run( "--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (1, 0, 0), res
        sys.modules.pop('test_a', None)

        tf = testdir.makepyfile(test_a="""
            def test_add():
                1/0
        """,)
        tf.setmtime(1424880936)
        reprec = testdir.inline_run( "--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (0, 0, 1), res
        sys.modules.pop('test_a', None)

        tf = testdir.makepyfile(test_a="""
            def test_add():
                blas
        """,)
        tf.setmtime(1424880937)
        reprec = testdir.inline_run( "--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (0, 0, 1), res
        sys.modules.pop('test_a', None)

        tf = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """,)
        tf.setmtime(1424880938)
        reprec = testdir.inline_run( "--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (1, 0, 0), res
        sys.modules.pop('test_a', None)

    def test_easy(self, testdir, monkeypatch):
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
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

    def test_easy_by_block(self, testdir, monkeypatch):
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
        test_a = """
            def test_add():
                assert add(1, 2) == 3

            def add(a, b):
                return a + b
        """
        testdir.makepyfile(test_a=test_a)
        Module(source_code=test_a, file_name='test_a')
        result = testdir.runpytest("--testmon", "--tb=long", "-v")

        result.stdout.fnmatch_lines([
            "*test_a.py::test_add PASSED*",
        ])

    def test_nonfunc_class(self, testdir, monkeypatch):
        """"
        """
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
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
        result = testdir.runpytest("--testmon", "test_a.py::TestA::test_one",)
        result.stdout.fnmatch_lines([
            "*1 passed*",
        ])

        testdir.makepyfile(test_a=cs2.source_code)
        test_a.setmtime(1424880935)
        result = testdir.runpytest("-v", "--collectonly", "--testmon", "--capture=no",)
        result.stdout.fnmatch_lines([
            "*test_one*",
        ])

    def test_strange_argparse_handling(self, testdir, monkeypatch):
        """"
        """
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
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

        result = testdir.runpytest("-vv", "--collectonly", "--testmon",)
        result.stdout.fnmatch_lines([
            "*test_one*",
        ])


    def test_new(self, testdir, monkeypatch):
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
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
        result = testdir.runpytest("--testmon",)
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


def get_modules(hashes):
    return hashes


if __name__ == '__main__':
    pytest.main()
