from array import array
import hashlib
import json
import os
import sqlite3
import sys

from coverage import Coverage
from coverage.tracer import CTracer

from testmon.process_code import (
    read_file_with_checksum,
    file_has_lines,
    create_fingerprints,
    encode_lines,
)
from testmon.process_code import Module

if sys.version_info.major < 3:
    range = xrange

CHECKUMS_ARRAY_TYPE = "I"  # from zlib.adler32
DB_FILENAME = ".testmondata"
SQLITE_PAGE_LIMIT = 5000


def checksums_to_blob(checksums):
    blob = array(CHECKUMS_ARRAY_TYPE, checksums)
    try:
        data = blob.tobytes()
    except AttributeError:
        data = blob.tostring()
    return sqlite3.Binary(data)


def blob_to_checksums(blob):
    a = array(CHECKUMS_ARRAY_TYPE)
    try:
        a.frombytes(blob)
    except AttributeError:
        a.fromstring(blob)
    return a


def _get_python_lib_paths():
    res = [sys.prefix]
    for attr in ["exec_prefix", "real_prefix", "base_prefix"]:
        if getattr(sys, attr, sys.prefix) not in res:
            res.append(getattr(sys, attr))
    return [os.path.join(d, "*") for d in res]


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
            "{} is in measured_files but wasn't measured! cov.config: ".format(filename) +
            "{config_files}, {_omit}, {_include}, {source}".format(**c)
        )
    return files


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


