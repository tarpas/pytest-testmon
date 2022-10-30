import hashlib
import os
import random
import sys
import textwrap
from functools import lru_cache
from collections import defaultdict
import pkg_resources
import pytest
from coverage import Coverage, CoverageData

from testmon.db import CachedProperty
from testmon import db
from testmon.process_code import (
    read_file_with_checksum,
    match_fingerprint,
    create_fingerprint,
    encode_lines,
    string_checksum,
)
from testmon.process_code import Module

TEST_BATCH_SIZE = 100


LIBRARIES_KEY = "/libraries_checksum_testmon_name"

CHECKUMS_ARRAY_TYPE = "I"
DB_FILENAME = ".testmondata"


def get_data_file_path(rootdir):
    return os.environ.get("TESTMON_DATAFILE", os.path.join(rootdir, DB_FILENAME))


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


class TestmonException(Exception):
    pass


class SourceTree:
    def __init__(self, rootdir="", libraries=None):
        self.rootdir = rootdir
        self.libraries = libraries
        self.cache = {}

    def get_file(self, filename):
        if filename not in self.cache:
            code, checksum = read_file_with_checksum(
                os.path.join(self.rootdir, filename)
            )
            if checksum:
                fs_mtime = os.path.getmtime(os.path.join(self.rootdir, filename))
                self.cache[filename] = Module(
                    source_code=code, mtime=fs_mtime, ext=filename.rsplit(".", 1)[1]
                )
            else:
                self.cache[filename] = None
        return self.cache[filename]


def check_mtime(file_system, record):
    absfilename = os.path.join(file_system.rootdir, record["filename"])

    cache_module = file_system.cache.get(record["filename"], None)
    try:
        fs_mtime = cache_module.mtime if cache_module else os.path.getmtime(absfilename)
    except OSError:
        return False
    return record["mtime"] == fs_mtime


def check_checksum(file_system, record):
    cache_module = file_system.get_file(record["filename"])
    fs_checksum = cache_module.fs_checksum if cache_module else None

    return record["checksum"] == fs_checksum


def check_fingerprint(disk, record):
    file = record[0]
    fingerprint = record[2]

    module = disk.get_file(file)
    return module and match_fingerprint(module, fingerprint)


def split_filter(disk, function, records):
    first = []
    second = []
    for record in records:
        if function(disk, record):
            first.append(record)
        else:
            second.append(record)
    return first, second


def get_measured_relfiles(rootdir, test_file, lines_data=None):
    files = {test_file: set([1])}
    for filename, lines in lines_data.items():
        if not is_python_file(filename):
            continue
        relfilename = cached_relpath(filename, rootdir)
        if lines:
            files[relfilename] = lines
    return files


