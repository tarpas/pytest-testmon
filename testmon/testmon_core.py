import hashlib
import json
import os
import random
import sqlite3
import sys
import textwrap
from packaging import version
from array import array
from collections import defaultdict

import coverage
from coverage import Coverage
from coverage.tracer import CTracer

from testmon.process_code import (
    read_file_with_checksum,
    file_has_lines,
    create_fingerprints,
    encode_lines,
)
from testmon.process_code import Module

CHECKUMS_ARRAY_TYPE = "I"
DB_FILENAME = ".testmondata"


def checksums_to_blob(checksums):
    blob = array(CHECKUMS_ARRAY_TYPE, checksums)
    data = blob.tobytes()
    return sqlite3.Binary(data)


def blob_to_checksums(blob):
    a = array(CHECKUMS_ARRAY_TYPE)
    a.frombytes(blob)
    return a.tolist()




class cached_property(object):
    

    def __init__(self, func):
        self.__doc__ = getattr(func, "__doc__")
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value



def _get_python_lib_paths():
    res = [sys.prefix]
    for attr in ["exec_prefix", "real_prefix", "base_prefix"]:
        if getattr(sys, attr, sys.prefix) not in res:
            res.append(getattr(sys, attr))
    return [os.path.join(d, "*") for d in res]


DISAPPEARED_FILE = Module("#dissapeared file")
DISAPPEARED_FILE_CHECKSUM = 3948583


def home_file(node_name):
    return node_name.split("::", 1)[0]


def is_python_file(file_path):
    return file_path[-3:] == ".py"


def get_measured_relfiles(rootdir, cov, test_file):
    files = {
        test_file: set()
    }
    c = cov.config
    for filename in cov.get_data().measured_files():
        if not is_python_file(filename):
            continue
        relfilename = os.path.relpath(filename, rootdir)
        files[relfilename] = cov.get_data().lines(filename)
        assert files[relfilename] is not None, (
            f"{filename} is in measured_files but wasn't measured! cov.config: "
            f"{c.config_files}, {c._omit}, {c._include}, {c.source}"
        )
    return files


class TestmonException(Exception):
    pass


class SourceTree:
    

    def __init__(self, rootdir=""):
        self.rootdir = rootdir
        self.cache = {}

    def get_file(self, filename):
        if filename not in self.cache:
            code, checksum = read_file_with_checksum(
                os.path.join(self.rootdir, filename)
            )
            if checksum:
                fs_mtime = os.path.getmtime(os.path.join(self.rootdir, filename))
                self.cache[filename] = Module(
                    source_code=code,
                    file_name=filename,
                    rootdir=self.rootdir,
                    mtime=fs_mtime,
                    checksum=checksum,
                )
            else:
                self.cache[filename] = None
        return self.cache[filename]


def check_mtime(file_system, record):
    absfilename = os.path.join(file_system.rootdir, record["file_name"])

    cache_module = file_system.cache.get(record["file_name"], None)
    try:
        fs_mtime = cache_module.mtime if cache_module else os.path.getmtime(absfilename)
    except OSError:
        return False
    return record["mtime"] == fs_mtime


def check_checksum(file_system, record):
    cache_module = file_system.get_file(record["file_name"])
    fs_checksum = cache_module.checksum if cache_module else None

    return record["checksum"] == fs_checksum


def check_fingerprint(disk, record):
    file = record[0]
    fingerprint = record[2]

    module = disk.get_file(file)
    return module and file_has_lines(module.full_lines, fingerprint)


def split_filter(disk, function, records):
    first = []
    second = []
    for record in records:
        if function(disk, record):
            first.append(record)
        else:
            second.append(record)
    return first, second


