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

from testmon import db
from testmon.process_code import (
    read_file_with_checksum,
    match_fingerprint,
    create_fingerprint,
    methods_to_checksums,
    string_checksum,
    Module,
)


TEST_BATCH_SIZE = 100

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


def home_file(test_execution_name):
    return test_execution_name.split("::", 1)[0]


def is_python_file(file_path):
    return file_path[-3:] == ".py"


class TestmonException(Exception):
    pass


class SourceTree:
    def __init__(self, rootdir="", packages=None):
        self.rootdir = rootdir
        self.packages = packages
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
                    mtime=fs_mtime,
                    ext=filename.rsplit(".", 1)[1],
                    fs_checksum=checksum,
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


@lru_cache(maxsize=1000)
def should_include(cov, filename):
    return cov._should_trace(str(filename), None).trace


class TestmonData:
    def __init__(
        self,
        rootdir="",
        environment=None,
        system_packages=None,
        remote_db=None,
        datafile=None,
        python_version=None,
    ):
        self.environment = environment if environment else "default"
        self.rootdir = rootdir
        self.unstable_files = None
        self.source_tree = SourceTree(rootdir=self.rootdir)
        if system_packages is None:
            system_packages = ", ".join(
                sorted(str(p) for p in pkg_resources.working_set or [])
            )
        self.connection = None
        self.datafile = datafile or get_data_file_path(self.rootdir)
        self.remote_db = None

        if remote_db:
            self.db = remote_db
        else:
            self.db = db.DB(self.datafile)

        if not python_version:
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        result = self.db.initiate_execution(
            self.environment, system_packages, python_version
        )

        self.exec_id = result["exec_id"]
        self.all_files = set(result["filenames"])

        self.system_packages_change = result["packages_changed"]
        self.unstable_test_names = set()
        self.unstable_files = set()
        self.stable_test_names = set()
        self.stable_files = set()

    def close_connection(self):
        if self.connection:
            self.connection.close()

    @property
    def all_tests(self):
        return self.db.all_test_executions(self.exec_id)

    def get_tests_fingerprints(self, files_lines):
        tests_fingerprints = []

        for filename, covered in files_lines.items():
            if os.path.exists(os.path.join(self.rootdir, filename)):
                module = self.source_tree.get_file(filename)
                fingerprint = create_fingerprint(module, covered)
                tests_fingerprints.append(
                    {
                        "filename": filename,
                        "mtime": module.mtime,
                        "checksum": string_checksum(module.source_code),
                        "method_checksums": fingerprint,
                    }
                )
        return tests_fingerprints

    def sync_db_fs_tests(self, retain):
        collected = retain.union(set(self.stable_test_names))
        with self.db as database:
            add = collected - set(self.all_tests)

            test_execution_file_fps = {
                test_name: (
                    {
                        "filename": home_file(test_name),
                        "method_checksums": methods_to_checksums(["0match"]),
                        "mtime": None,
                        "checksum": None,
                    },
                )
                for test_name in add
                if is_python_file(home_file(test_name))
            }
            if test_execution_file_fps:
                self.save_test_execution_file_fps(test_execution_file_fps)

            to_delete = list(set(self.all_tests) - collected)
            database.delete_test_executions(to_delete, self.exec_id)

    def determine_stable(self):

        files_checksums = {}
        for filename in self.all_files:
            module = self.source_tree.get_file(filename)
            if module:
                files_checksums[filename] = module.fs_checksum

        new_changed_file_data = self.db.new_fetch_changed_file_data(
            files_checksums, self.exec_id
        )

        filenames_fingerprints = self.db.filenames_fingerprints(self.exec_id)

        _, checksum_misses = split_filter(
            self.source_tree, check_checksum, filenames_fingerprints
        )

        changed_file_data = self.db.fetch_changed_file_data(
            [checksum_miss["fingerprint_id"] for checksum_miss in (checksum_misses)],
            self.exec_id,
        )

        _, fingerprint_misses = split_filter(
            self.source_tree, check_fingerprint, changed_file_data
        )

        _, new_fingerprint_misses = split_filter(
            self.source_tree, check_fingerprint, new_changed_file_data
        )

        fingerprint_misses = new_fingerprint_misses

        self.unstable_test_names = set()
        self.unstable_files = set()

        for fingerprint_miss in fingerprint_misses:
            self.unstable_test_names.add(fingerprint_miss[1])
            self.unstable_files.add(fingerprint_miss[1].split("::", 1)[0])

        self.stable_test_names = set(self.all_tests) - self.unstable_test_names
        self.stable_files = set(self.all_files) - self.unstable_files

        _, new_fingerprint_misses = split_filter(
            self.source_tree, check_fingerprint, new_changed_file_data
        )

        assert fingerprint_misses == new_fingerprint_misses

    @property
    def avg_durations(self):
        stats = defaultdict(lambda: {"test_execution": 0, "sum_duration": 0})

        for (
            test_execution_id,
            report,
        ) in self.all_tests.items():
            if report:
                class_name = get_test_execution_class_name(test_execution_id)
                module_name = get_test_execution_module_name(test_execution_id)

                stats[test_execution_id]["test_execution"] += 1
                stats[test_execution_id]["sum_duration"] = report.get("duration") or 0
                if class_name:
                    stats[class_name]["test_execution"] += 1
                    stats[class_name]["sum_duration"] += stats[test_execution_id][
                        "sum_duration"
                    ]
                stats[module_name]["test_execution"] += 1
                stats[module_name]["sum_duration"] += stats[test_execution_id][
                    "sum_duration"
                ]

        durations = defaultdict(lambda: 0)
        for key, stats in stats.items():
            durations[key] = stats["sum_duration"] / stats["test_execution"]

        return durations

    def save_test_execution_file_fps(self, test_executions_fingerprints, fa_durs=None):
        if self.remote_db:
            self.remote_db.tmnet_insert_test_files_fps(
                test_executions_fingerprints, fa_durs
            )
        self.db.insert_test_file_fps(
            test_executions_fingerprints, fa_durs, self.exec_id
        )


