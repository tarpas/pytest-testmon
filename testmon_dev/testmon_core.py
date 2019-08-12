from collections import defaultdict

from array import array

from coverage.parser import PythonParser

try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import hashlib
import json
import os
import random
import sqlite3
import sys
import textwrap

import coverage

from testmon_dev.process_code import read_file_with_checksum, \
    file_has_lines, create_fingerprints
from testmon_dev.process_code import Module

if sys.version_info > (3,):
    buffer = memoryview
    encode = lambda x: bytes(x, 'utf_8')
else:
    encode = lambda x: x

CHECKUMS_ARRAY_TYPE = 'I'


def checksums_to_blob(checksums):
    return json.dumps(checksums)


def blob_to_checksums(blob):
    return json.loads(blob)


def _get_python_lib_paths():
    res = [sys.prefix]
    for attr in ['exec_prefix', 'real_prefix', 'base_prefix']:
        if getattr(sys, attr, sys.prefix) not in res:
            res.append(getattr(sys, attr))
    return [os.path.join(d, "*") for d in res]


def flip_dictionary(node_data):
    files = defaultdict(lambda: {})
    for nodeid, node_files in node_data.items():
        for filename, checksums in node_files.items():
            files[filename][nodeid] = checksums
    return files


def stable(node_data, changed_files):
    file_data = node_data.file_data()
    changed_nodes = set()
    changed_files2 = set()

    changed_files_set = changed_files & file_data.keys()  # changed_files will be a subset of file_data,
    # but we'll make sure anyway
    for file in changed_files_set:
        for nodeid, fingerprints in file_data[file].items():
            if not file_has_lines(changed_files[file].full_lines, fingerprints):
                changed_nodes.add(nodeid)
                changed_files2.add(nodeid.split('::', 1)[0])
                changed_files2.add(file)

    return node_data.keys() - changed_nodes, set(file_data) - changed_files2


def node_data_to_test_files(node_data):
    """only return files that contain tests, without indirect dependencies"""
    test_files = defaultdict(lambda: set())
    for nodeid, node_files in node_data.items():
        test_files[nodeid.split("::", 1)[0]].add(nodeid)
    return test_files


def sort_items_by_duration(items, reports):
    durations = defaultdict(lambda: {'node_count': 0, 'duration': 0})
    for item in items:
        item.duration = sum([report['duration'] for report in reports[item.nodeid].values()])
        item.module_name = item.location[0]
        item_hierarchy = item.location[2].split('.')
        item.node_name = item_hierarchy[-1]
        item.class_name = item_hierarchy[0]

        durations[item.class_name]['node_count'] += 1
        durations[item.class_name]['duration'] += item.duration
        durations[item.module_name]['node_count'] += 1
        durations[item.module_name]['duration'] += item.duration

    for key, stats in durations.items():
        durations[key]['avg_duration'] = stats['duration'] / stats['node_count']

    items.sort(key=lambda item: item.duration)
    items.sort(key=lambda item: durations[item.class_name]['avg_duration'])
    items.sort(key=lambda item: durations[item.module_name]['avg_duration'])


class NodesData(dict):

    def file_data(self):
        return flip_dictionary(self)


