import gzip
import hashlib
import os
import random
import sys
import sysconfig
import textwrap
import zlib
from functools import lru_cache
from collections import defaultdict
import http.client
import xmlrpc.client
from xml.parsers.expat import ExpatError
from xmlrpc.client import ServerProxy

from typing import TypeVar

try:
    from pytest_cov.plugin import CovPlugin
except ImportError:
    pass
import pytest
from coverage import Coverage, CoverageData
from coverage.exceptions import CoverageException

from testmon import db
from testmon import TESTMON_VERSION as TM_CLIENT_VERSION
from testmon.common import (
    get_logger,
    get_system_packages,
    drop_patch_version,
    git_current_head,
    git_heads,
)

from testmon.process_code import (
    match_fingerprint,
    create_fingerprint,
    methods_to_checksums,
    get_source_sha,
    Module,
)

from testmon.common import DepsNOutcomes, TestExecutions
from testmon.transports import Transport, Transports

T = TypeVar("T")

TEST_BATCH_SIZE = 250

CHECKUMS_ARRAY_TYPE = "I"
DB_FILENAME = ".testmondata"

logger = get_logger(__name__)


def get_data_file_path():
    return os.environ.get("TESTMON_DATAFILE", DB_FILENAME)


def home_file(test_execution_name):
    return test_execution_name.split("::", 1)[0]


def not_run_yet(test_names):
    """Records for tests without a result: their fingerprint matches no file, so they run."""
    return {
        test_name: {
            "deps": (
                {
                    "filename": home_file(test_name),
                    "method_checksums": methods_to_checksums(["0match"]),
                    "mtime": None,
                    "fsha": None,
                },
            )
        }
        for test_name in test_names
        if is_python_file(home_file(test_name))
    }


def is_python_file(file_path):
    return file_path[-3:] == ".py"


class TestmonException(Exception):
    pass


class SourceTree:
    """
    - reads files from file_system and caches them in memory
      (if the file was once read, let's use the on memory
      copy for further operations. Also caches the mtime.)
    - store rootdir and convert between relative and absolute paths
    - implement the check if the file is changed based on mtime, fsha.
    - implement the ckeck if the node is stable based on fingerprint
    - mockability (unit tests without filesystem, check if the file is changed
      based on mtime, fsha)
    """

    def __init__(self, rootdir, packages=None):
        self.rootdir = rootdir
        self.packages = packages
        self.cache: dict = {}

    def get_file(self, filename):
        if filename not in self.cache:
            code, fsha = get_source_sha(directory=self.rootdir, filename=filename)
            if fsha:
                try:
                    fs_mtime = os.path.getmtime(os.path.join(self.rootdir, filename))
                    self.cache[filename] = Module(
                        source_code=code,
                        mtime=fs_mtime,
                        ext=filename.rsplit(".", 1)[1],
                        fs_fsha=fsha,
                        filename=filename,
                        rootdir=self.rootdir,
                    )
                except FileNotFoundError:
                    self.cache[filename] = None
            else:
                self.cache[filename] = None
        return self.cache[filename]


def check_mtime(file_system: SourceTree, record):
    absfilename = os.path.join(file_system.rootdir, record["filename"])

    cache_module = file_system.cache.get(record["filename"], None)
    try:
        fs_mtime = cache_module.mtime if cache_module else os.path.getmtime(absfilename)
    except OSError:
        return False
    return record["mtime"] == fs_mtime


def check_fsha(file_system, record):
    cache_module = file_system.get_file(record["filename"])
    fs_fsha = cache_module.fs_fsha if cache_module else None

    return record["fsha"] == fs_fsha


def check_fingerprint(
    disk, record: db.ChangedFileData
):  # filename name method_fshas id failed
    file = record[0]
    fingerprint = record[2]

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


@lru_cache(maxsize=1000)
def should_include(cov, filename):
    return cov._should_trace(str(filename), None).trace


def collect_mhashes(source_tree, new_changed_file_data):
    files_mhashes = {}
    for filename in new_changed_file_data:
        module = source_tree.get_file(filename)
        files_mhashes[filename] = module.method_checksums if module else None
    return files_mhashes


