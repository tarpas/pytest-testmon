import os
import pytest
import shutil
import py
from testmon.process_code import Module, Block 
from testmon.testmon_models import DepGraph
from test_process_code import code_samples, CodeSample
from testmon.plugin import TESTS_CACHE_KEY

pytest_plugins = "pytester",

def test_cache_reportheader(testdir):
    p = testdir.makepyfile("""
        def test_hello():
            pass
    """)
    cachedir = p.dirpath(".cache")
    result = testdir.runpytest("-v")
    result.stdout.fnmatch_lines([
        "*Thanks Indiegogo contributors, stay tuned for more!*",
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
        from testmon.plugin import TESTS_CACHE_KEY, MTIMES_CACHE_KEY
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
        from testmon.plugin import DepGraph, TESTS_CACHE_KEY, MTIMES_CACHE_KEY
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
        cs1 = CodeSample("""
            class TestA(object):
                def test_one(self):
                    print "1"
            
                def test_two(self):
                    print "2"
        """)
                
        cs2 = CodeSample("""
            class TestA(object):
                def test_one(self):
                    print "1"
            
                def test_twob(self):
                    print "2"
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
        cs2 = CodeSample("""
            class TestA(object):
                def test_one(self):
                    print "1"
            
                def test_twob(self):
                    print "2"
        """)
        module2 = Module(cs2.source_code)
        test_a = testdir.makepyfile(test_a=cs2.source_code)

        dep_graph = DepGraph({'test_a.py::TestA::()::test_one': {test_a.strpath: [1718898506, 2057111600]}})
        assert dep_graph.test_should_run('test_a.py::TestA::()::test_one', { test_a.strpath: module2 }) == True
        config.cache.set(TESTS_CACHE_KEY, dep_graph.node_data)
        result = testdir.runpytest("-vv", "--collectonly", "--testmon" )
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
    m1 = Module("print 1","a.py")
    m1.blocks = [Block(-1, 0, hass) for hass in hashes]
    return m1


class TestDepGraph():
    
    def test_dep_graph1(self):       
        dg = DepGraph({ 'a.py::test_1': {'a.py' : [101, 102]}})
        assert dg.test_should_run('a.py::test_1', {'a.py': get_modules([101, 102, 3])}) == False

    def test_dep_graph_new(self):       
        dg = DepGraph({ 'a.py::test_1': {'a.py' : [101, 102]}})
        assert dg.test_should_run('a.py::test_1', {'new.py': get_modules([101, 102, 3]), 
                                                   'a.py': get_modules([101, 102, 3])}) == False
        
    def test_dep_graph2(self):
        dg = DepGraph({ 'a.py::test_1': {'a.py' : [101, 102]}})
        assert dg.test_should_run('a.py::test_1', {'a.py': get_modules([101, 102])}) == False

    def test_dep_graph3(self):
        dep_graph = DepGraph({ 'a.py::test_1': {'a.py' : [101, 102]}})
        assert dep_graph.test_should_run('a.py::test_1', {'a.py': get_modules([101, 102, 103])}) == False

    def test_dep_graph4(self):
        dep_graph = DepGraph({ 'a.py::test_1': {'a.py' : [101, 102]}})
        assert dep_graph.test_should_run('a.py::test_1', {'a.py': get_modules([101, 103])}) == True

    def test_dep_graph_two_modules(self):
        dep_graph = DepGraph({ 'test_1': {'a.py': [101, 102]}, 'test_2': { 'b.py': [103, 104]}})
        changed_py_files = {'b.py' : get_modules([]) }
        assert dep_graph.test_should_run('test_1', changed_py_files) == False
        assert dep_graph.test_should_run('test_2', changed_py_files) == True

    def test_two_modules_combination(self):
        dep_graph = DepGraph({'test_1': {'a.py': [101, 102]},
                              'test_2': { 'b.py': [103, 104]},
                              'test_both': {'a.py' : [105, 106], 'b.py': [107, 108] }})
        changed_py_files = {'b.py' : get_modules([]) }
        assert dep_graph.test_should_run('test_1', changed_py_files) == False
        assert dep_graph.test_should_run('test_both', changed_py_files) == True

    def test_two_modules_combination2(self):
        dep_graph = DepGraph({'test_1': {'a.py': [101, 102]},
                              'test_2': { 'b.py': [103, 104]},
                              'test_both': {'a.py' : [101], 'b.py': [107] }})
        changed_py_files = {'b.py' : get_modules([103, 104]) }
        assert dep_graph.test_should_run('test_1', changed_py_files) == False
        assert dep_graph.test_should_run('test_both', changed_py_files) == True

    def test_two_modules_combination3(self):
        dep_graph = DepGraph({ 'test_1': {'a.py': [101, 102]},
                               'test_2': { 'b.py': [103, 104]},
                               'test_both': {'a.py' : [101], 'b.py': [103] }})
        changed_py_files = {'b.py' : get_modules([103, 104]) }
        assert dep_graph.test_should_run('test_1', changed_py_files) == False
        assert dep_graph.test_should_run('test_both', changed_py_files) == False

    def test_classes_depggraph(self):        
        module1 = Module(CodeSample("""
            class TestA(object):
                def test_one(self):
                    print "1"
            
                def test_two(self):
                    print "2"
        """).source_code)
        bs1=module1.blocks
        
        
        module2 = Module(CodeSample("""
            class TestA(object):
                def test_one(self):
                    print "1"
            
                def test_twob(self):
                    print "2"
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

        dep_graph = DepGraph({'test_s.py::TestA::test_one': {'test_s.py': [bs1[0].checksum, bs1[2].checksum]},
                              'test_s.py::TestA::test_two': {'test_s.py': [bs1[1].checksum, bs1[2].checksum]}})
        
        assert dep_graph.test_should_run('test_s.py::TestA::test_one', {'test_s.py': module2 }) == True
        assert dep_graph.test_should_run('test_s.py::TestA::test_twob', {'test_s.py': module2 }) == True
        
        
if __name__ == '__main__':
    pytest.main()
