import os
from collections import defaultdict
from testmon.process_code import checksum_coverage
from testmon.process_code import Module


class DepGraph(object):

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
        if (nodeid not in self.node_data) or (self.node_data[nodeid] is False):
            # not enough data, means test should run
            return True
        else:
            # TODO This can almost certainly be rewritten in half the lines and double the clarity.
            if set(self.node_data[nodeid]) & set(changed_py_files):
                for changed_file_name, module in changed_py_files.items():
                    checksumes_in_changed_files = set()
                    for block in module.blocks:
                        checksumes_in_changed_files.add(block.checksum)
                    if not set(self.node_data[nodeid].get(changed_file_name,())).issubset(checksumes_in_changed_files):
                        return True
            return False

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