class TestmonData(object):
    # If you change the SQLlite schema, you should bump this number
    DATA_VERSION = 4

    def __init__(self, rootdir, variant=None):

        self.variant = variant if variant else 'default'
        self.rootdir = rootdir
        self.init_connection()
        self.node_data = NodesData({})
        self.reports = defaultdict(lambda: [])

    def init_connection(self):
        self.datafile = os.environ.get(
            'TESTMON_DATAFILE',
            os.path.join(self.rootdir, '.testmondata'))
        self.connection = None

        new_db = not os.path.exists(self.datafile)

        self.connection = sqlite3.connect(self.datafile)
        self.connection.execute("PRAGMA recursive_triggers = TRUE ")

        if new_db:
            self.init_tables()

        self._check_data_version()

    def close_connection(self):
        if self.connection:
            self.connection.close()

    def _check_data_version(self):
        stored_data_version = self._fetch_attribute('__data_version', default=None, variant='default')

        if stored_data_version is None or int(stored_data_version) == self.DATA_VERSION:
            return

        msg = (
            "The stored data file {} version ({}) is not compatible with current version ({})."
            " You must delete the stored data to continue."
        ).format(self.datafile, stored_data_version, self.DATA_VERSION)
        raise Exception(msg)

    def _fetch_attribute(self, attribute, default=None, variant=None):
        cursor = self.connection.execute("SELECT data FROM metadata WHERE dataid=?",
                                         [(variant if variant else self.variant) + ':' + attribute])
        result = cursor.fetchone()
        if result:
            return json.loads(result[0])  # zlib.decompress(result[0]).decode('utf-8)'))
        else:
            return default

    def _fetch_node_data(self):
        dependencies = NodesData()
        for row in self.connection.execute("""SELECT
                                                n.name,
                                                nf.file_name,
                                                nf.checksums
                                              FROM node n, node_file nf WHERE n.id = nf.node_id AND n.variant=?""",
                                           (self.variant,)):
            if row[0] in dependencies:
                dependencies[row[0]][row[1]] = blob_to_checksums(row[2])
            else:
                dependencies[row[0]] = {row[1]: blob_to_checksums(row[2])}

        fail_reports = defaultdict(lambda: {})

        for row in self.connection.execute('SELECT name, result FROM node WHERE variant=?',
                                           (self.variant,)):
            fail_reports[row[0]] = json.loads(row[1])

        return dependencies, fail_reports

    def _write_attribute(self, attribute, data, variant=None):
        dataid = (variant if variant else self.variant) + ':' + attribute
        json_data = json.dumps(data)
        compressed_data_buffer = json_data  # buffer(zlib.compress(json_data.encode('utf-8')))
        cursor = self.connection.execute("UPDATE metadata SET data=? WHERE dataid=?",
                                         [compressed_data_buffer, dataid])
        if not cursor.rowcount:
            cursor.execute("INSERT INTO metadata VALUES (?, ?)",
                           [dataid, compressed_data_buffer])

    def init_tables(self):
        self.connection.execute('CREATE TABLE metadata (dataid TEXT PRIMARY KEY, data TEXT)')
        self.connection.execute("""
          CREATE TABLE node (
              id INTEGER PRIMARY KEY ASC,
              variant TEXT,
              name TEXT,
              result TEXT,
              failed BIT,
              UNIQUE (variant, name)
              )
""")
        self.connection.execute("""
          CREATE TABLE node_file (
            node_id INTEGER,
            file_name TEXT,
            checksums text,
            FOREIGN KEY(node_id) REFERENCES node(id) ON DELETE CASCADE)
    """)
        self._write_attribute('__data_version', str(self.DATA_VERSION), variant='default')

    def read_data(self):
        self.node_data, self.reports = self._fetch_node_data()
        self.f_last_failed = set(nodeid.split("::", 1)[0] for nodeid in self.reports)
        self.f_tests = node_data_to_test_files(self.node_data)

    def write_common_data(self):
        with self.connection:
            if hasattr(self, 'source_tree'):
                self._write_attribute('mtimes', self.source_tree.mtimes)
                self._write_attribute('file_checksums', self.source_tree.checksums)

    def collect_garbage(self, retain):
        delete = set(self.node_data.keys()) - retain
        for node_id in delete:
            self.node_data.pop(node_id, None)
        self.connection.executemany('DELETE FROM node WHERE variant=? AND name=?',
                                    [(self.variant, removed_nodeid) for removed_nodeid in delete])

    def repr_per_node(self, key):
        return "{}: {}\n".format(key,
                                 [(os.path.relpath(p), checksum)
                                  for (p, checksum)
                                  in self.node_data[key].items()])

    def file_data(self):
        return flip_dictionary(self.node_data)

    def _parse_source(self, covered, source_code):
        parser = PythonParser(text=source_code)
        parser.parse_source()
        return parser.statements, parser.translate_lines(covered), parser._multiline

    def get_nodedata(self, cov, nodeid):
        def update_result(filename, covered):
            relfilename = os.path.relpath(filename, self.rootdir)
            module = self.source_tree.get_file(relfilename)
            result[relfilename] = create_fingerprints(module.lines, module.special_blocks, covered)

        result = {}

        for filename in cov.get_data().measured_files():
            if os.path.exists(filename):
                covered = set(cov.get_data().lines(filename))
                update_result(filename, covered)
        if not result:
            update_result(filename=os.path.join(self.rootdir, nodeid).split("::", 1)[0],
                          covered=set())  # all special blocks get a GAP_MARK, the rest literal
        return result

    def set_dependencies(self, nodeid, cov, result=None):
        nodedata = self.get_nodedata(cov, nodeid)
        self.write_node_data(nodeid, nodedata, result)

    def write_node_data(self, nodeid, nodedata, result):
        with self.connection as con:
            outcome = bool([True for r in result.values() if r.get('outcome') == u'failed'])
            cursor = con.cursor()
            cursor.execute("INSERT OR REPLACE INTO "
                           "node "
                           "(variant, name, result, failed) "
                           "VALUES (?, ?, ?, ?)",
                           (self.variant, nodeid,
                            json.dumps(result),
                            outcome))
            con.executemany("INSERT INTO node_file VALUES (?, ?, ?)",
                            [(cursor.lastrowid, filename, checksums_to_blob(nodedata[filename])) for filename in
                             nodedata])

    def read_source(self):
        mtimes = self._fetch_attribute('mtimes', default={})
        checksums = self._fetch_attribute('file_checksums', default={})

        self.source_tree = SourceTree(rootdir=self.rootdir, mtimes=mtimes, checksums=checksums)
        self.stable_nodeids, self.stable_files = stable(self.node_data,
                                                        self.source_tree.get_changed_files())


