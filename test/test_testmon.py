import os

import pytest
from testmon.process_code import Module, Block
from testmon.testmon_core import Testmon, is_dependent
from test.test_process_code import CodeSample
from testmon.pytest_testmon import TESTS_CACHE_KEY, get_variant
import sys


pytest_plugins = "pytester",


def test_run_variant_header(testdir):
    testdir.makeini("""
                    [pytest]
                    run_variants=1
                    """)
    result = testdir.runpytest("-v")
    result.stdout.fnmatch_lines([
        "*Run variant: 1*",
    ])


def test_run_variant_empty(testdir):
    config = testdir.parseconfigure()
    assert get_variant(config) == ''


def test_run_variant_env(testdir):
    test_v_before = os.environ.get('TEST_V')
    os.environ['TEST_V'] = 'JUST_A_TEST'
    testdir.makeini("""
                    [pytest]
                    run_variants=os.environ.get('TEST_V')
                                 None # What evaluates to false is no included
                    """)
    config = testdir.parseconfigure()
    assert get_variant(config) == 'JUST_A_TEST'
    del os.environ['TEST_V']
    if test_v_before is not None:
        os.environ['TEST_V']

def test_run_variant_nonsense(testdir):
    testdir.makeini("""
                    [pytest]
                    run_variants=nonsense
                    """)
    config = testdir.parseconfigure()
    assert 'NameError' in get_variant(config)


class TestmonDeselect(object):

    def test_dont_readcoveragerc(self, testdir, monkeypatch):
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
        p = testdir.tmpdir.join('.coveragerc')
        p.write("[")
        a = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """)
        testdir.inprocess_run(["--testmon", ])

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
        del sys.modules['test_a']

        tf = testdir.makepyfile(test_a="""
            def test_add():
                1/0
        """,)
        tf.setmtime(1424880936)
        reprec = testdir.inline_run( "--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (0, 0, 1), res
        del sys.modules['test_a']

        tf = testdir.makepyfile(test_a="""
            def test_add():
                blas
        """,)
        tf.setmtime(1424880937)
        reprec = testdir.inline_run( "--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (0, 0, 1), res
        del sys.modules['test_a']

        tf = testdir.makepyfile(test_a="""
            def test_add():
                pass
        """,)
        tf.setmtime(1424880938)
        reprec = testdir.inline_run( "--testmon", "-v")
        res = reprec.countoutcomes()
        assert tuple(res) == (1, 0, 0), res


    def test_easy(self, testdir, monkeypatch):
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
        a = testdir.makepyfile(test_a="""
            def test_add():
                assert add(1, 2) == 3

            def add(a, b):
                return a + b
        """)
        result = testdir.runpytest("--testmon", "--tb=long", "-v")
        from testmon.pytest_testmon import MTIMES_CACHE_KEY

        config = testdir.parseconfigure()
        node_data = config.cache.get(TESTS_CACHE_KEY, {})
        mtimes = config.cache.get(MTIMES_CACHE_KEY, {})
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
        a = testdir.makepyfile(test_a=test_a)
        Module(source_code=test_a, file_name='test_a')
        result = testdir.runpytest("--testmon", "--tb=long", "-v")
        from testmon.pytest_testmon import TESTS_CACHE_KEY, MTIMES_CACHE_KEY

        config = testdir.parseconfigure()
        node_data = config.cache.get(TESTS_CACHE_KEY, {})
        mtimes = config.cache.get(MTIMES_CACHE_KEY, {})
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
        module2 = Module(cs2.source_code)

        test_a = testdir.makepyfile(test_a=cs1.source_code)
        result = testdir.runpytest("--testmon", "test_a.py::TestA::test_one")
        result.stdout.fnmatch_lines([
            "*1 passed*",
        ])

        testdir.makepyfile(test_a=cs2.source_code)
        test_a.setmtime(1424880935)
        result = testdir.runpytest("-v", "--collectonly", "--testmon", "--capture=no")
        result.stdout.fnmatch_lines([
            "*test_one*",
        ])

    def test_nonfunc_class_2(self, testdir):
        config = testdir.parseconfigure()
        cs2 = CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")
            
                def test_twob(self):
                    print("2")
        """)
        testdir.makepyfile(test_a=cs2.source_code)

        result = testdir.runpytest("-vv", "--collectonly", "--testmon")
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

        b = testdir.makepyfile(b="""
            def divide(a, b):
                return a // b
            
            def multiply(a, b):
                return a * b
        """)

        test_a = testdir.makepyfile(test_a=""" 
            from a import add, subtract
            import time
            
            def test_add():
                assert add(1, 2) == 3
            
            def test_subtract():
                assert subtract(1, 2) == -1
                    """)

        test_a = testdir.makepyfile(test_b="""
            import unittest
            
            from b import multiply, divide
            
            class TestB(unittest.TestCase):
                def test_multiply(self):
                    self.assertEqual(multiply(1, 2), 2)
            
                def test_divide(self):
                    self.assertEqual(divide(1, 2), 0)
        """)

        test_ab = testdir.makepyfile(test_ab=""" 
            from a import add
            from b import multiply
            def test_add_and_multiply():
                assert add(2, 3) == 5
                assert multiply(2, 3) == 6
        """)
        result = testdir.runpytest("--testmon")
        result.stdout.fnmatch_lines([
            "*5 passed*",
        ])
        result = testdir.runpytest("--testmon")
        result.stdout.fnmatch_lines([
            "*5 deselected*",
        ])
        a.setmtime(1424880935)
        result = testdir.runpytest("--testmon")
        result.stdout.fnmatch_lines([
            "*5 deselected*",
        ])


