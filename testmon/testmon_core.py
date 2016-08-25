import zlib

try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import hashlib
import json
import os
from collections import defaultdict
import sys
import textwrap
import random

import coverage
from testmon.process_code import checksum_coverage
from testmon.process_code import Module

if sys.version_info > (3,):
    buffer = memoryview

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

    def __init__(self, project_dirs, testmon_labels=set()):
        self.project_dirs = project_dirs
        self.testmon_labels = testmon_labels
        self.setup_coverage(not('singleprocess' in testmon_labels))

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

        self.cov = coverage.Coverage(include=includes,
                                     omit=_get_python_lib_paths(),
                                     data_file=getattr(self, 'sub_cov_file', None),
                                     config_file=False, )
        self.cov._warn_no_data = False

    def track_dependencies(self, callable_to_track, testmon_data, rootdir, nodeid):
        self.start()
        try:
            callable_to_track()
        except:
            raise
        finally:
            self.stop_and_save(testmon_data, rootdir, nodeid)


    def start(self):
        self.cov.erase()
        self.cov.start()

    def stop(self):
        self.cov.stop()

    def stop_and_save(self, testmon_data, rootdir, nodeid):
        self.stop()
        if hasattr(self, 'sub_cov_file'):
            self.cov.combine()

        testmon_data.set_dependencies(nodeid, self.cov.get_data(), rootdir)



    def close(self):
        if hasattr(self, 'sub_cov_file'):
            os.remove(self.sub_cov_file + "_rc")
        os.environ.pop('COVERAGE_PROCESS_START', None)


def eval_variant(run_variant, **kwargs):
    if not run_variant:
        return ''

    def md5(s):
        return hashlib.md5(s.encode()).hexdigest()

    eval_globals = {'os': os, 'sys': sys, 'hashlib': hashlib, 'md5': md5}
    eval_globals.update(kwargs)

    try:
        return str(eval(run_variant, eval_globals))
    except Exception as e:
        return repr(e)


def get_variant_inifile(inifile):
    config = configparser.ConfigParser()
    config.read(str(inifile),)
    if config.has_section('pytest') and config.has_option('pytest', 'run_variant_expression'):
        run_variant_expression = config.get('pytest', 'run_variant_expression')
    else:
        run_variant_expression = None

    return eval_variant(run_variant_expression)


class TestmonData(object):

    def __init__(self, rootdir, variant=None):

        self.variant = variant if variant else 'default'
        self.rootdir = rootdir
        self.init_connection()
        self.mtimes = {}
        self.node_data = {}
        self.modules_cache = {}
        self.lastfailed = []

    def __eq__(self, other):
        return (self.mtimes, \
                self.node_data, \
                self.lastfailed == other.mtimes, \
                other.node_data, \
                other.lastfailed)

    def init_connection(self):
        self.datafile = os.path.join(self.rootdir, '.testmondata')
        self.connection = None
        import sqlite3

        if os.path.exists(self.datafile):
            self.newfile = False
        else:
            self.newfile = True
        self.connection = sqlite3.connect(self.datafile)
        if getattr(self, 'newfile', False):
            self.init_tables()

    def _fetch_attribute(self, attribute, default=None):
        cursor = self.connection.execute("SELECT data FROM alldata WHERE dataid=?",
                                         [self.variant + ':' + attribute])
        result = cursor.fetchone()
        if result:
            return json.loads(zlib.decompress(result[0]).decode('utf-8)'))
        else:
            return default

    def _write_attribute(self, attribute, data):
        dataid = self.variant + ':' + attribute
        json_data = json.dumps(data).encode('utf-8')
        compressed_data_buffer = buffer(zlib.compress(json_data))
        cursor = self.connection.execute("UPDATE alldata SET data=? WHERE dataid=?",
                                         [compressed_data_buffer, dataid])
        if not cursor.rowcount:

            cursor.execute("INSERT INTO alldata VALUES (?, ?)",
                           [dataid, compressed_data_buffer])

    def init_tables(self):
        self.connection.execute('CREATE TABLE alldata (dataid text primary key, data blob)')

    def read_data(self):
        self.mtimes, \
        self.node_data, \
        self.lastfailed = self._fetch_attribute('mtimes', default={}), \
                          self._fetch_attribute('node_data', default={}), \
                          self._fetch_attribute('lastfailed', default=[])

    def write_data(self):
        with self.connection:
            self._write_attribute('mtimes', self.mtimes)
            self._write_attribute('node_data', self.node_data)
            self._write_attribute('lastfailed', self.lastfailed)

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

    def set_dependencies(self, nodeid, coverage_data, rootdir):
        result = {}
        for filename in coverage_data.measured_files():
            lines = coverage_data.lines(filename)
            if os.path.exists(filename):
                result[filename] = checksum_coverage(self.parse_cache(filename).blocks, lines)
        if not result:
            filename = os.path.join(rootdir, nodeid).split("::",1)[0]
            result[filename] = checksum_coverage(self.parse_cache(filename).blocks,[1])
        self.node_data[nodeid] = result

    def parse_cache(self, module, new_mtime=None):
        if module not in self.modules_cache:
            self.modules_cache[module] = Module(file_name=module)
            self.mtimes[module] = new_mtime if new_mtime else os.path.getmtime(module)

        return self.modules_cache[module]

    def read_fs(self):
        self.read_data()
        self.old_mtimes = self.mtimes.copy()
        self.unchanged_paths = set()
        for py_file in self.modules_test_counts():
            try:
                new_mtime = os.path.getmtime(py_file)
                if self.old_mtimes.get(py_file) != new_mtime:
                    self.parse_cache(py_file, new_mtime)

            except OSError:
                self.mtimes[py_file] = [-2]

        self.compute_unaffected()

    def compute_unaffected(self):
        affected_paths = set()
        all_paths = defaultdict(lambda: 0)
        for nodeid in self.node_data:
            path = os.path.join(self.rootdir, nodeid.split("::")[0])
            all_paths[path] += 1
            if self.test_should_run(nodeid):
                affected_paths.add(path)

        affected_paths.update([os.path.join(self.rootdir, nodeid.split("::")[0]) for nodeid in self.lastfailed])

        self.unaffected_paths = {path: all_paths[path] for path in all_paths if path not in affected_paths}

## possible data structures
## nodeid1 -> [filename -> [block_a, block_b]]
## filename -> [block_a -> [nodeid1, ], block_b -> [nodeid1], block_c -> [] ]

    def collect_garbage(self, allnodeids): # TODO, this was naive a causing loss of data ..
        return
        for testmon_nodeid in list(self.node_data.keys()):
            if testmon_nodeid not in allnodeids:
                del self.node_data[testmon_nodeid]
        for lastfailed_nodeid in self.lastfailed:
            if lastfailed_nodeid not in allnodeids:
                self.lastfailed.remove(lastfailed_nodeid)
