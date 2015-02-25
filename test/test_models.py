import pytest
from testmon.testmon_models import Block, Module

class TestHashCoverage(object):

    def test_miss_before(self):
        assert hash_coverage([Block(2, 3, 101)], [1]) == []
        
    def test_hit_first(self):
        assert hash_coverage([Block(2, 3, 102)], [2]) == [102]
    
    def test_hit_first2(self):
        assert hash_coverage([Block(2, 3, 102), Block(6, 7, 103)], [2]) == [102]
    
    def test_miss_after(self):
        assert hash_coverage([Block(1, 2, 103)], [3]) == []
        
    def test_hit_second(self):
        assert hash_coverage([Block(2, 3, 101), Block(5, 6, 102)], [5]) == [102]
        
    def test_hit_second_twice(self):
        assert hash_coverage([Block(2, 3, 101), Block(4, 7, 102)], [5, 6]) == [102]
  
    @pytest.mark.parametrize("lines", [[3, 5], [5, 3]])      
    def test_hit_both(self, lines):
        assert hash_coverage([Block(2, 3, 101), Block(5, 6, 102)], lines) == [101, 102]

    @pytest.mark.parametrize("lines", [[4, 7], [7, 4]])      
    def test_miss_both(self, lines):
        assert hash_coverage([Block(2, 3, 101), Block(5, 6, 102)], lines) == []    
        
class TestModule(object):
    
    def test_base_diff(self):
        module1 = Module('test/astfixture.py')
        module2 = Module('test/astfixture2.py')
        
        blocks1 = module1.blocks
        blocks2 = module2.blocks
        assert (blocks1[0], blocks1[1], blocks2[3]) == (blocks2[0], blocks2[1], blocks2[3])
        assert blocks1[2] != blocks2[2]
    
def hash_coverage(blocks, lines):
    result = []
    line_index = 0
    lines.sort()

    for current_block in blocks:
        try:
            while lines[line_index] < current_block.start:
                line_index += 1
            if lines[line_index] <= current_block.end:
                result.append(current_block.hash)
        except IndexError:
            break
    
    return result

# classy: Module(path, mtime, main, [Blocks])
# ModuleCollection = [Module, Module, Module]
#last_state=ModuleCollection, new_state=ModuleCollection(), changes=ModuleCollection()
# DepGraph {for all nodeid: dependencies [ModuleCollection] intersect changes } or
#dependencies - new_state <> []

#new_dependencies = track_executable(nodeid)