def nofili2fingerprints(nodes_files_lines, testmon_data):

    test_executions_fingerprints = {}
    for context in nodes_files_lines:
        node_fingerprints = testmon_data.get_tests_fingerprints(
            nodes_files_lines[context]
        )

        test_executions_fingerprints[context] = node_fingerprints
    return test_executions_fingerprints


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


def get_test_execution_class_name(node_id):
    if len(node_id.split("::")) > 2:
        return node_id.split("::")[1]
    return None


def get_test_execution_module_name(node_id):
    return node_id.split("::")[0]


@lru_cache(1000)
def cached_relpath(path, basepath):
    return os.path.relpath(path, basepath).replace(os.sep, "/")


class TestmonCollector:
    coverage_stack = []

    def __init__(self, rootdir="", testmon_labels=None, cov_plugin=None):
        try:
            from testmon.testmon_core import (
                Testmon as UberTestmon,
            )

            TestmonCollector.coverage_stack = UberTestmon.coverage_stack
        except ImportError:
            pass
        if testmon_labels is None:
            testmon_labels = {"singleprocess"}
        self.rootdir = rootdir
        self.testmon_labels = testmon_labels
        self.cov = None
        self.sub_cov_file = None
        self.cov_plugin = cov_plugin
        self._test_name = None
        self._next_test_name = None
        self.batched_test_names = set()
        self.check_stack = []
        self.is_started = False
        self._interrupted_at = None

    def start_cov(self):
        if not self.cov._started:
            TestmonCollector.coverage_stack.append(self.cov)
            self.cov.start()

    def stop_cov(self):
        if self.cov is None:
            return
        assert self.cov in TestmonCollector.coverage_stack
        if TestmonCollector.coverage_stack:
            while TestmonCollector.coverage_stack[-1] != self.cov:
                cov = TestmonCollector.coverage_stack.pop()
                cov.stop()
        if self.cov._started:
            self.cov.stop()
            TestmonCollector.coverage_stack.pop()
        if TestmonCollector.coverage_stack:
            TestmonCollector.coverage_stack[-1].start()

    def setup_coverage(self, subprocess=False):
        params = {
            "include": [os.path.join(self.rootdir, "*")],
            "omit": _get_python_lib_paths(),
        }

        if self.cov_plugin and self.cov_plugin._started:
            cov = self.cov_plugin.cov_controller.cov
            TestmonCollector.coverage_stack.append(cov)
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
        if TestmonCollector.coverage_stack:
            TestmonCollector.coverage_stack[-1].stop()

        self.start_cov()

    def start_testmon(self, test_name, next_test_name=None):
        self._next_test_name = next_test_name

        self.batched_test_names.add(test_name)
        if self.cov is None:
            self.setup_coverage()

        self.start_cov()
        self._test_name = test_name
        self.cov.switch_context(test_name)
        self.check_stack = TestmonCollector.coverage_stack.copy()

    def discard_current(self):
        self._interrupted_at = self._test_name

    def get_batch_coverage_data(self):

        if self.check_stack != TestmonCollector.coverage_stack:
            pytest.exit(
                f"Exiting pytest!!!! This test corrupts Testmon.coverage_stack: "
                f"{self._test_name} {self.check_stack}, {TestmonCollector.coverage_stack}",
                returncode=3,
            )

        nodes_files_lines = {}

        if self.cov and (
            len(self.batched_test_names) >= TEST_BATCH_SIZE
            or self._next_test_name is None
            or self._interrupted_at
        ):
            self.cov.stop()
            nodes_files_lines, lines_data = self.get_nodes_files_lines(
                dont_include=self._interrupted_at
            )

            if (
                len(TestmonCollector.coverage_stack) > 1
                and TestmonCollector.coverage_stack[-1] == self.cov
            ):
                filtered_lines_data = {
                    file: data
                    for file, data in lines_data.items()
                    if should_include(TestmonCollector.coverage_stack[-2], file)
                }
                TestmonCollector.coverage_stack[-2].get_data().add_lines(
                    filtered_lines_data
                )

            self.cov.erase()
            self.cov.start()
            self.batched_test_names = set()
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
        self.batched_test_names.discard(dont_include)
        nodes_files_lines.pop("", None)
        for test_name in self.batched_test_names:
            if home_file(test_name) not in nodes_files_lines.setdefault(test_name, {}):
                nodes_files_lines[test_name].setdefault(home_file(test_name), {1})
        return nodes_files_lines, files_lines

    def close(self):
        if self.cov is None:
            return
        assert self.cov in TestmonCollector.coverage_stack
        if TestmonCollector.coverage_stack:
            while TestmonCollector.coverage_stack[-1] != self.cov:
                cov = TestmonCollector.coverage_stack.pop()
                cov.stop()
        if self.cov._started:
            self.cov.stop()
            TestmonCollector.coverage_stack.pop()
        if self.sub_cov_file:
            os.remove(self.sub_cov_file + "_rc")
        os.environ.pop("COVERAGE_PROCESS_START", None)
        self.cov = None
        if TestmonCollector.coverage_stack:
            TestmonCollector.coverage_stack[-1].start()


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
