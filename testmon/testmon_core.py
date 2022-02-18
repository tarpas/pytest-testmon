import hashlib
import os
import random
import sys
import textwrap

import coverage
import pkg_resources

from collections import defaultdict
from packaging import version
from typing import TypeVar

from coverage import Coverage

from testmon import db
from testmon.process_code import (
    read_file_with_checksum,
    match_fingerprint,
    create_fingerprint,
    encode_lines,
    string_checksum,
)
from testmon.process_code import Module, fingerprint_to_blob

T = TypeVar("T")

LIBRARIES_KEY = "/libraries_checksum_testmon_name"

CHECKUMS_ARRAY_TYPE = "I"
DB_FILENAME = ".testmondata"


class CachedProperty(object):
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
    absfilename = os.path.join(file_system.rootdir, record["file_name"])

    cache_module = file_system.cache.get(record["file_name"], None)
    try:
        fs_mtime = cache_module.mtime if cache_module else os.path.getmtime(absfilename)
    except OSError:
        return False
    return record["mtime"] == fs_mtime


def check_checksum(file_system, record):
    cache_module = file_system.get_file(record["file_name"])
    fs_checksum = string_checksum(cache_module.source_code) if cache_module else None

    return record["checksum"] == fs_checksum


def check_fingerprint(disk, record: db.ChangedFileData):
    file = record.file_name
    fingerprint = record.checksums

    module = disk.get_file(file)
    return module and match_fingerprint(module, fingerprint)


def split_filter(disk, function, records: [T]) -> ([T], [T]):
    first = []
    second = []
    for record in records:
        if function(disk, record):
            first.append(record)
        else:
            second.append(record)
    return first, second


def get_measured_relfiles(rootdir, cov, test_file):
    files = {test_file: set([1])}
    c = cov.config
    cov_data = cov.get_data()
    for filename in cov_data.measured_files():
        if not is_python_file(filename):
            continue
        relfilename = os.path.relpath(filename, rootdir)
        files[relfilename] = cov_data.lines(filename)
        assert files[relfilename] is not None, (
            f"{filename} is in measured_files but wasn't measured! cov.config: "
            f"{c.config_files}, {c._omit}, {c._include}, {c.source}"
        )
    return files


