import os
import pytest
import shutil
import py

pytest_plugins = "pytester",

def test_cache_reportheader(testdir):
    p = testdir.makepyfile("""
        def test_hello():
            pass
    """)
    cachedir = p.dirpath(".cache")
    result = testdir.runpytest("-v")
    result.stdout.fnmatch_lines([
        "*igg.me/at/testmon*",
    ])

class TestmonDeselect(object):
    
    def test_easy(self, testdir, monkeypatch):
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", 1)
        a = testdir.makepyfile(test_a="""
            def test_add():
                assert add(1, 2) == 3

            def add(a, b):
                return a + b
        """)
        result = testdir.runpytest("--testmon", "--tb=long", "-v")
        from testmon.plugin import DepGraph, TESTS_CACHE_KEY, MTIMES_CACHE_KEY
        config = testdir.parseconfigure()
        node_data = config.cache.get(TESTS_CACHE_KEY, {})
        mtimes = config.cache.get(MTIMES_CACHE_KEY, {})
        print(repr(DepGraph(node_data=node_data)))

        result.stdout.fnmatch_lines([
            "*1 passed*",
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
        from testmon.plugin import DepGraph, TESTS_CACHE_KEY, MTIMES_CACHE_KEY
        config = testdir.parseconfigure()
        node_data = config.cache.get(TESTS_CACHE_KEY, {})
        print(repr(DepGraph(node_data=node_data, 
                            )))
        a.setmtime(1424880935)
        result = testdir.runpytest("--testmon")
        result.stdout.fnmatch_lines([
            "test_a.py ..",
            "test_ab.py .",
            "*3 passed*2 deselected*",
        ])
        

class TestDepGraph():
    
    def test_gep_graph(self):
        node_data = { 'test_a.py::test_add': ['test_a.py']}
        
if __name__ == '__main__':
    pytest.main()