class TestmonData(object):
    DATA_VERSION = 6

    def __init__(self, rootdir="", environment=None):

        self.environment = environment if environment else "default"
        self.rootdir = rootdir
        self.unstable_files = None
        self.source_tree = SourceTree(rootdir=self.rootdir)

        self.connection = None
        self.init_connection()

    def init_connection(self):
        self.datafile = os.environ.get(
            "TESTMON_DATAFILE", os.path.join(self.rootdir, DB_FILENAME)
        )

        new_db = not os.path.exists(self.datafile)

        self.connection = sqlite3.connect(self.datafile)
        self.connection.execute("PRAGMA foreign_keys = TRUE ")
        self.connection.execute("PRAGMA recursive_triggers = TRUE ")
        self.connection.row_factory = sqlite3.Row

        if new_db:
            self.init_tables()

        self._check_data_version()

    def close_connection(self):
        if self.connection:
            self.connection.close()

    def init_tables(self):
        self.connection.execute(
            "CREATE TABLE metadata (dataid TEXT PRIMARY KEY, data TEXT)"
        )

        self.connection.execute(
            """
            CREATE TABLE node (
                id INTEGER PRIMARY KEY ASC,
                environment TEXT,
                name TEXT,
                result TEXT,
                failed BIT,
                UNIQUE (environment, name)
            )
            """
        )

        self.connection.execute(
            """
            CREATE TABLE node_fingerprint (
                node_id INTEGER,
                fingerprint_id INTEGER,
                FOREIGN KEY(node_id) REFERENCES node(id) ON DELETE CASCADE,
                FOREIGN KEY(fingerprint_id) REFERENCES fingerprint(id)
            )
            """
        )

        self.connection.execute(
            """
            CREATE table fingerprint 
            (
                id INTEGER PRIMARY KEY,
                file_name TEXT,
                fingerprint TEXT,
                mtime FLOAT,
                checksum TEXT,
                UNIQUE (file_name, fingerprint)            
            )
            """
        )

        self._write_attribute(
            "__data_version", str(self.DATA_VERSION), environment="default"
        )

    def _check_data_version(self):
        stored_data_version = self._fetch_attribute(
            "__data_version", default=None, environment="default"
        )

        if stored_data_version is None or int(stored_data_version) == self.DATA_VERSION:
            return

        msg = (
            "The stored data file {} version ({}) is not compatible with current version ({})."
            " You must delete the stored data to continue."
        ).format(self.datafile, stored_data_version, self.DATA_VERSION)
        raise TestmonException(msg)

    def _fetch_attribute(self, attribute, default=None, environment=None):
        cursor = self.connection.execute(
            "SELECT data FROM metadata WHERE dataid=?",
            [(environment if environment else self.environment) + ":" + attribute],
        )
        result = cursor.fetchone()
        if result:
            return json.loads(result[0])
        else:
            return default

    def _write_attribute(self, attribute, data, environment=None):
        dataid = (environment if environment else self.environment) + ":" + attribute
        with self.connection as con:
            con.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
                [dataid, json.dumps(data)],
            )

    @cached_property
    def filenames_fingerprints(self):
        return self.connection.execute(
            """
                SELECT DISTINCT 
                    f.file_name, f.mtime, f.checksum, f.id as fingerprint_id 
                FROM node n, node_fingerprint nfp, fingerprint f 
                WHERE n.id = nfp.node_id AND 
                      nfp.fingerprint_id = f.id AND 
                      environment = ?""",
            (self.environment,),
        ).fetchall()

    @property
    def all_files(self):
        return {row[0] for row in self.filenames_fingerprints}

    @cached_property
    def all_nodes(self):
        return {
            row[0]: json.loads(row[1])
            for row in self.connection.execute(
                """  SELECT name, result
                                    FROM node 
                                    WHERE environment = ?
                                   """,
                (self.environment,),
            )
        }

    def get_changed_file_data(self, changed_fingerprints):
        in_clause_questionsmarks = ", ".join("?" * len(changed_fingerprints))
        result = []
        for row in self.connection.execute(
            """
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
                            f.id IN (%s)"""
            % in_clause_questionsmarks,
            [self.environment,] + list(changed_fingerprints),
        ):
            result.append((row[0], row[1], blob_to_checksums(row[2]), row[3]))

        return result

    def make_nodedata(self, measured_files, default=None):
        result = {}
        for filename, covered in measured_files.items():
            if default:
                result[filename] = default
            else:
                if os.path.exists(os.path.join(self.rootdir, filename)):
                    module = self.source_tree.get_file(filename)
                    result[filename] = encode_lines(
                        create_fingerprints(
                            module.lines, module.special_blocks, covered
                        )
                    )
        return result

    def node_data_from_cov(self, cov, nodeid):
        return self.make_nodedata(
            get_measured_relfiles(self.rootdir, cov, home_file(nodeid))
        )

    def write_node_data(self, nodeid, nodedata, result={}, fake=False):
        with self.connection as con:
            failed = any(r.get("outcome") == "failed" for r in result.values())
            cursor = con.cursor()
            cursor.execute(
                """ 
                INSERT OR REPLACE INTO node 
                (environment, name, result, failed) 
                VALUES (?, ?, ?, ?)
                """,
                (self.environment, nodeid, json.dumps(result), failed),
            )
            node_id = cursor.lastrowid


            for filename in nodedata:
                if fake:
                    mtime, checksum = None, None
                else:
                    module = self.source_tree.get_file(filename)
                    mtime, checksum = module.mtime, module.checksum

                fingerprint = checksums_to_blob(nodedata[filename])
                con.execute(
                    """
                    INSERT OR IGNORE INTO fingerprint
                    (file_name, fingerprint, mtime, checksum)
                    VALUES (?, ?, ?, ?)
                    """,
                    (filename, fingerprint, mtime, checksum),
                )

                fingerprint_id, db_mtime, db_checksum = con.execute(
                    "SELECT id, mtime, checksum FROM fingerprint WHERE file_name = ? AND fingerprint=?",
                    (filename, fingerprint,),
                ).fetchone()

                if (
                    db_checksum != checksum or db_mtime != mtime
                ):
                    self.update_mtimes([(mtime, checksum, fingerprint_id)])

                con.execute(
                    "INSERT INTO node_fingerprint VALUES (?, ?)",
                    (node_id, fingerprint_id),
                )

    def sync_db_fs_nodes(self, retain):
        collected = retain.union(set(self.stable_nodeids))
        with self.connection as con:
            add = collected - set(self.all_nodes)

            for nodeid in add:
                if is_python_file(home_file(nodeid)):
                    self.write_node_data(
                        nodeid,
                        self.make_nodedata(
                            {home_file(nodeid): None}, encode_lines(["0match"])
                        ),
                        fake=True,
                    )

            con.executemany(
                """
                DELETE
                FROM node
                WHERE environment = ?
                  AND name = ?""",
                [
                    (self.environment, nodeid)
                    for nodeid in set(self.all_nodes) - collected
                ],
            )

    def remove_unused_fingerprints(self):
        with self.connection as con:
            con.execute(
                """
                DELETE FROM fingerprint
                WHERE id NOT IN (
                    SELECT DISTINCT fingerprint_id FROM node_fingerprint
                )
                """
            )

    def update_mtimes(self, new_mtimes):
        with self.connection as con:
            con.executemany(
                "UPDATE fingerprint SET mtime=?, checksum=? WHERE id = ?", new_mtimes
            )

    def run_filters(self):
        

        filenames_fingerprints = self.filenames_fingerprints


        _, mtime_misses = split_filter(
            self.source_tree, check_mtime, filenames_fingerprints
        )

        checksum_hits, checksum_misses = split_filter(
            self.source_tree, check_checksum, mtime_misses
        )

        changed_file_data = self.get_changed_file_data(
            {checksum_miss["fingerprint_id"] for checksum_miss in checksum_misses}
        )


        fingerprint_hits, fingerprint_misses = split_filter(
            self.source_tree, check_fingerprint, changed_file_data
        )

        return fingerprint_hits, fingerprint_misses, checksum_hits

    def determine_stable(self):

        fingerprint_hits, fingerprint_misses, checksum_hits = self.run_filters()

        self.unstable_nodeids = set()
        self.unstable_files = set()

        for fingerprint_miss in fingerprint_misses:
            self.unstable_nodeids.add(fingerprint_miss[1])
            self.unstable_files.add(fingerprint_miss[1].split("::", 1)[0])

        self.stable_nodeids = set(self.all_nodes) - self.unstable_nodeids
        self.stable_files = self.all_files - self.unstable_files

        self.update_mtimes(get_new_mtimes(self.source_tree, checksum_hits))
        self.update_mtimes(get_new_mtimes(self.source_tree, fingerprint_hits))


