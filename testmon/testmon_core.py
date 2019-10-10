from array import array
from collections import defaultdict

import configparser
import hashlib
import json
import os
import random
import sqlite3
import sys
import textwrap

import coverage
from coverage.tracer import CTracer

from testmon.process_code import read_file_with_checksum,    file_has_lines, create_fingerprints, encode_lines
from testmon.process_code import Module

CHECKUMS_ARRAY_TYPE = 'I'
DB_FILENAME = '.testmondata'


def checksums_to_blob(checksums):
    blob = array(CHECKUMS_ARRAY_TYPE, checksums)
    data = blob.tobytes()
    return sqlite3.Binary(data)


def blob_to_checksums(blob):
    a = array(CHECKUMS_ARRAY_TYPE)
    a.frombytes(blob)
    return a.tolist()



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


DISAPPEARED_FILE = Module("#dissapeared file")
DISAPPEARED_FILE_CHECKSUM = 3948583


def home_file(node_name):
    return node_name.split("::", 1)[0]


def is_python_file(file_path):
    return file_path[-3:] == '.py'


def get_measured_relfiles(rootdir, cov, test_file):
    files = {test_file: set()}  
    c = cov.config
    for filename in cov.get_data().measured_files():
        if not is_python_file(filename):
            continue
        relfilename = os.path.relpath(filename, rootdir)
        files[relfilename] = cov.get_data().lines(filename)
        assert files[relfilename] is not None, f"{filename} is in measured_files but wasn't measured! cov.config: "                                               f"{c.config_files}, {c._omit}, {c._include}, {c.source}"
    return files


class SourceTree():
    

    def __init__(self, rootdir=''):
        self.rootdir = rootdir
        self.cache = {}

    def get_changed_files(self, db_files):
        
        result = set()
        for filename, mtime, checksum, fingerprint_id in db_files:
            try:
                absfilename = os.path.join(self.rootdir, filename)
                module = self.cache.get(filename, None)
                fs_mtime = module.mtime if module else os.path.getmtime(absfilename)
                if mtime != fs_mtime:
                    module = self.get_file(filename)
                    if checksum != module.checksum:
                        result.add(fingerprint_id)
                    else:
                        module.mtime = fs_mtime

            except OSError:
                result.add(fingerprint_id)

        return result

    def get_file(self, filename):
        if filename not in self.cache:
            code, checksum = read_file_with_checksum(os.path.join(self.rootdir, filename))
            fs_mtime = os.path.getmtime(os.path.join(self.rootdir, filename))
            self.cache[filename] = Module(source_code=code, file_name=filename, rootdir=self.rootdir,
                                          mtime=fs_mtime, checksum=checksum)
        return self.cache[filename]

    def unstable(self, changed_files_data):
        unstable_nodes = set()
        unstable_files = set()
        new_mtimes = []

        for file, node_name, fingerprint, fingerprint_id in changed_files_data:
            module = self.get_file(file)
            if not file_has_lines(module.full_lines, module.full_lines_checksums, fingerprint):
                unstable_nodes.add(node_name)
                unstable_files.add(node_name.split('::', 1)[0])  
            else:
                new_mtimes.append((module.mtime, module.checksum, fingerprint_id))

        return unstable_nodes, unstable_files, new_mtimes