class TestmonData:
    def __init__(self, rootdir="", environment=None, libraries=None, rpc=None):

        self.environment = environment if environment else "default"
        self.rootdir = rootdir
        self.unstable_files = None
        self.source_tree = SourceTree(rootdir=self.rootdir)
        if libraries is None:
            libraries = ", ".join(
                sorted(str(p) for p in pkg_resources.working_set or [])
            )

        self.libraries = libraries

        self.connection = None
        self.datafile = get_data_file_path(self.rootdir)
        if rpc:
            self.db = rpc
        else:
            self.db = db.DB(self.datafile, self.environment)

        self.libraries_miss = set()
        self.unstable_nodeids = set()
        self.unstable_files = set()
        self.stable_nodeids = set()
        self.stable_files = set()

    def close_connection(self):
        if self.connection:
            self.connection.close()

    @property
    def all_files(self):
        return {row["filename"] for row in self.db.filenames_fingerprints()}

    @CachedProperty
    def all_nodes(self):
        return self.db.all_nodes()

    def get_nodes_fingerprints(self, measured_files):
        nodes_fingerprints = []

        for filename, covered in measured_files.items():
            if os.path.exists(os.path.join(self.rootdir, filename)):
                module = self.source_tree.get_file(filename)
                fingerprint = create_fingerprint(module, covered)
                nodes_fingerprints.append(
                    {
                        "filename": filename,
                        "mtime": module.mtime,
                        "checksum": string_checksum(module.source_code),
                        "method_checksums": fingerprint,
                    }
                )
        return nodes_fingerprints

    def sync_db_fs_nodes(self, retain):
        collected = retain.union(set(self.stable_nodeids))
        with self.db as database:
            add = collected - set(self.all_nodes)

            for nodeid in add:
                if is_python_file(home_file(nodeid)):
                    database.insert_node_file_fps(
                        {
                            nodeid: (
                                {
                                    "filename": home_file(nodeid),
                                    "method_checksums": encode_lines(["0match"]),
                                    "mtime": None,
                                    "checksum": None,
                                },
                            )
                        },
                    )
            database.delete_nodes(list(set(self.all_nodes) - collected))

    def run_filters(self, filenames_fingerprints):

        library_misses = []
        mtime_misses = []

        for record in filenames_fingerprints:
            if record["filename"] == LIBRARIES_KEY:
                if record["checksum"] != self.libraries:
                    library_misses.append(record)
            else:
                if not check_mtime(self.source_tree, record):
                    mtime_misses.append(record)

        checksum_hits, checksum_misses = split_filter(
            self.source_tree, check_checksum, mtime_misses
        )

        changed_file_data = self.db.get_changed_file_data(
            [
                checksum_miss["fingerprint_id"]
                for checksum_miss in (checksum_misses + library_misses)
            ],
        )

        fingerprint_hits, fingerprint_misses = split_filter(
            self.source_tree, check_fingerprint, changed_file_data
        )

        return (
            fingerprint_hits,
            fingerprint_misses,
            checksum_hits,
            library_misses,
        )

    def determine_stable(self):

        filenames_fingerprints = self.db.filenames_fingerprints()

        (
            fingerprint_hits,
            fingerprint_misses,
            checksum_hits,
            libraries_miss,
        ) = self.run_filters(filenames_fingerprints)

        self.libraries_miss = libraries_miss
        self.unstable_nodeids = set()
        self.unstable_files = set()

        for fingerprint_miss in fingerprint_misses:
            self.unstable_nodeids.add(fingerprint_miss[1])
            self.unstable_files.add(fingerprint_miss[1].split("::", 1)[0])

        self.stable_nodeids = set(self.all_nodes) - self.unstable_nodeids
        self.stable_files = self.all_files - self.unstable_files

        self.db.update_mtimes(list(get_new_mtimes(self.source_tree, checksum_hits)))
        self.db.update_mtimes(list(get_new_mtimes(self.source_tree, fingerprint_hits)))

    @property
    def avg_durations(self):
        stats = defaultdict(lambda: {"node_count": 0, "sum_duration": 0})

        for node_id, report in self.all_nodes.items():
            if report:
                class_name = get_node_class_name(node_id)
                module_name = get_node_module_name(node_id)

                stats[node_id]["node_count"] += 1
                stats[node_id]["sum_duration"] = report.get("duration") or 0
                if class_name:
                    stats[class_name]["node_count"] += 1
                    stats[class_name]["sum_duration"] += stats[node_id]["sum_duration"]
                stats[module_name]["node_count"] += 1
                stats[module_name]["sum_duration"] += stats[node_id]["sum_duration"]

        durations = defaultdict(lambda: 0)
        for key, stats in stats.items():
            durations[key] = stats["sum_duration"] / stats["node_count"]

        return durations


def nofili2fingerprints(nodes_files_lines, testmon_data):

    nodes_fingerprints = {}
    for context in nodes_files_lines:
        node_fingerprints = testmon_data.get_nodes_fingerprints(
            nodes_files_lines[context]
        )

        node_fingerprints.append(
            {
                "filename": LIBRARIES_KEY,
                "checksum": testmon_data.libraries,
                "mtime": None,
                "method_checksums": encode_lines([testmon_data.libraries]),
            }
        )

        nodes_fingerprints[context] = node_fingerprints
    return nodes_fingerprints


def get_new_mtimes(filesystem, hits):

    try:
        for hit in hits:
            module = filesystem.get_file(hit[0])
            if module:
                yield module.mtime, string_checksum(module.source_code), hit[3]
    except KeyError:
        for hit in hits:
            module = filesystem.get_file(hit["filename"])
            if module:
                yield module.mtime, string_checksum(module.source_code), hit[
                    "fingerprint_id"
                ]


def get_node_class_name(node_id):
    if len(node_id.split("::")) > 2:
        return node_id.split("::")[1]
    return None


def get_node_module_name(node_id):
    return node_id.split("::")[0]


@lru_cache(1000)
def cached_relpath(path, basepath):
    return os.path.relpath(path, basepath)