def get_new_mtimes(filesystem, hits):
    
    for hit in hits:
        module = filesystem.get_file(hit[0])
        if module:
            yield module.mtime, module.checksum, hit[3]


class Testmon(object):
    coverage_stack = []

    def __init__(self, rootdir="", testmon_labels=None, cov_plugin=None):
        if testmon_labels is None:
            testmon_labels = set(["singleprocess"])
        self.rootdir = rootdir
        self.testmon_labels = testmon_labels
        self.cov = None
        self.setup_coverage(not ("singleprocess" in testmon_labels), cov_plugin)

    def setup_coverage(self, subprocess, cov_plugin=None):
        params = {
            "include": [os.path.join(self.rootdir, "*")],
            "omit": _get_python_lib_paths(),
        }



        self.cov = Coverage(
            data_file=getattr(self, "sub_cov_file", None), config_file=False, **params
        )
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
        if hasattr(self, "sub_cov_file"):
            self.cov.combine()
        node_data = testmon_data.node_data_from_cov(self.cov, nodeid)
        testmon_data.write_node_data(nodeid, node_data, result)

    def close(self):
        if hasattr(self, "sub_cov_file"):
            os.remove(self.sub_cov_file + "_rc")
        os.environ.pop("COVERAGE_PROCESS_START", None)