# Whatever a call to testmon.net can fail with: no connection, a reset, a timeout, TLS (all
# OSError), an HTTP error such as 502 or a server-side exception (xmlrpc.client.Error), a broken
# or non-XML response, a broken gzip response (zlib.error, EOFError; a bad header is an OSError).
REMOTE_ERRORS = (
    OSError,
    xmlrpc.client.Error,
    http.client.HTTPException,
    ExpatError,
    zlib.error,
    EOFError,
)
REMOTE_TIMEOUT = 60  # seconds, for the connect and for each read
GZIP_THRESHOLD = 1024  # bytes; a larger request is sent compressed


def timeout_transport(url, headers=()):
    """An xmlrpc transport for `url` that gives up after REMOTE_TIMEOUT instead of hanging.

    ServerProxy ignores its own `headers` when given a transport, so they come here.
    """
    base = (
        xmlrpc.client.SafeTransport
        if url.startswith("https")
        else xmlrpc.client.Transport
    )

    class TimeoutTransport(base):
        gzip_requests = False  # set once the server announced that it reads them

        def make_connection(self, host):
            connection = super().make_connection(host)
            connection.timeout = REMOTE_TIMEOUT
            return connection

        def send_content(self, connection, request_body):
            if self.gzip_requests and len(request_body) > GZIP_THRESHOLD:
                connection.putheader("Content-Encoding", "gzip")
                request_body = gzip.compress(request_body, compresslevel=6)
            super().send_content(connection, request_body)

    return TimeoutTransport(headers=headers)


class RemoteDB:
    """testmon.net (an xmlrpc proxy) behind the interface of db.DB.

    Until the tests to run are determined, a failed call raises and TestmonData falls back to
    the local .testmondata. After that (`lenient`) the pytest run must go on: the first failure
    is logged, nothing more is sent, and every call returns "no data".
    """

    NO_DATA = {
        "all_test_executions": dict,
        "fetch_saving_stats": lambda: (0,) * 8,
    }

    def __init__(self, proxy):
        self._proxy = proxy
        self.lenient = False
        self.failed = False

    def __getattr__(self, name):
        def call(*args):
            if not self.failed:
                try:
                    return getattr(self._proxy, name)(*args)
                except REMOTE_ERRORS as exc:
                    if not self.lenient:
                        raise
                    self.failed = True
                    logger.error(
                        "%r error when communicating with testmon.net. The run continues,"
                        " its results are not saved.",
                        exc,
                    )
            return self.NO_DATA.get(name, lambda: None)()

        return call

    def use(self, capabilities):
        """Switch on what the server announced in the result of initiate_execution."""
        if capabilities.get("gzip_requests") and isinstance(self._proxy, ServerProxy):
            self._proxy("transport").gzip_requests = True

    def close(self):
        try:
            if isinstance(self._proxy, ServerProxy):
                self._proxy("close")()  # attribute access would be a remote call
            else:
                self._proxy.close()
        except REMOTE_ERRORS:
            pass