class cached_property(object):

    def __init__(self, func):
        self.__doc__ = getattr(func, "__doc__")
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


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
        self.connection.execute("PRAGMA shrink_memory")
        self.connection.execute("PRAGMA temp_store = FILE")
        self.connection.execute("PRAGMA auto_vacuum = INCREMENTAL")
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
        self.connection.execute(
            """
            CREATE INDEX node_fingerprint_idx ON node_fingerprint (
                node_id,
                fingerprint_id
            )
            """
        )
        # Speeds up `remove_unused_fingerprints`
        self.connection.execute(
            """
            CREATE INDEX fingerprint_idx ON node_fingerprint (
                fingerprint_id
            )
            """
        )

        self._write_attribute(
            "__data_version", str(self.DATA_VERSION), environment="default"
        )
        self.connection.commit()

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

    @property
    def filenames_fingerprints(self):
        return self.connection.execute(
            """
            SELECT DISTINCT
            f.file_name, f.mtime, f.checksum, f.id as fingerprint_id
            FROM fingerprint f
            JOIN node n ON n.id = nfp.node_id
            JOIN node_fingerprint nfp ON nfp.fingerprint_id = f.id
            WHERE environment =?
            """,
            (self.environment,),
        )

    @property
    def all_files(self):
        return {row[0] for row in self.filenames_fingerprints}

    @cached_property
    def all_nodes(self):
        return {
            row[0]
            for row in self.connection.execute(
                """
                SELECT name
                FROM node
                WHERE environment = ?
                """,
                (self.environment,),
            )
        }

    @cached_property
    def failing_nodes(self):
        return {
            row[0]
            for row in self.connection.execute(
                """
                SELECT name
                FROM node
                WHERE environment = ?
                AND failed = true
                """,
                (self.environment,),
            )
        }

    def get_report(self, nodeid):
        result_row = self.connection.execute(
            """
            SELECT result FROM node WHERE name = ?
            """, (nodeid,)
        ).fetchone()
        return json.loads(result_row[0]) if result_row else {}

    def make_nodedata(self, measured_files, default=None):
        result = {}
        for filename, covered in measured_files.items():
            if default:
                result[filename] = default
            else:
                if os.path.exists(os.path.join(self.rootdir, filename)):
                    coverage_set = set(covered)  # To speed `in` lookups
                    module = self.source_tree.get_file(filename)
                    result[filename] = encode_lines(
                        create_fingerprints(
                            module.lines, module.special_blocks, coverage_set
                        )
                    )
        return result

    def node_data_from_cov(self, cov, nodeid):
        return self.make_nodedata(
            get_measured_relfiles(self.rootdir, cov, home_file(nodeid))
        )

    @staticmethod
    def did_fail(reports):
        return any(
            [True for report in reports.values() if report.get("outcome") == u"failed"]
        )

    def write_node_data(self, nodeid, nodedata, result={}, fake=False):
        with self.connection as con:
            failed = self.did_fail(result)
            cursor = con.cursor()
            # This replaces a node each time to clear out any node<->fingerprint mappings
            # by relying on the `ON DELETE CASCADE` on `node_id` in `node_fingerprint`.
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
                fingerprint_id = cursor.lastrowid  # See if it changes (i.e. new record)
                cursor.execute(
                    """
                    INSERT INTO fingerprint
                    (file_name, fingerprint, mtime, checksum)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(file_name, fingerprint)
                    DO UPDATE SET mtime=excluded.mtime, checksum=excluded.checksum
                    """,
                    (filename, fingerprint, mtime, checksum),
                )
                fingerprint_id = cursor.lastrowid if cursor.lastrowid != fingerprint_id else None
                if not fingerprint_id:  # Updated, so get ID
                    fingerprint_id = cursor.execute(
                        'SELECT id FROM fingerprint WHERE file_name=? AND fingerprint=?',
                        (filename, fingerprint),
                    ).fetchone()[0]
                cursor.execute(
                    "INSERT INTO node_fingerprint VALUES (?, ?)",
                    (node_id, fingerprint_id),
                )

    def sync_db_fs_nodes(self, retain):
        collected = retain.union(self.stable_nodeids)
        with self.connection as con:
            add = collected - self.all_nodes

            for nodeid in add:
                if not is_python_file(home_file(nodeid)):
                    continue
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
                  AND name = ?
                """,
                [
                    (self.environment, nodeid)
                    for nodeid in self.all_nodes - collected
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
        """Takes list of tuples of the form `mtime, checksum, fingerprint_id` to update"""
        with self.connection as con:
            con.executemany(
                "UPDATE fingerprint SET mtime=?, checksum=? WHERE id = ?", new_mtimes
            )

    def get_new_mtimes(self, hits):
        """
        Take a list of dictionaries/sqlite3.Row of objects with at least a `file_name` and
        a `fingerprint_id` and yields the modified time of the module, the checksum and the
        fingerprint_id.
        """
        for hit in hits:
            module = self.source_tree.get_file(hit["file_name"])
            if module:
                yield module.mtime, module.checksum, hit["fingerprint_id"]

    def get_changed_file_data(self, changed_fingerprints):
        """
        This may be a monster dataset, i.e. 800k fingerprints changed,
        so page through SQLite style, and yield until there are no more results.
        """
        last_nfp_rowid = 0
        fingerprint_ids = ', '.join([str(fp) for fp in changed_fingerprints])
        while True:
            current_page = self.connection.execute(
                """
                SELECT
                  f.file_name,
                  n.name,
                  nfp.fingerprint_id,
                  f.fingerprint,
                  nfp.ROWID
                FROM node_fingerprint nfp
                JOIN node n ON n.id = nfp.node_id
                JOIN fingerprint f ON f.id = nfp.fingerprint_id
                WHERE nfp.fingerprint_id IN ({fingerprint_ids})
                AND nfp.ROWID > {last_nfp_rowid}
                ORDER BY nfp.ROWID
                LIMIT {limit}
                """.format(
                    fingerprint_ids=fingerprint_ids,
                    limit=SQLITE_PAGE_LIMIT,
                    last_nfp_rowid=last_nfp_rowid,
                )
            ).fetchall()
            if len(current_page) == 0:
                return

            for row in current_page:
                yield (
                    row["file_name"],
                    row["name"],
                    blob_to_checksums(row["fingerprint"]),
                    row["fingerprint_id"]
                )
                last_nfp_rowid = row["ROWID"]

    def check_mtime(self, file_name, mtime):
        absfilename = os.path.join(self.source_tree.rootdir, file_name)

        cache_module = self.source_tree.cache.get(file_name, None)
        try:
            fs_mtime = cache_module.mtime if cache_module else os.path.getmtime(absfilename)
        except OSError:
            return False
        return mtime == fs_mtime

    def check_checksum(self, file_name, checksum):
        cache_module = self.source_tree.get_file(file_name)
        fs_checksum = cache_module.checksum if cache_module else None

        return checksum == fs_checksum

    def check_fingerprint(self, file_name, fingerprint):
        module = self.source_tree.get_file(file_name)

        return module and file_has_lines(module.full_lines, fingerprint)

    def determine_stable(self):

        missed_checksum_fingerprint_ids = set()
        hit_checksum_fingerprints = []
        for fingerprint in self.filenames_fingerprints:
            # If the mtime matches, file is unchanged
            if self.check_mtime(fingerprint["file_name"], fingerprint["mtime"]):
                continue

            # If the checksum is a hit update the modified time
            # otherwise add the fingerprint id to a set for finding
            # affected nodes with that fingerprint
            if self.check_checksum(fingerprint["file_name"], fingerprint["checksum"]):
                hit_checksum_fingerprints.append(fingerprint)
            else:
                missed_checksum_fingerprint_ids.add(fingerprint["fingerprint_id"])

        self.update_mtimes(self.get_new_mtimes(hit_checksum_fingerprints))
        del hit_checksum_fingerprints  # Memory sensitive function, so free early

        # Loop through all changed files and verify the fingerprint
        self.unstable_files = set()
        self.unstable_nodeids = set()
        hit_fingerprint_nodes = []

        # Loop through files by affected node
        for file_name, nodeid, fingerprint, fingerprint_id in self.get_changed_file_data(
                missed_checksum_fingerprint_ids
        ):
            # If the fingerprint is hit, update the mtime
            # otherwise add the node for the missed fingerprint to the unstable set
            if self.check_fingerprint(file_name, fingerprint):
                hit_fingerprint_nodes.append(
                    {"file_name": file_name, "fingerprint_id": fingerprint_id}
                )
            else:
                self.unstable_nodeids.add(nodeid)
                self.unstable_files.add(home_file(nodeid))
        self.update_mtimes(self.get_new_mtimes(hit_fingerprint_nodes))

        # Reverse the unstable set to the stable set to appropriately handle
        # new files.
        self.stable_nodeids = self.all_nodes - self.unstable_nodeids
        self.stable_files = self.all_files - self.unstable_files


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

    def stop_and_save(self, testmon_data, rootdir, nodeid, result):
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
                "{} automatically deactivated because {}, ".format(what, reasons[0])
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
            "testmon: {}".format(message),
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