class TestmonData(object):
    def __init__(self, rootdir="", environment=None, libraries=None):

        self.environment = environment if environment else "default"
        self.rootdir = rootdir
        self.unstable_files = None
        self.source_tree = SourceTree(rootdir=self.rootdir)
        if libraries is None:
            libraries = ", ".join(sorted(str(p) for p in pkg_resources.working_set))

        self.libraries = libraries

        self.connection = None
        self.datafile = os.environ.get(
            "TESTMON_DATAFILE", os.path.join(self.rootdir, DB_FILENAME)
        )
        self.db = db.DB(self.datafile, self.environment)

        self.libraries_miss = set()
        self.unstable_nodeids = set()
        self.unstable_files = set()
        self.stable_nodeids = set()
        self.stable_files = set()

    def close_connection(self):
        if self.connection:
            self.connection.close()

    @CachedProperty
    def filenames_fingerprints(self):
        return self.db.filenames_fingerprints()

    @property
    def all_files(self):
        return {row["file_name"] for row in self.filenames_fingerprints}

    @CachedProperty
    def all_nodes(self):
        return self.db.all_nodes()

    def get_nodes_fingerprints(self, measured_files, default=None):
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
                        "fingerprint": fingerprint,
                    }
                )
        return nodes_fingerprints

    def sync_db_fs_nodes(self, retain, should_sync=True):
        collected = retain.union(set(self.stable_nodeids))
        with self.db as database:
            add = collected - set(self.all_nodes)

            if should_sync:
                for nodeid in add:
                    if is_python_file(home_file(nodeid)):
                        database.insert_node_fingerprints(
                            nodeid=nodeid,
                            fingerprint_records=(
                                {
                                    "filename": home_file(nodeid),
                                    "fingerprint": encode_lines(["0match"]),
                                    "mtime": None,
                                    "checksum": None,
                                },
                            ),
                        )
            database.delete_nodes(set(self.all_nodes) - collected)

    def run_filters(self, filenames_fingerprints):

        library_misses = []
        mtime_misses = []

        for record in filenames_fingerprints:
            if record["file_name"] == LIBRARIES_KEY:
                if record["checksum"] != self.libraries:
                    library_misses.append(record)
            else:
                if not check_mtime(self.source_tree, record):
                    mtime_misses.append(record)

        checksum_hits, checksum_misses = split_filter(
            self.source_tree, check_checksum, mtime_misses
        )

        changed_file_data = self.db.get_changed_file_data(
            {
                checksum_miss["fingerprint_id"]
                for checksum_miss in (checksum_misses + library_misses)
            },
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

        filenames_fingerprints = self.filenames_fingerprints

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

        self.db.update_mtimes(get_new_mtimes(self.source_tree, checksum_hits))
        self.db.update_mtimes(get_new_mtimes(self.source_tree, fingerprint_hits))

    @property
    def nodes_classes_modules_avg_durations(self) -> dict:
        stats = defaultdict(lambda: {"node_count": 0, "sum_duration": 0})

        for node_id, report in self.all_nodes.items():
            if report:
                class_name = get_node_class_name(node_id)
                module_name = get_node_module_name(node_id)

                stats[node_id]["node_count"] += 1
                stats[node_id]["sum_duration"] = sum(report["durations"].values())
                if class_name:
                    stats[class_name]["node_count"] += 1
                    stats[class_name]["sum_duration"] += stats[node_id]["sum_duration"]
                stats[module_name]["node_count"] += 1
                stats[module_name]["sum_duration"] += stats[node_id]["sum_duration"]

        avg_durations = {}
        for key, stats in stats.items():
            avg_durations[key] = stats["sum_duration"] / stats["node_count"]

        return avg_durations


def get_new_mtimes(filesystem, hits):

    for hit in hits:
        module = filesystem.get_file(hit[0])
        if module:
            yield module.mtime, string_checksum(module.source_code), hit[3]


def get_node_class_name(node_id):

    if len(node_id.split("::")) > 2:
        return node_id.split("::")[1]
    else:
        return None


def get_node_module_name(node_id):
    return node_id.split("::")[0]


class Testmon(object):
    coverage_stack = []

    def __init__(self, rootdir="", testmon_labels=None, cov_plugin=None):
        if testmon_labels is None:
            testmon_labels = {"singleprocess"}
        self.rootdir = rootdir
        self.testmon_labels = testmon_labels
        self.cov = None
        self.sub_cov_file = None
        self.setup_coverage(not ("singleprocess" in testmon_labels), cov_plugin)

    def setup_coverage(self, subprocess, cov_plugin=None):
        params = {
            "include": [os.path.join(self.rootdir, "*")],
            "omit": _get_python_lib_paths(),
        }

        self.cov = Coverage(data_file=self.sub_cov_file, config_file=False, **params)
        self.cov._warn_no_data = False

    def start(self):

        Testmon.coverage_stack.append(self.cov)
        self.cov.erase()
        self.cov.start()

    def stop(self):
        self.cov.stop()
        if Testmon.coverage_stack:
            Testmon.coverage_stack.pop()

    def stop_and_process(self, testmon_data: TestmonData, nodeid):
        self.stop()
        if self.sub_cov_file:
            self.cov.combine()
        measured_files = get_measured_relfiles(
            self.rootdir, self.cov, home_file(nodeid)
        )

        node_fingerprints = testmon_data.get_nodes_fingerprints(measured_files)

        node_fingerprints.append(
            {
                "filename": LIBRARIES_KEY,
                "checksum": testmon_data.libraries,
                "mtime": None,
                "fingerprint": encode_lines([testmon_data.libraries]),
            }
        )
        return node_fingerprints

    def save_fingerprints(self, testmon_data, nodeid, node_fingerprints, result):
        testmon_data.db.insert_node_fingerprints(
            nodeid,
            node_fingerprints,
            result,
        )

    def close(self):
        if self.sub_cov_file:
            os.remove(self.sub_cov_file + "_rc")
        os.environ.pop("COVERAGE_PROCESS_START", None)


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