class TestmonData:  # pylint: disable=too-many-instance-attributes
    __test__ = False

    def __init__(
        self,
        rootdir,
        database=None,
        readonly=False,
    ):
        self.rootdir = rootdir
        self.source_tree = SourceTree(rootdir=self.rootdir)

        if database:
            self.db = RemoteDB(database)  # pylint: disable=invalid-name
        else:
            self.db = db.DB(
                os.path.join(self.rootdir, get_data_file_path()), readonly=readonly
            )  # pylint: disable=invalid-name

        # Initialize instance variables (will be set by init methods)
        self.environment = None
        self.exec_id = None
        self.system_packages_change = None
        self.files_of_interest = None
        self.all_files = {}
        self.unstable_test_names = None
        self.unstable_files = None
        self.stable_test_names = None
        self.stable_files = None
        self.failing_tests = None
        self.failed_test_names = None
        self.transports = None

    @classmethod
    def for_local_run(  # pylint: disable=too-many-arguments
        cls,
        rootdir,
        database=None,
        environment=None,
        system_packages=None,
        python_version=None,
        mirror=False,
    ):
        instance = cls(rootdir, database=database, readonly=False)
        instance._init_for_local_run(
            environment, system_packages, python_version, mirror
        )
        return instance

    def _init_for_local_run(
        self,
        environment=None,
        system_packages=None,
        python_version=None,
        mirror=False,
    ):
        """Internal method to initialize for local run."""
        self.environment = environment if environment else "default"

        if system_packages is None:
            system_packages = get_system_packages()
        system_packages = drop_patch_version(system_packages)

        if not python_version:
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        self._initiate_args = (self.environment, system_packages, python_version)
        # Only testmon.net uses the commits, so only then `git` is asked for them.
        heads = git_heads(self.rootdir) if isinstance(self.db, RemoteDB) else []
        # Initiate execution (controller or single process)
        try:
            result = self.db.initiate_execution(
                *self._initiate_args,
                {
                    "tm_client_version": TM_CLIENT_VERSION,
                    "git_head_sha": heads[0] if heads else git_current_head(),
                    # A server that does not know a key ignores it.
                    "git_heads": heads,
                    "ci": os.environ.get("CI"),
                },
            )
            self._set_execution(result)
            if isinstance(self.db, RemoteDB):
                self.db.use(result)
        except REMOTE_ERRORS as exc:
            if not isinstance(self.db, RemoteDB):
                raise
            self._fall_back_to_local(exc)
        else:
            try:
                self.transports = self._open_transports(mirror)
            except Exception:
                self._close_storage()  # testmon.net is open, and nobody else closes it
                raise

    def _open_transports(self, mirror) -> Transports:
        """Write to the storage in use; with `mirror`, testmon.net also to .testmondata."""
        transports = [Transport(self.db, self.exec_id)]
        if mirror and isinstance(self.db, RemoteDB):
            local = db.DB(os.path.join(self.rootdir, get_data_file_path()))
            local_exec = local.initiate_execution(*self._initiate_args, {})
            transports.append(Transport(local, local_exec["exec_id"]))
        return Transports(transports)

    def _close_storage(self):
        """Close what the run writes to; before the transports exist, only the database."""
        transports, self.transports = self.transports, None
        database, self.db = self.db, None
        if transports is not None:
            transports.close()
        elif database is not None:
            database.close()

    def _fall_back_to_local(self, exc):
        logger.error(
            "%r error when communicating with testmon.net. (falling back to"
            " .testmondata locally)",
            exc,
        )
        self._close_storage()
        self.db = db.DB(os.path.join(self.rootdir, get_data_file_path()))
        self._set_execution(self.db.initiate_execution(*self._initiate_args, {}))
        self.transports = self._open_transports(mirror=False)

    def _set_execution(self, result):
        self.exec_id = result["exec_id"]
        self.system_packages_change = result["packages_changed"]
        self.files_of_interest = result["filenames"]

    @classmethod
    def for_worker(  # pylint: disable=too-many-arguments
        cls,
        rootdir,
        exec_id,
        database=None,
        system_packages_change=None,
        files_of_interest=None,
        environment=None,
    ):
        instance = cls(rootdir, database=database, readonly=True)
        instance._init_for_worker(
            exec_id, system_packages_change, files_of_interest, environment
        )
        return instance

    def _init_for_worker(
        self,
        exec_id,
        system_packages_change=None,
        files_of_interest=None,
        environment=None,
    ):
        """Internal method to initialize for worker run."""
        self.exec_id = exec_id
        self.system_packages_change = system_packages_change
        self.files_of_interest = files_of_interest
        if environment:
            self.environment = environment
        elif not hasattr(self, "environment") or self.environment is None:
            self.environment = "default"

    @property
    def new_db(self):
        # Only local DB instances have file_created attribute
        if isinstance(self.db, db.DB):
            return self.db.file_created
        return False

    def close_connection(self):
        """Release the storage: the sqlite connection, or the transport of a tmnet proxy.

        Idempotent. Tests that inspect the data after a run reopen it (see tests/lib4tests.py).
        """
        self._close_storage()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close_connection()

    @property
    def all_tests(self):
        return self.db.all_test_executions(self.exec_id)

    def get_tests_fingerprints(self, nodes_files_lines, reports) -> TestExecutions:
        test_executions_fingerprints = {}
        for context in nodes_files_lines:
            deps_n_outcomes: DepsNOutcomes = {"deps": []}

            for filename, covered in nodes_files_lines[context].items():
                if os.path.exists(os.path.join(self.rootdir, filename)):
                    module = self.source_tree.get_file(filename)
                    fingerprint = create_fingerprint(module, covered)
                    deps_n_outcomes["deps"].append(
                        {
                            "filename": filename,
                            "mtime": module.mtime,
                            "fsha": module.fs_fsha,
                            "method_checksums": fingerprint,
                        }
                    )

            deps_n_outcomes.update(process_result(reports[context]))
            deps_n_outcomes["forced"] = context in self.stable_test_names and (
                context not in self.failing_tests
            )
            test_executions_fingerprints[context] = deps_n_outcomes
        return test_executions_fingerprints

    def sync_db_fs_tests(self, retain):
        collected = retain.union(set(self.stable_test_names))
        known = set(self.all_tests)
        test_execution_file_fps = not_run_yet(collected - known)
        if test_execution_file_fps:
            self.save_test_execution_file_fps(test_execution_file_fps)
        self.transports.insert_tests_unknown_to_mirrors(collected | known, not_run_yet)

        self.transports.delete_test_executions(self._tests_to_forget(retain, collected))

    def _tests_to_forget(self, retain, collected):
        """The known tests that are neither collected nor stable: they are gone.

        Except in a file this run may not have collected at all (pytest was started for
        another path) which still has stable tests. Forgetting only the affected tests of
        such a file would leave it with stable tests alone: it would be skipped at collection
        from then on, and the forgotten tests would never run with the change that affected
        them.
        """
        collected_files = {home_file(test_name) for test_name in retain}
        files_with_stable_tests = {
            home_file(test_name) for test_name in self.stable_test_names
        }
        to_forget = []
        for test_name in set(self.all_tests) - collected:
            file = home_file(test_name)
            if (
                file in collected_files
                or file not in files_with_stable_tests
                or not os.path.exists(os.path.join(self.rootdir, file))
            ):
                to_forget.append(test_name)
        return to_forget

    def determine_stable(self):
        """Decide which tests are affected; with testmon.net, any failure means .testmondata."""
        if not isinstance(self.db, RemoteDB):
            self._determine_stable()
            return
        try:
            self._determine_stable()
        except REMOTE_ERRORS as exc:
            self._fall_back_to_local(exc)
            self._determine_stable()
        else:
            self.db.lenient = True

    def _determine_stable(self):
        files_fshas = {}
        for filename in self.files_of_interest:
            module = self.source_tree.get_file(filename)
            if module:
                files_fshas[filename] = module.fs_fsha

        # Compare the fshas from disk to the fshas in the database and get files
        # where the fsha is not in database.
        new_changed_file_data = self.db.fetch_unknown_files(files_fshas, self.exec_id)

        # Get the mhashes for the files from above
        files_mhashes = collect_mhashes(self.source_tree, new_changed_file_data)

        tests = self.db.determine_tests(self.exec_id, files_mhashes)
        affected_tests, self.failing_tests = tests["affected"], tests["failing"]

        self.all_files = set(self.db.filenames(self.exec_id))
        self.unstable_test_names = set()
        self.unstable_files = set()

        for fingerprint_miss in affected_tests:
            self.unstable_test_names.add(fingerprint_miss)
            self.unstable_files.add(fingerprint_miss.split("::", 1)[0])

        # Everything the selection needs is read here, while a failure of testmon.net still
        # means falling back; a later, lenient read would return "no tests failed".
        all_tests = self.all_tests
        self.failed_test_names = {
            test_name for test_name, result in all_tests.items() if result["failed"]
        }
        self.stable_test_names = set(all_tests) - self.unstable_test_names
        self.stable_files = set(self.all_files) - self.unstable_files

    @property
    def avg_durations(self) -> dict:
        stats = defaultdict(lambda: {"test_execution": 0, "sum_duration": 0})

        for (
            test_execution_id,
            report,
        ) in self.all_tests.items():  # pylint: disable=no-member
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

    def save_test_execution_file_fps(self, test_executions_fingerprints):
        self.transports.insert_test_file_fps(test_executions_fingerprints)

    def finish_execution(self, duration, select):
        self.transports.finish_execution(duration, select)

    def fetch_saving_stats(self, select):
        return self.db.fetch_saving_stats(self.exec_id, select)


