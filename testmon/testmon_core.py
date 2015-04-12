import os
from collections import defaultdict
import sys
import textwrap
import coverage
import random

from testmon.process_code import checksum_coverage
from testmon.process_code import Module


def _get_python_lib_paths():
    res = [sys.prefix]
    for attr in ['exec_prefix', 'real_prefix', 'base_prefix']:
        if getattr(sys, attr, sys.prefix) not in res:
            res.append(getattr(sys, attr))
    return [os.path.join(d, "*") for d in res]


def is_dependent(node, changed_py_files):
    if node:
        for changed_file_name in set(node) & set(changed_py_files):
            new_checksums = set(changed_py_files[changed_file_name])
            if set(node[changed_file_name]) - new_checksums:
                return True
        return False
    else:
        # not enough data, means test should run
        return True



class Testmon(object):

    def setup_coverage(self, includes, subprocess):

        if subprocess:
            if not os.path.exists('.tmonsub'):
                os.makedirs('.tmonsub')

            self.sub_cov_file = os.path.abspath('.tmonsub/.testmoncoverage' + str(random.randint(0, 1000000)))
            with open(self.sub_cov_file + "_rc", "w") as subprocess_rc:
                rc_content = textwrap.dedent("""\
                    [run]
                    data_file = {}
                    include = {}
                    omit = {}
                    parallel=True
                    """).format(self.sub_cov_file,
                                "\n ".join(includes),
                                "\n ".join(_get_python_lib_paths())
                                )
                subprocess_rc.write(rc_content)
            os.environ['COVERAGE_PROCESS_START'] = self.sub_cov_file + "_rc"

        self.cov = coverage.coverage(include=includes,
                                     omit=_get_python_lib_paths(),
                                     data_file=getattr(self, 'sub_cov_file', None),
                                     config_file=False, )
        self.cov.use_cache(False)

    def __init__(self, node_data, project_dirs, testmon="yes", variant=None):
        self.modules_cache = {}

        self.node_data = node_data
        self.mtimes = {}
        self.variant = variant

        includes = [os.path.join(path, '*') for path in project_dirs]

        self.setup_coverage(includes, subprocess=testmon == 'subprocess')

    def parse_cache(self, module):
        if module not in self.modules_cache:
                        self.modules_cache[module] = Module(file_name=module).blocks
                        self.mtimes[module] = os.path.getmtime(module)
        return self.modules_cache[module]

    def read_fs(self, mtimes):
        """

        """
        self.mtimes = mtimes
        for py_file in self.modules_test_counts():
            try:
                current_mtime = os.path.getmtime(py_file)
                if self.mtimes.get(py_file) != current_mtime:
                    self.parse_cache(py_file)

            except OSError:
                self.mtimes[py_file] = [-2]

    def repr_per_node(self, key):
        return "{}: {}\n".format(key,
                                 [(os.path.relpath(p), checksum)
                                  for (p, checksum)
                                  in self.node_data[key].items()])

    def __repr__(self):
        return "\n".join((self.repr_per_node(nodeid) for nodeid in self.node_data))

    def test_should_run(self, nodeid):
        """
        TODO
        """
        node = self.node_data.get(nodeid)
        return is_dependent(node, {filename: [block.checksum for block in blocks]
                                  for filename, blocks
                                  in self.modules_cache.items()})

    def modules_test_counts(self):
        test_counts = defaultdict(lambda: 0)
        for _, node in self.node_data.items():
            for module in node:
                test_counts[module] += 1
        return test_counts

    def set_dependencies(self, nodeid, coverage_data):
        result = {}
        for filename, value in coverage_data.lines.items():
            result[filename] = checksum_coverage(self.parse_cache(filename), value.keys())
        self.node_data[nodeid] = result

    def track_execute(self, callable_to_track, nodeid):
        self.cov.erase()
        self.cov.start()
        try:
            result = callable_to_track()
        except:
            raise
        finally:
            self.cov.stop()
            self.cov.save()
            if hasattr(self, 'sub_cov_file'):
                self.cov.combine()

            self.set_dependencies(nodeid, self.cov.data)

            if not self.cov.data:
                # TODO warning with chance of beeing propagated to the user
                print("Warning: tracing of %s failed!" % nodeid)
        return result

    def close(self):
        if hasattr(self, 'sub_cov_file'):
            os.remove(self.sub_cov_file + "_rc")

