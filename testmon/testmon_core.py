try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import gzip
import json
import os
from collections import defaultdict
import sys
import textwrap
import random

import coverage
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


def affected_nodeids(nodes, changes):
    affected = []
    for filename in changes:
        for nodeid, node in nodes.items():
            if filename in node:
                new_checksums = set(changes[filename])
                if set(node[filename]) - new_checksums:
                    affected.append(nodeid)
    return affected


class Testmon(object):

    def __init__(self, project_dirs, testmon_labels=set(), variant=None):

        self.variant = variant if variant else 'default'

        self.alldata = {}
        self.mtimes = {}
        self.node_data = {}
        self.modules_cache = {}
        self.project_dirs = project_dirs
        self.lastfailed = []
        self.testmon_labels = testmon_labels

        self.setup_coverage(not('singleprocess' in testmon_labels))

    def read_data(self):
        try:
            with gzip.GzipFile(os.path.join(self.project_dirs[0], ".testmondata"), "r") as f:
                self.alldata = json.loads(f.read().decode('UTF-8'))
                if self.variant in self.alldata:
                    self.mtimes, self.node_data, self.lastfailed = self.alldata[self.variant]
        except IOError:
            self.alldata = {}

    def setup_coverage(self, subprocess):

        includes = [os.path.join(path, '*') for path in self.project_dirs]
        if subprocess:
            if not os.path.exists('.tmontmp'):
                os.makedirs('.tmontmp')

            self.sub_cov_file = os.path.abspath('.tmontmp/.testmoncoverage' + str(random.randint(0, 1000000)))
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

    def parse_cache(self, module):
        if module not in self.modules_cache:
            self.modules_cache[module] = Module(file_name=module)
            self.mtimes[module] = os.path.getmtime(module)

        return self.modules_cache[module]

    def read_fs(self):
        """

        """
        self.read_data()
        self.old_mtimes = self.mtimes.copy()
        for py_file in self.modules_test_counts():
            try:
                current_mtime = os.path.getmtime(py_file)
                if self.mtimes.get(py_file) != current_mtime:
                    self.parse_cache(py_file)

            except OSError:
                self.mtimes[py_file] = [-2]

        self.affected = affected_nodeids(self.node_data,
                                         {filename: module.checksums for filename, module in
                                          self.modules_cache.items()})


## possible data structures
## nodeid1 -> [filename -> [block_a, block_b]]
## filename -> [block_a -> [nodeid1, ], block_b -> [nodeid1], block_c -> [] ]


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
        return is_dependent(node, {filename: module.checksums
                                   for filename, module
                                   in self.modules_cache.items()})

    def modules_test_counts(self):
        test_counts = defaultdict(lambda: 0)
        for files in self.node_data.values():
            for module in files:
                test_counts[module] += 1
        return test_counts

    def set_dependencies(self, nodeid, coverage_data):
        result = {}
        for filename, value in coverage_data.lines.items():
            if os.path.exists(filename):
                result[filename] = checksum_coverage(self.parse_cache(filename).blocks, value.keys())
        self.node_data[nodeid] = result


    def track_dependencies(self, callable_to_track, nodeid):
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


    def save(self):
        if 'readonly' not in self.testmon_labels:
            with gzip.GzipFile(os.path.join(self.project_dirs[0], ".testmondata"), "w", 1) as f:
                self.alldata[self.variant] = (self.mtimes,
                                              self.node_data,
                                              self.lastfailed)
                f.write(json.dumps(self.alldata).encode('UTF-8'))


    def close(self):
        if hasattr(self, 'sub_cov_file'):
            os.remove(self.sub_cov_file + "_rc")


def eval_variants(run_variants):
    eval_locals = {'os': os, 'sys': sys}

    eval_values = []
    for var in run_variants:
        try:
            eval_values.append(eval(var, {}, eval_locals))
        except Exception as e:
            eval_values.append(repr(e))

    return ":".join([str(value) for value in eval_values if value])


def get_variant_inifile(inifile):
    config = configparser.ConfigParser()
    config.read(str(inifile),)
    if config.has_section('pytest') and config.has_option('pytest', 'run_variants'):
        run_variants = config.get('pytest', 'run_variants').split('\n')
    else:
        run_variants = []

    return eval_variants(run_variants)