def get_modules(hashes):
    return hashes


class TestDepGraph():
    def test_dep_graph1(self):
        assert is_dependent({'a.py': [101, 102]}, {'a.py': [101, 102, 3]}) == False

    def test_dep_graph_new(self):
        assert is_dependent({'a.py': [101, 102]}, {'new.py': get_modules([101, 102, 3]),
                                                   'a.py': get_modules([101, 102, 3])}) == False

    def test_dep_graph2(self):
        assert is_dependent({'a.py': [101, 102]}, {'a.py': get_modules([101, 102])}) == False

    def test_dep_graph3(self):
        assert is_dependent({'a.py': [101, 102]}, {'a.py': get_modules([101, 102, 103])}) == False

    def test_dep_graph4(self):
        assert is_dependent({'a.py': [101, 102]}, {'a.py': get_modules([101, 103])}) == True

    def test_dep_graph_two_modules(self):
        changed_py_files = {'b.py': get_modules([])}
        assert is_dependent({'a.py': [101, 102]}, changed_py_files) == False
        assert is_dependent({'b.py': [103, 104]}, changed_py_files) == True

    def test_two_modules_combination(self):
        changed_py_files = {'b.py': get_modules([])}
        assert is_dependent( {'a.py': [101, 102]}, changed_py_files) == False
        assert is_dependent({'a.py': [105, 106], 'b.py': [107, 108]}, changed_py_files) == True

    def test_two_modules_combination2(self):
        changed_py_files = {'b.py': get_modules([103, 104])}
        assert is_dependent({'a.py': [101, 102]}, changed_py_files) == False
        assert is_dependent({'a.py': [101], 'b.py': [107]}, changed_py_files) == True

    def test_two_modules_combination3(self):
        changed_py_files = {'b.py': get_modules([103, 104])}
        assert is_dependent('test_1', changed_py_files) == False
        assert is_dependent('test_both', changed_py_files) == False

    def test_classes_depggraph(self):
        module1 = Module(CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")
            
                def test_two(self):
                    print("2")
        """).source_code)
        bs1 = module1.blocks

        module2 = Module(CodeSample("""\
            class TestA(object):
                def test_one(self):
                    print("1")
            
                def test_twob(self):
                    print("2")
        """).source_code)
        bs2 = module2.blocks

        assert bs1[0] == bs2[0]
        assert bs1[1] != bs2[1]
        assert bs1[2] != bs2[2]

        assert len(module1.blocks) == len(module2.blocks) == 3
        assert (bs1[1].start,
                bs1[1].end,
                bs1[1].checksum) == (bs2[1].start,
                                     bs2[1].end,
                                     bs2[1].checksum)
        assert (bs1[1].name) != (bs2[1].name)


        assert is_dependent({'test_s.py': [bs1[0].checksum, bs1[2].checksum]}, {'test_s.py': [b.checksum for b in bs2]}) == True
        assert is_dependent({'test_s.py': [bs1[1].checksum, bs1[2].checksum]}, {'test_s.py': [b.checksum for b in bs2]}) == True


if __name__ == '__main__':
    pytest.main()
