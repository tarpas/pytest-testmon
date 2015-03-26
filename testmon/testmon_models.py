import os
from collections import defaultdict

from testmon.process_code import checksum_coverage
from testmon.process_code import Module


class DepGraph(object):
    """
    each node is a dict of lists, first level is file names, second level is is checksums of the blocks inside the
    file on which the node depends. self.node_data is a dict of nodes.
    """

    def __init__(self, node_data):
        self.node_data = node_data
        self.modules_cache = {}

    def repr_per_node(self, key):
        return "{}: {}\n".format(key,
                                 [(os.path.relpath(p), checksum)
                                  for (p, checksum)
                                  in self.node_data[key].items()])

    def __repr__(self):
        return "\n".join((self.repr_per_node(nodeid) for nodeid in self.node_data))

    def test_should_run(self, nodeid, changed_py_files):
        """
        See test_testmon::TestDepGraph to understand.
        """
        node = self.node_data.get(nodeid)
        if node:
            for changed_file_name in set(node) & set(changed_py_files):
                new_checksums = set([block.checksum
                                     for block
                                     in changed_py_files[changed_file_name].blocks])
                if set(node[changed_file_name]) - new_checksums:
                    return True
            return False
        else:
            # not enough data, means test should run
            return True

    def modules_test_counts(self):
        test_counts = defaultdict(lambda: 0)
        for _, node in self.node_data.items():
            for module in node:
                test_counts[module] += 1
        return test_counts

    def set_dependencies(self, nodeid, coverage_data):
        result = {}
        for filename, value in coverage_data.lines.items():
            if filename not in self.modules_cache:
                self.modules_cache[filename] = Module(file_name=filename).blocks
            result[filename] = checksum_coverage(self.modules_cache[filename], value.keys())
        self.node_data[nodeid] = result