class TestmonData(object):
    
    DATA_VERSION = 6

    def __init__(self, rootdir="", environment=None):

        self.environment = environment if environment else 'default'
        self.rootdir = rootdir
        self.all_files = None
        self.all_nodes = None
        self.unstable_files = None
        self.source_tree = SourceTree(rootdir=self.rootdir)

        self.connection = None
        self.init_connection()

    def init_connection(self):
        self.datafile = os.environ.get(
            'TESTMON_DATAFILE',
            os.path.join(self.rootdir, DB_FILENAME))

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
        stored_data_version = self._fetch_attribute('__data_version', default=None, environment='default')

        if stored_data_version is None or int(stored_data_version) == self.DATA_VERSION:
            return

        msg = (
            "The stored data file {} version ({}) is not compatible with current version ({})."
            " You must delete the stored data to continue."
        ).format(self.datafile, stored_data_version, self.DATA_VERSION)
        raise Exception(msg)

    def _fetch_attribute(self, attribute, default=None, environment=None):
        cursor = self.connection.execute("SELECT data FROM metadata WHERE dataid=?",
                                         [(environment if environment else self.environment) + ':' + attribute])
        result = cursor.fetchone()
        if result:
            return json.loads(result[0])  
        else:
            return default

    def read_data(self):
        con = self.connection

        self.nfp_product = self.connection.execute("""
                SELECT DISTINCT 
                    f.file_name, f.mtime, f.checksum, f.id 
                FROM node n, node_fingerprint nfp, fingerprint f 
                WHERE n.id = nfp.node_id AND 
                      nfp.fingerprint_id = f.id AND 
                      environment = ?""",
                                                   (self.environment,)).fetchall()

        self.all_files = {row[0] for row in self.nfp_product}

        self.all_nodes = {row[0]: json.loads(row[1]) for row in con.execute("""  SELECT name, result
                                    FROM node 
                                    WHERE environment = ?
                                   """, (self.environment,))}

    def get_files(self):
        return self.nfp_product

    def get_changed_file_data(self, changed_fingerprints):
        in_clause_questionsmarks = ', '.join('?' * len(changed_fingerprints))
        result = []
        for row in self.connection.execute("""
            SELECT
                f.file_name,
                n.name,
                f.fingerprint,
                f.id
            FROM node n, node_fingerprint nfp, fingerprint f
            WHERE 
                n.environment = ? AND
                n.id = nfp.node_id AND 
                nfp.fingerprint_id = f.id AND
                f.id IN (%s)""" % in_clause_questionsmarks,
                                           [self.environment, ] + list(changed_fingerprints)):
            result.append((row[0], row[1], blob_to_checksums(row[2]), row[3]))

        return result

    def _write_attribute(self, attribute, data, environment=None):
        dataid = (environment if environment else self.environment) + ':' + attribute
        with self.connection as con:
            con.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)",
                        [dataid, json.dumps(data)])

    def init_tables(self):
        self.connection.execute('CREATE TABLE metadata (dataid TEXT PRIMARY KEY, data TEXT)')

        self.connection.execute("""
          CREATE TABLE node (
              id INTEGER PRIMARY KEY ASC,
              environment TEXT,
              name TEXT,
              result TEXT,
              failed BIT,
              UNIQUE (environment, name)
              )
""")

        self.connection.execute("""
              CREATE TABLE node_fingerprint (
                node_id INTEGER,
                fingerprint_id INTEGER,
                FOREIGN KEY(node_id) REFERENCES node(id) ON DELETE CASCADE,
                FOREIGN KEY(fingerprint_id) REFERENCES fingerprint(id)
                    )
        """)

        self.connection.execute("""
            CREATE table fingerprint 
            (
              id INTEGER PRIMARY KEY,
              file_name TEXT,
              fingerprint TEXT,
              mtime FLOAT,
              checksum TEXT,
              UNIQUE (file_name, fingerprint)            
            )
                            """)

        self._write_attribute('__data_version', str(self.DATA_VERSION), environment='default')

    def sync_db_fs_nodes(self, retain):
        collected = retain.union(set(self.stable_nodeids))
        with self.connection as con:
            add = collected - set(self.all_nodes)

            for nodeid in add:
                if is_python_file(home_file(nodeid)):
                    self.write_node_data(nodeid,
                                         self.make_nodedata({home_file(nodeid): None}, encode_lines(['0match'])),
                                         fake=True)

            con.executemany("""
                DELETE
                FROM node
                WHERE environment = ?
                  AND name = ?""",
                            [(self.environment, nodeid) for nodeid in
                             set(self.all_nodes) - collected])

    def make_nodedata(self, measured_files, default=None):
        result = {}
        for filename, covered in measured_files.items():
            if default:
                result[filename] = default
            else:
                if os.path.exists(os.path.join(self.rootdir, filename)):
                    module = self.source_tree.get_file(filename)
                    result[filename] = encode_lines(create_fingerprints(module.lines, module.special_blocks, covered))
        return result

    def node_data_from_cov(self, cov, nodeid):
        return self.make_nodedata(get_measured_relfiles(self.rootdir, cov, home_file(nodeid)))

    def write_node_data(self, nodeid, nodedata, result={}, fake=False):
        with self.connection as con:
            failed = any(r.get('outcome') == u'failed' for r in result.values())
            cursor = con.cursor()
            cursor.execute("INSERT OR REPLACE INTO "
                           "    node "
                           "(environment, name, result, failed) "
                           "VALUES (?, ?, ?, ?)",
                           (self.environment, nodeid,
                            json.dumps(result),
                            failed))
            node_id = cursor.lastrowid

            cursor.execute(
                "DELETE FROM node_fingerprint WHERE node_id = ?", (node_id,)
            )  

            for filename in nodedata:
                if fake:
                    mtime, checksum = None, None
                else:
                    module = self.source_tree.get_file(filename)
                    mtime, checksum = module.mtime, module.checksum

                fingerprint = checksums_to_blob(nodedata[filename])
                con.execute("""INSERT OR IGNORE INTO
                                    fingerprint
                                (file_name, fingerprint, mtime, checksum)
                                VALUES
                                    (?, ?, ?, ?)
                                """, (filename, fingerprint, mtime, checksum))

                fingerprint_id, db_mtime, db_checksum = con.execute(
                    "SELECT id, mtime, checksum FROM fingerprint WHERE file_name = ? AND fingerprint=?",
                    (filename, fingerprint,)).fetchone()

                if db_checksum != checksum or db_mtime != mtime:  
                    self.update_mtimes([(mtime, checksum, fingerprint_id)])

                con.execute("INSERT INTO node_fingerprint VALUES (?, ?)",
                            (node_id, fingerprint_id))

    def update_mtimes(self, new_mtimes):
        self.connection.executemany(
            "UPDATE fingerprint SET mtime=?, checksum=? WHERE id = ?",
            new_mtimes)

    def determine_stable(self):
        

        db_files = self.get_files()

        
        

        changed_fingeprints_files = self.source_tree.get_changed_files(
            db_files)  

        

        changed_file_data = self.get_changed_file_data(changed_fingeprints_files)  
        

        
        
        
        

        self.unstable_nodeids, self.unstable_files, new_mtimes = self.source_tree.unstable(
            changed_file_data)  

        self.stable_nodeids = set(self.all_nodes) - self.unstable_nodeids  
        self.stable_files = self.all_files - self.unstable_files

        self.update_mtimes(new_mtimes)