def get_new_mtimes(filesystem, hits):
    """hits: [(filename, _, _, fingerprint_id)]"""
    try:
        for hit in hits:
            module = filesystem.get_file(hit[0])
            if module:
                yield module.mtime, module.fs_fsha, hit[3]
    except KeyError:
        for hit in hits:
            module = filesystem.get_file(hit["filename"])
            if module:
                yield module.mtime, module.fs_fsha, hit["fingerprint_id"]


def get_test_execution_class_name(node_id):
    if len(node_id.split("::")) > 2:
        return node_id.split("::")[1]
    return None


def get_test_execution_module_name(node_id):
    return node_id.split("::")[0]


@lru_cache(1000)
def cached_relpath(path, basepath):
    return os.path.relpath(path, basepath).replace(os.sep, "/")


# coverage 7.10+ defaults to the sys.monitoring core on CPython 3.14+. That core
# doesn't support dynamic contexts: sys.monitoring disables a line event once the
# line has been recorded, so a line executed by several tests of one batch is
# attributed to the first test only and the other tests lose the dependency.
# testmon relies on contexts_by_lineno, so it needs the C tracer.
COVERAGE_CORE = "ctrace"


def force_context_capable_core(cov: Coverage):
    try:
        cov.set_option("run:core", COVERAGE_CORE)
    except CoverageException:
        # coverage < 7.10 has no core option and never defaults to sys.monitoring.
        pass