class Testmon(object):
    def __init__(self, project_dirs, testmon_labels=set()):
        self.project_dirs = project_dirs
        self.testmon_labels = testmon_labels
        self.setup_coverage(not ('singleprocess' in testmon_labels))

    def setup_coverage(self, subprocess):
        includes = [os.path.join(path, '*') for path in self.project_dirs]
        if subprocess:
            self.setup_subprocess(includes)

        self.cov = coverage.Coverage(include=includes,
                                     omit=_get_python_lib_paths(),
                                     data_file=getattr(self, 'sub_cov_file', None),
                                     config_file=False, )
        self.cov._warn_no_data = False

    def setup_subprocess(self, includes):
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

    def stop_and_save(self, testmon_data, rootdir, nodeid, result):
        self.stop()
        if hasattr(self, 'sub_cov_file'):
            self.cov.combine()

        testmon_data.set_dependencies(nodeid, self.cov, result)

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
    config.read(str(inifile), )
    if config.has_section('pytest') and config.has_option('pytest', 'run_variant_expression'):
        run_variant_expression = config.get('pytest', 'run_variant_expression')
    else:
        run_variant_expression = None

    return eval_variant(run_variant_expression)


class SourceTree():
    def __init__(self, rootdir, mtimes, checksums):
        self.rootdir = rootdir
        self.mtimes = mtimes
        self.checksums = checksums
        self.changed_files = {}

    def get_changed_files(self):

        for filename in self.mtimes:
            try:
                absfilename = os.path.join(self.rootdir, filename)
                fs_mtime = os.path.getmtime(absfilename)
                if self.mtimes[filename] != fs_mtime:
                    self.mtimes[filename] = fs_mtime
                    code, fs_checksum = read_file_with_checksum(absfilename)
                    if self.checksums.get(filename) != fs_checksum:
                        self.checksums[filename] = fs_checksum
                        self.changed_files[filename] = Module(source_code=code, file_name=filename,
                                                              rootdir=self.rootdir)

            except OSError:
                pass
                # self.changed_files[filename] = DISAPPEARED_FILE

        return self.changed_files

    def get_file(self, filename):
        if filename not in self.changed_files:
            code, checksum = read_file_with_checksum(os.path.join(self.rootdir, filename))
            self.mtimes[filename] = os.path.getmtime(os.path.join(self.rootdir, filename))
            self.checksums[filename] = checksum
            self.changed_files[filename] = Module(source_code=code, file_name=filename, rootdir=self.rootdir)
        return self.changed_files[filename]
