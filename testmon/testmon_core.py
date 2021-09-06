import hashlib
import os
import random
from typing import TypeVar

import pkg_resources
import sys
import textwrap
from packaging import version
from collections import defaultdict

import coverage
from coverage import Coverage

from testmon import db

from testmon.process_code import (
    read_file_with_checksum,
    file_has_lines,
    create_fingerprints,
    encode_lines,
)
from testmon.process_code import Module, checksums_to_blob

T = TypeVar("T")

LIBRARIES_KEY = "/libraries_checksum_testmon_name"

CHECKUMS_ARRAY_TYPE = "I"
DB_FILENAME = ".testmondata"


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


def check_fingerprint(disk, record: db.ChangedFileData):
    file = record.file_name
    fingerprint = record.checksums

    module = disk.get_file(file)
    return module and file_has_lines(module.full_lines, fingerprint)


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
    files = {test_file: set()}
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


class TestmonData(object):
    def __init__(self, rootdir="", environment=None, libraries=None):

        self.environment = environment if environment else "default"
        self.rootdir = rootdir
        self.unstable_files = None
        self.source_tree = SourceTree(rootdir=self.rootdir)
        if libraries == None:
            libraries = ", ".join(sorted(str(p) for p in pkg_resources.working_set))

        self.libraries = libraries

        self.connection = None
        self.init_connection()

    def init_connection(self):
        self.datafile = os.environ.get(
            "TESTMON_DATAFILE", os.path.join(self.rootdir, DB_FILENAME)
        )

        self.db = db.DB(self.datafile, self.environment)

    def close_connection(self):
        if self.connection:
            self.connection.close()

    @cached_property
    def filenames_fingerprints(self):
        return self.db.filenames_fingerprints()

    @property
    def all_files(self):
        return {row["file_name"] for row in self.filenames_fingerprints}

    @cached_property
    def all_nodes(self):
        return self.db.all_nodes()

    def node_data_from_cov(self, measured_files, default=None):
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

    def sync_db_fs_nodes(self, retain):
        collected = retain.union(set(self.stable_nodeids))
        with self.db as db:
            add = collected - set(self.all_nodes)

            for nodeid in add:
                if is_python_file(home_file(nodeid)):
                    db.insert_node_fingerprints(
                        nodeid=nodeid,
                        fingerprint_records=(
                            {
                                "filename": home_file(nodeid),
                                "fingerprint": checksums_to_blob(
                                    encode_lines("0match")
                                ),
                                "mtime": None,
                                "checksum": None,
                            },
                        ),
                    )
            db.delete_nodes(set(self.all_nodes) - collected)

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

    def node_data2records(self, nodedata):
        fingerprint_records = []
        for filename in nodedata:
            module = self.source_tree.get_file(filename)
            fingerprint_records.append(
                {
                    "filename": filename,
                    "mtime": module.mtime,
                    "checksum": module.checksum,
                    "fingerprint": checksums_to_blob(nodedata[filename]),
                }
            )
        return fingerprint_records


def get_new_mtimes(filesystem, hits):

    for hit in hits:
        module = filesystem.get_file(hit[0])
        if module:
            yield module.mtime, module.checksum, hit[3]


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

    def stop_and_save(self, testmon_data: TestmonData, nodeid, result):
        self.stop()
        if hasattr(self, "sub_cov_file"):
            self.cov.combine()
        measured_files = get_measured_relfiles(
            self.rootdir, self.cov, home_file(nodeid)
        )
        node_data = testmon_data.node_data_from_cov(measured_files)
        nodes_fingerprints = testmon_data.node_data2records(node_data)
        nodes_fingerprints.append(
            {
                "filename": LIBRARIES_KEY,
                "checksum": testmon_data.libraries,
                "mtime": None,
                "fingerprint": checksums_to_blob(
                    encode_lines([testmon_data.libraries])
                ),
            }
        )
        testmon_data.db.insert_node_fingerprints(
            nodeid,
            nodes_fingerprints,
            result,
        )

    def close(self):
        if hasattr(self, "sub_cov_file"):
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