class TestmonCollector:
    coverage_stack: [Coverage] = []

    def __init__(
        self, rootdir, testmon_labels=None, cov_plugin=None
    ):  # TODO remove cov_plugin
        try:
            from testmon.testmon_core import (  # pylint: disable=import-outside-toplevel
                Testmon as UberTestmon,
            )

            TestmonCollector.coverage_stack: [Coverage] = UberTestmon.coverage_stack
        except ImportError:
            pass
        if testmon_labels is None:
            testmon_labels = {"singleprocess"}
        self.rootdir = rootdir
        self.testmon_labels = testmon_labels
        self.cov: Coverage = None
        self.sub_cov_file = None
        self.cov_plugin: CovPlugin = cov_plugin
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
            "omit": {
                os.path.join(value, "*")
                for key, value in sysconfig.get_paths().items()
                if key.endswith("lib")
            },
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
            # params["omit"] = cov.config.run_omit
            if cov.config.branch:
                raise TestmonException(
                    "testmon doesn't support simultaneous run with pytest-cov when "
                    "branch coverage is on. Please disable branch coverage."
                )
        if subprocess:
            self.setup_subprocess(params["include"])
        self.cov = Coverage(data_file=self.sub_cov_file, config_file=False, **params)
        self.cov._warn_no_data = False
        force_context_capable_core(self.cov)
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
                (
                    "Exiting pytest!!!! This test corrupts Testmon.coverage_stack:"
                    f" {self._test_name} {self.check_stack},"
                    f" {TestmonCollector.coverage_stack}"
                ),
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
        cov_data: CoverageData = self.cov.get_data()
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
            os.environ.pop("COVERAGE_CORE", None)
        os.environ.pop("COVERAGE_PROCESS_START", None)
        self.cov = None
        if TestmonCollector.coverage_stack:
            TestmonCollector.coverage_stack[-1].start()

    def setup_subprocess(self, includes):
        # This can be redone to use functionality from pytest-cov
        if not os.path.exists(".tmontmp"):
            os.makedirs(".tmontmp")
        self.sub_cov_file = os.path.abspath(
            ".tmontmp/.testmoncoverage" + str(random.randint(0, 1000000))
        )
        with open(self.sub_cov_file + "_rc", "w", encoding="utf-8") as subprocess_rc:
            rc_content = textwrap.dedent(
                """\
                    [run]
                    data_file = {}
                    include = {}
                    parallel=True
                    """
            ).format(
                self.sub_cov_file,
                "\n ".join(includes),
            )
            subprocess_rc.write(rc_content)
        os.environ["COVERAGE_PROCESS_START"] = self.sub_cov_file + "_rc"
        os.environ["COVERAGE_CORE"] = COVERAGE_CORE


def eval_environment(environment, **kwargs):
    if not environment:
        return ""

    def md5(string):
        return hashlib.md5(string.encode()).hexdigest()

    eval_globals = {"os": os, "sys": sys, "hashlib": hashlib, "md5": md5}
    eval_globals.update(kwargs)

    try:
        return str(eval(environment, eval_globals))
    except Exception as error:  # pylint: disable=broad-except
        return repr(error)


def process_result(result):
    failed = any(r.outcome == "failed" for r in result.values())
    duration = sum(value.duration for value in result.values())
    return {"failed": failed, "duration": duration}
