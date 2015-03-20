import sys
import coverage
import os
from tests.coveragetest import CoverageTest
from testmon.plugin import track_execute
from test_models import MODS_COVS

class TestCoverageAssumptions(CoverageTest):
        
    def setUp(self):
        super(TestCoverageAssumptions, self).setUp()
        self.cov = coverage.coverage(cover_pylib=False)
        self.cov.use_cache(False)

    def test_easy(self):

        for mod_cov in MODS_COVS.values(): 
            modname = self.get_module_name()
            self.make_file(modname+".py", mod_cov[0])
    
            def callit():
                self.import_local_file(modname)
    
            result, cov_data = track_execute(callit, self.cov)
    
            # Clean up our side effects
            del sys.modules[modname]
    
            filename = os.path.abspath(modname + '.py')
            assert cov_data.lines[filename] == mod_cov[1], "for hey hou %s" % str(mod_cov)
        