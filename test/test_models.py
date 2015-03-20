import pytest
from testmon.testmon_models import Block, Module, hash_coverage

global_block = Block(-1, 0, 1000)


class TestHashCoverage(object):


    def test_miss_before(self):
        assert hash_coverage([global_block, Block(2, 3, 101)], [1]) == [1000, ]
        
    def test_hit_first(self):
        assert hash_coverage([global_block, Block(2, 3, 102)], [2]) == [1000, 102]
    
    def test_hit_first2(self):
        assert hash_coverage([global_block, Block(2, 3, 102), Block(6, 7, 103)], [2]) == [1000, 102]
    
    def test_miss_after(self):
        assert hash_coverage([global_block, Block(1, 2, 103)], [3]) == [1000, ]
        
    def test_hit_second(self):
        assert hash_coverage([global_block, Block(2, 3, 101), Block(5, 6, 102)], [5]) == [1000, 102]
        
    def test_hit_second_twice(self):
        assert hash_coverage([global_block, Block(2, 3, 101), Block(4, 7, 102)], [5, 6]) == [1000, 102]
  
    @pytest.mark.parametrize("lines", [[3, 5], [5, 3]])      
    def test_hit_both(self, lines):
        assert hash_coverage([global_block, Block(2, 3, 101), Block(5, 6, 102)], lines) == [1000, 101, 102]

    @pytest.mark.parametrize("lines", [[4, 7], [7, 4]])      
    def test_miss_both(self, lines):
        assert hash_coverage([global_block, Block(2, 3, 101), Block(5, 6, 102)], lines) == [1000, ]    


MODS_COVS = {
    1: ("""
        def add(a, b):
            return a + b
    
        assert add(1, 2) == 3
            """,
            {2: None, 3: None, 5: None}),
 
    2: ("""
        def add(a, b):
            return a + b
            
        def subtract(a, b):
            return a - b

        assert add(1, 3) == 4
            """,
            {2: None, 3: None, 5: None, 8: None})
}
    
class TestModule(object):
    
    def test_base_diff(self):
        module1 = Module(filename='test/astfixture.py')
        module2 = Module(filename='test/astfixture2.py')
        
        blocks1 = module1.blocks
        blocks2 = module2.blocks
        assert (blocks1[0], blocks1[1], blocks2[3]) == (blocks2[0], blocks2[1], blocks2[3])
        assert blocks1[2] != blocks2[2]
    

    def test_covdata_intersects_deps(self):
        module1 = Module(MODS_COVS[1][0], 'a.py')
        covdata = MODS_COVS[1][1]
        
        print module1.blocks
        assert hash_coverage(module1.blocks, covdata.keys()) == [6093239351826790794, -256290574503913225]


        module1 = Module(MODS_COVS[2][0], 'a.py')
        covdata = MODS_COVS[2][1]
        
        print module1.blocks
        assert hash_coverage(module1.blocks, covdata.keys()) == [2750655356717219630, -256290574503913225]

# classy: Module(path, mtime, main, [Blocks])
# ModuleCollection = [Module, Module, Module]
#last_state=ModuleCollection, new_state=ModuleCollection(), changes=ModuleCollection()
# DepGraph {for all nodeid: dependencies [ModuleCollection] intersect changes } or
#dependencies - new_state <> []

#new_dependencies = track_executable(nodeid)