class Testmon:
    coverage_stack = []

    def __init__(self, rootdir="", testmon_labels=None, cov_plugin=None):
        try:
            from testmon.testmon_core import Testmon as UberTestmon

            Testmon.coverage_stack = UberTestmon.coverage_stack
        except ImportError:
            pass
        if testmon_labels is None:
            testmon_labels = {"singleprocess"}
        self.rootdir = rootdir
        self.testmon_labels = testmon_labels
        self.cov = None
        self.sub_cov_file = None
        self.cov_plugin = cov_plugin
        self._nodeid = None
        self._next_nodeid = None
        self.batched_nodeids = set()
        self.check_stack = []
        self.is_started = False
        self._interrupted_at = None

    def start_cov(self):
        if not self.cov._started:
            Testmon.coverage_stack.append(self.cov)
            self.cov.start()

    def stop_cov(self):
        if self.cov is None:
            return
        assert self.cov in Testmon.coverage_stack
        if Testmon.coverage_stack:
            while Testmon.coverage_stack[-1] != self.cov:
                cov = Testmon.coverage_stack.pop()
                cov.stop()
        if self.cov._started:
            self.cov.stop()
            Testmon.coverage_stack.pop()
        if Testmon.coverage_stack:
            Testmon.coverage_stack[-1].start()

    def setup_coverage(self, subprocess=False):
        params = {
            "include": [os.path.join(self.rootdir, "*")],
            "omit": _get_python_lib_paths(),
        }

        if self.cov_plugin and self.cov_plugin._started:
            cov = self.cov_plugin.cov_controller.cov
            Testmon.coverage_stack.append(cov)
            if cov.config.source:
                params["include"] = list(
                    set(
                        [os.path.join(self.rootdir, "*")]
                        + [
                            os.path.join(os.path.abspath(source), "*")
                            for source in cov.config.source
                        ]
                    )
                )
            elif cov.config.run_include:
                params["include"] = list(
                    set(cov.config.run_include + params["include"])
                )
            if cov.config.branch:
                raise TestmonException(
                    "testmon doesn't support simultaneous run with pytest-cov when "
                    "branch coverage is on. Please disable branch coverage."
                )

        self.cov = Coverage(data_file=self.sub_cov_file, config_file=False, **params)
        self.cov._warn_no_data = False
        if Testmon.coverage_stack:
            Testmon.coverage_stack[-1].stop()

        self.start_cov()

    class DummyFrame:
        f_globals = None

    @lru_cache(1000)
    def filter_parent(self, parent_cov, filename):
        check_include_omit_etc = parent_cov._inorout.check_include_omit_etc
        return check_include_omit_etc(filename, self.DummyFrame)

    def start_testmon(self, nodeid, next_nodeid=None):
        self._next_nodeid = next_nodeid

        self.batched_nodeids.add(nodeid)
        if self.cov is None:
            self.setup_coverage()

        self.start_cov()
        self._nodeid = nodeid
        self.cov.switch_context(nodeid)
        self.check_stack = Testmon.coverage_stack.copy()

    def discard_current(self):
        self._interrupted_at = self._nodeid

    def get_batch_coverage_data(self):

        if self.check_stack != Testmon.coverage_stack:
            pytest.exit(
                f"Exiting pytest!!!! This test corrupts Testmon.coverage_stack: "
                f"{self._nodeid} {self.check_stack}, {Testmon.coverage_stack}",
                returncode=3,
            )

        nodes_files_lines = {}

        if self.cov and (
            len(self.batched_nodeids) >= TEST_BATCH_SIZE
            or self._next_nodeid is None
            or self._interrupted_at
        ):
            self.cov.stop()
            nodes_files_lines, lines_data = self.get_nodes_files_lines(
                dont_include=self._interrupted_at
            )

            if (
                len(Testmon.coverage_stack) > 1
                and Testmon.coverage_stack[-1] == self.cov
            ):
                filtered_lines_data = {
                    file: data
                    for file, data in lines_data.items()
                    if not self.filter_parent(Testmon.coverage_stack[-2], file)
                }
                Testmon.coverage_stack[-2].get_data().add_lines(filtered_lines_data)

            self.cov.erase()
            self.cov.start()
            self.batched_nodeids = set()
        return nodes_files_lines

    def get_nodes_files_lines(self, dont_include):
        cov_data = self.cov.get_data()
        files = cov_data.measured_files()
        nodes_files_lines = {}
        files_lines = {}
        for file in files:

            relfilename = cached_relpath(file, self.rootdir)

            contexts_by_lineno = cov_data.contexts_by_lineno(file)

            for lineno, contexts in contexts_by_lineno.items():
                for context in contexts:
                    nodes_files_lines.setdefault(context, {}).setdefault(
                        relfilename, set()
                    ).add(lineno)
                    files_lines.setdefault(file, set()).add(lineno)
        nodes_files_lines.pop(dont_include, None)
        self.batched_nodeids.discard(dont_include)
        nodes_files_lines.pop("", None)
        for nodeid in self.batched_nodeids:
            if home_file(nodeid) not in nodes_files_lines.setdefault(nodeid, {}):
                nodes_files_lines[nodeid].setdefault(home_file(nodeid), {1})
        return nodes_files_lines, files_lines

    @staticmethod
    def save_fingerprints(testmon_data, nodeid, node_fingerprints, failed, duration):
        testmon_data.db.insert_node_file_fps(
            nodeid, node_fingerprints, failed, duration
        )

    def close(self):
        if self.cov is None:
            return
        assert self.cov in Testmon.coverage_stack
        if Testmon.coverage_stack:
            while Testmon.coverage_stack[-1] != self.cov:
                cov = Testmon.coverage_stack.pop()
                cov.stop()
        if self.cov._started:
            self.cov.stop()
            Testmon.coverage_stack.pop()
        if self.sub_cov_file:
            os.remove(self.sub_cov_file + "_rc")
        os.environ.pop("COVERAGE_PROCESS_START", None)
        self.cov = None
        if Testmon.coverage_stack:
            Testmon.coverage_stack[-1].start()


def eval_environment(environment, **kwargs):
    if not environment:
        return ""

    def md5(string):
        return hashlib.md5(string.encode()).hexdigest()

    eval_globals = {"os": os, "sys": sys, "hashlib": hashlib, "md5": md5}
    eval_globals.update(kwargs)

    try:
        return str(eval(environment, eval_globals))
    except Exception as error:
        return repr(error)