class TestmonConfig:


    def _is_debugger(self):
        return sys.gettrace() and not isinstance(sys.gettrace(), CTracer)

    def _is_coverage(self):
        return isinstance(sys.gettrace(), CTracer)

    def _is_xdist(self, options):
        return (
            "dist" in options and options["dist"] != "no"
        ) or "slaveinput" in options

    def _get_notestmon_reasons(self, options, xdist):
        if options["no-testmon"]:
            return "deactivated through --no-testmon"

        if options["testmon_noselect"] and options["testmon_nocollect"]:
            return "deactivated, both noselect and nocollect options used"

        if not any(
            options[t]
            for t in [
                "testmon",
                "testmon_noselect",
                "testmon_nocollect",
                "testmon_forceselect",
            ]
        ):
            return "not mentioned"

        if xdist:
            return "deactivated, execution with xdist is not supported"

        return None

    def _get_nocollect_reasons(
        self,
        options,
        debugger=False,
        coverage=False,
        dogfooding=False,
        cov_plugin=False,
    ):
        if options["testmon_nocollect"]:
            return [None]


        if coverage and not dogfooding:
            return ["it's not compatible with coverage.py"]

        if debugger and not dogfooding:
            return ["it's not compatible with debugger"]

        return []

    def _get_noselect_reasons(self, options):
        if options["testmon_forceselect"]:
            return []

        elif options["testmon_noselect"]:
            return [None]

        if options["keyword"]:
            return ["-k was used"]

        if options["markexpr"]:
            return ["-m was used"]

        if options["lf"]:
            return ["--lf was used"]

        return []

    def _formulate_deactivation(self, what, reasons):
        if reasons:
            return [
                f"{what} automatically deactivated because {reasons[0]}, "
                if reasons[0]
                else what + " deactivated, "
            ]
        else:
            return []

    def _header_collect_select(
        self,
        options,
        debugger=False,
        coverage=False,
        dogfooding=False,
        xdist=False,
        cov_plugin=False,
    ):
        notestmon_reasons = self._get_notestmon_reasons(options, xdist=xdist)

        if notestmon_reasons == "not mentioned":
            return None, False, False
        elif notestmon_reasons:
            return "testmon: " + notestmon_reasons, False, False

        nocollect_reasons = self._get_nocollect_reasons(
            options,
            debugger=debugger,
            coverage=coverage,
            dogfooding=dogfooding,
            cov_plugin=cov_plugin,
        )

        noselect_reasons = self._get_noselect_reasons(options)

        if nocollect_reasons or noselect_reasons:
            message = "".join(
                self._formulate_deactivation("collection", nocollect_reasons)
                + self._formulate_deactivation("selection", noselect_reasons)
            )
        else:
            message = ""

        return (
            f"testmon: {message}",
            not bool(nocollect_reasons),
            not bool(noselect_reasons),
        )

    def header_collect_select(self, config, coverage_stack, cov_plugin=None):
        options = vars(config.option)
        return self._header_collect_select(
            options,
            debugger=self._is_debugger(),
            coverage=self._is_coverage(),
            xdist=self._is_xdist(options),
            cov_plugin=cov_plugin,
        )


def eval_environment(environment, **kwargs):
    if not environment:
        return ""

    def md5(s):
        return hashlib.md5(s.encode()).hexdigest()

    eval_globals = {"os": os, "sys": sys, "hashlib": hashlib, "md5": md5}
    eval_globals.update(kwargs)

    try:
        return str(eval(environment, eval_globals))
    except Exception as e:
        return repr(e)