class Testmon(object):
    coverage_stack = []

    def __init__(self, project_dirs, testmon_labels=set(['singleprocess'])):
        self.project_dirs = project_dirs
        self.testmon_labels = testmon_labels
        self.setup_coverage(not ('singleprocess' in testmon_labels))

    def setup_coverage(self, subprocess):
        includes = [os.path.join(path, '*') for path in self.project_dirs]

        self.cov = coverage.Coverage(include=includes,
                                     omit=_get_python_lib_paths(),
                                     data_file=getattr(self, 'sub_cov_file', None),
                                     config_file=False, )
        self.cov._warn_no_data = False


    def start(self):
        Testmon.coverage_stack.append(self.cov)

        self.cov.erase()
        self.cov.start()

    def stop(self):
        self.cov.stop()
        Testmon.coverage_stack.pop()

    def stop_and_save(self, testmon_data: TestmonData, rootdir, nodeid, result):
        self.stop()
        if hasattr(self, 'sub_cov_file'):
            self.cov.combine()
        node_data = testmon_data.node_data_from_cov(self.cov, nodeid)
        testmon_data.write_node_data(nodeid, node_data, result)

    def close(self):
        if hasattr(self, 'sub_cov_file'):
            os.remove(self.sub_cov_file + "_rc")
        os.environ.pop('COVERAGE_PROCESS_START', None)


class TestmonConfig:


    def _is_debugger(self):
        return sys.gettrace() and not isinstance(sys.gettrace(), CTracer)

    def _is_coverage(self):
        return isinstance(sys.gettrace(), CTracer)

    def _is_xdist(self, options):
        return ('dist' in options and options['dist'] != 'no') or 'slaveinput' in options

    def _get_notestmon_reasons(self, options, xdist):
        if options['no-testmon']:
            return "deactivated through --no-testmon"

        if options['testmon_noselect'] and options['testmon_nocollect']:
            return "deactivated, both noselect and nocollect options used"

        if not any(options[t] for t in
                   ['testmon', 'testmon_noselect', 'testmon_nocollect', 'testmon_forceselect']):
            return 'not mentioned'

        if xdist:
            return "deactivated, execution with xdist is not supported"

        return None

    def _get_nocollect_reasons(self, options, debugger=False, coverage=False, dogfooding=False):
        if options['testmon_nocollect']:
            return [None]

        if coverage and not dogfooding:
            return ["it's not compatible with coverage.py"]

        if debugger and not dogfooding:
            return ["it's not compatible with debugger"]

        return []

    def _get_noselect_reasons(self, options):
        if options['testmon_forceselect']:
            return []

        elif options['testmon_noselect']:
            return [None]

        if options['keyword']:
            return ['-k was used']

        if options['markexpr']:
            return ['-m was used']

        if options['lf']:
            return ['--lf was used']

        return []

    def _formulate_deactivation(self, what, reasons):
        if reasons:
            return [
                f"{what} automatically deactivated because {reasons[0]}, " if reasons[0] else what + " deactivated, "]
        else:
            return []

    def _header_collect_select(self, options, debugger=False, coverage=False, dogfooding=False, xdist=False):
        notestmon_reasons = self._get_notestmon_reasons(options, xdist=xdist)

        if notestmon_reasons == 'not mentioned':
            return None, False, False
        elif notestmon_reasons:
            return 'testmon: ' + notestmon_reasons, False, False

        nocollect_reasons = self._get_nocollect_reasons(options, debugger=debugger, coverage=coverage,
                                                        dogfooding=dogfooding)

        noselect_reasons = self._get_noselect_reasons(options)

        if nocollect_reasons or noselect_reasons:
            message = ''.join(self._formulate_deactivation('collection', nocollect_reasons) +
                              self._formulate_deactivation('selection', noselect_reasons))
        else:
            message = ''

        return f"testmon: {message}", not bool(nocollect_reasons), not bool(noselect_reasons)

    def header_collect_select(self, config, coverage_stack):
        options = vars(config.option)
        return self._header_collect_select(
            options,
            debugger=self._is_debugger(),
            coverage=self._is_coverage(),
            xdist=self._is_xdist(options)
        )


def eval_environment(environment, **kwargs):
    if not environment:
        return ''

    def md5(s):
        return hashlib.md5(s.encode()).hexdigest()

    eval_globals = {'os': os, 'sys': sys, 'hashlib': hashlib, 'md5': md5}
    eval_globals.update(kwargs)

    try:
        return str(eval(environment, eval_globals))
    except Exception as e:
        return repr(e)
