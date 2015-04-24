from _pytest.config import get_common_ancestor, getcfg
import sys
from testmon.testmon_core import get_variant_inifile, Testmon


ancestor = get_common_ancestor(sys.argv[1:])
rootdir, inifile, inicfg = getcfg(
    [ancestor], ["pytest.ini", "tox.ini", "setup.cfg"])
if rootdir is None:
    for rootdir in ancestor.parts(reverse=True):
        if rootdir.join("setup.py").exists():
            break
    else:
        rootdir = ancestor

variant = get_variant_inifile(inifile)

testmon = Testmon([str(rootdir)], variant=variant )
testmon.read_fs()


node_files = testmon.modules_test_counts().keys()

changed_files = []
for node_file in node_files:
    if testmon.old_mtimes.get(node_file) != testmon.mtimes.get(node_file):
        changed_files.append(node_file)
print "Changed files:%s " % changed_files

print rootdir, inifile, inicfg



#print  ccc
