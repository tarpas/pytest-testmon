import importlib
import os
import sys
import sqlite3
import copy
import pytest
import textwrap
import threading

from array import array
from collections import defaultdict
from inspect import getframeinfo, currentframe

from testmon.common import git_path, git_current_branch, git_current_head
from testmon.process_code import (
    Module,
    create_fingerprint_source,
    checksums_to_blob,
    methods_to_checksums,
    bytes_to_string_and_fsha,
)
from testmon.collector import make_collector
from testmon.collector.ctrace import CtraceCollector as CoreTestmon
from testmon.testmon_core import (
    TestmonData as CoreTestmonData,
    SourceTree,
    CHECKUMS_ARRAY_TYPE,
    is_python_file,
    check_mtime,
    check_fingerprint,
    check_fsha,
    get_new_mtimes,
    collect_mhashes,
    split_filter,
)

pytest_plugins = ("pytester",)

FINGERPRINT0 = create_fingerprint_source("", {1})
FINGERPRINT1 = create_fingerprint_source("FINGERPRINT1", {1})

FPF1 = create_fingerprint_source("F1", {1})
FPFA = create_fingerprint_source("FA", {1})
FPFA2 = create_fingerprint_source("FA2", {2})


class CoreTestmonDataForTest(CoreTestmonData):
    def __init__(self, database=None, environment=None, system_packages=None, **kwargs):
        # Use the classmethod to create and initialize
        instance = CoreTestmonData.for_local_run(
            rootdir="",
            database=database,
            environment=environment,
            system_packages=system_packages,
            **kwargs,
        )
        # Copy all attributes to self
        self.__dict__.update(instance.__dict__)

    def create_report(
        self, phases_count, duration, node_name, node_module, node_class=None
    ):
        name = "".join(
            [
                node_module,
                "::",
                f"{node_class}::{node_name}" if node_class else node_name,
            ]
        )

        self.write_fixture(name, {node_module: FINGERPRINT0}, False, duration)

    def write_fixture(self, node, files, failed=False, duration=0.1):
        records = []
        for filename in files:
            records.append(
                {
                    "method_checksums": files[filename],
                    "filename": filename,
                    "mtime": 1.0,
                    "fsha": "100",
                }
            )
            self.source_tree.cache[filename] = Module(
                source_code="FINGERPRINT1", fs_fsha="100", mtime=1.0
            )
        self.save_test_execution_file_fps(
            {node: {"deps": records, "failed": failed, "duration": duration}}
        )
        self.all_files = self.db.filenames(self.exec_id)


@pytest.fixture
def tmdata(testdir):
    with CoreTestmonDataForTest(system_packages="default") as tmdata:
        yield tmdata


@pytest.fixture
def git_repo(testdir):
    testdir.run("git", "init", ".")
    testdir.run("git", "config", "user.name", "Test .git")
    testdir.run("git", "config", "user.email", "test@git.com")
    testdir.run("git", "config", "init.defaultBranch", "main")
    testdir.makepyfile(testfile="'''Test content'''")
    testdir.run("git", "add", ".")
    testdir.run("git", "commit", "-m", "Test commit")


COLLECTORS = {"ctrace": CoreTestmon}
if sys.version_info >= (3, 12):
    from testmon.collector.sysmon import SysmonCollector

    COLLECTORS["sysmon"] = SysmonCollector


class TestMakeCollector:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("TESTMON_CORE", raising=False)
        expected = "sysmon" if sys.version_info >= (3, 12) else "ctrace"
        assert isinstance(make_collector(""), COLLECTORS[expected])

    @pytest.mark.parametrize("core", COLLECTORS)
    def test_forced(self, monkeypatch, core):
        monkeypatch.setenv("TESTMON_CORE", core)
        assert isinstance(make_collector(""), COLLECTORS[core])

    def test_unknown_value_uses_default(self, monkeypatch):
        monkeypatch.setenv("TESTMON_CORE", "nope")
        expected = "sysmon" if sys.version_info >= (3, 12) else "ctrace"
        assert isinstance(make_collector(""), COLLECTORS[expected])

    @pytest.mark.skipif(sys.version_info < (3, 12), reason="needs sys.monitoring")
    def test_no_free_tool_id_falls_back_to_ctrace(self, monkeypatch):
        import testmon.collector.sysmon  # pylint: disable=import-outside-toplevel

        monkeypatch.delenv("TESTMON_CORE", raising=False)
        monkeypatch.setattr(
            testmon.collector.sysmon, "search_free_tool_id", lambda: None
        )
        assert isinstance(make_collector(""), CoreTestmon)


class TestMisc(object):
    def test_is_python_file(self):
        assert is_python_file("/dir/file.py")
        assert is_python_file("f.py")
        assert not is_python_file("/notpy/file.p")

    def test_sqlite_assumption(self):
        assert array(CHECKUMS_ARRAY_TYPE).itemsize == 4

        checksums = methods_to_checksums(["1", "2"])

        blob = checksums_to_blob(checksums)

        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE a (c BLOB)")
        con.execute("INSERT INTO a VALUES (?)", [blob])

        cursor = con.execute("SELECT c FROM A")
        assert blob == cursor.fetchone()[0]

        cursor = con.execute("SELECT length(c) FROM A")
        assert cursor.fetchone()[0] == len(checksums) * 4
        con.close()

    def test_sqlite_assumption_foreign_key(self, tmdata):
        def test_execution_count(test_execution_id):
            return tmdata.db.con.execute(
                "SELECT count(*) FROM test_execution where id = ?",
                (test_execution_id,),
            ).fetchone()[0]

        record1 = {
            "filename": "test_a.py",
            "method_checksums": FINGERPRINT0,
            "mtime": None,
            "fsha": bytes_to_string_and_fsha(b"FINGERPRINT0")[1],
        }

        record2 = {
            "filename": "test_a.py",
            "method_checksums": FINGERPRINT1,
            "mtime": None,
            "fsha": bytes_to_string_and_fsha(b"FINGERPRINT1")[1],
        }
        tmdata.db.insert_test_file_fps(
            {"test_a.py::n1": {"deps": [record1], "failed": False, "duration": 0}},
            exec_id=tmdata.exec_id,
        )
        con = tmdata.db.con
        first_test_execution_id = con.execute(
            "SELECT id FROM test_execution"
        ).fetchone()[0]
        assert first_test_execution_id == 1

        tmdata.db.insert_test_file_fps(
            {"test_a.py::n2": {"deps": [record2], "failed": False, "duration": 0}},
            exec_id=tmdata.exec_id,
        )
        second_test_execution_id = con.execute(
            "SELECT max(id) FROM test_execution"
        ).fetchone()[0]
        assert second_test_execution_id == 2

        tmdata.db.insert_test_file_fps(
            {"test_a.py::n1": {"deps": [record1], "failed": False, "duration": 0}},
            exec_id=tmdata.exec_id,
        )
        third_test_execution_id = con.execute(
            "SELECT max(id) FROM test_execution"
        ).fetchone()[0]
        assert third_test_execution_id == 3

        assert first_test_execution_id != second_test_execution_id
        assert test_execution_count(first_test_execution_id) == 0
        assert test_execution_count(second_test_execution_id) == 1
        assert test_execution_count(third_test_execution_id) == 1
        tmdata.db.con.execute("DELETE FROM test_execution_file_fp")
        tmdata.db.con.execute("DELETE FROM test_execution")
        assert test_execution_count(second_test_execution_id) == 0

    def test_git_utilities(self, testdir, git_repo):
        assert git_path()
        assert git_current_head()
        assert git_current_branch()
        # let's go deeper
        cwd = os.getcwd()
        testdir.mkdir("subdir")
        os.chdir("subdir")  # testdir.chdir doesn't change dir
        assert cwd != os.getcwd()
        assert git_path() == str(testdir.tmpdir / ".git")

    def test_failed_git_utilities(self, testdir):
        assert git_path() == None
        assert git_current_branch() == None
        assert git_current_head() == None


class TestTestmonRecursive:
    @pytest.fixture
    def parent_testmon(self, testdir):
        parent_testmon = CoreTestmon(rootdir="parent_rootdir")
        yield parent_testmon
        parent_testmon.close()

    def test_filter_excluded_cov_data(self, testdir, parent_testmon):
        p = testdir.mkdir("child_rootdir").join("a.py")
        p.write("pass")

        parent_testmon.start_testmon("1")

        testmon = CoreTestmon(rootdir="child_rootdir")
        testmon.setup_coverage()
        testmon.start_testmon("2")
        testdir.inline_run("child_rootdir/a.py")
        assert testmon.cov.get_data().measured_files()
        testmon.close()

        parent_testmon.discard_current()
        assert not parent_testmon.cov.get_data().measured_files()

    @pytest.mark.parametrize("collector_class", COLLECTORS.values(), ids=COLLECTORS)
    def test_shared_line_recorded_for_every_test_in_batch(
        self, testdir, collector_class
    ):
        # coverage's sys.monitoring core (its default on CPython 3.14+) records a
        # line only for the first dynamic context that executes it. Every
        # collector must pick a core where every test of a batch gets its lines.
        testdir.makepyfile(shared_dep="def f(x):\n    return x + 1\n")
        testdir.syspathinsert()
        import shared_dep  # pylint: disable=import-error,import-outside-toplevel

        testmon = collector_class(rootdir=str(testdir.tmpdir))
        testmon.start_testmon("1", next_test_name="2")
        shared_dep.f(1)
        assert testmon.get_batch_coverage_data() == {}
        testmon.start_testmon("2", next_test_name=None)
        shared_dep.f(2)
        nodes_files_lines = testmon.get_batch_coverage_data()
        testmon.close()

        assert nodes_files_lines["1"]["shared_dep.py"] == {2}
        assert nodes_files_lines["2"]["shared_dep.py"] == {2}

    @pytest.mark.parametrize("collector_class", COLLECTORS.values(), ids=COLLECTORS)
    def test_one_line_function_recorded_for_every_test_in_batch(
        self, testdir, collector_class
    ):
        # On CPython 3.14+, re-arming a one-line function's LINE event with
        # set_local_events() doesn't bring it back: only the first test that
        # ran the lambda would get its line.
        testdir.makepyfile(one_line_dep="inc = lambda x: x + 1\n")
        testdir.syspathinsert()
        import one_line_dep  # pylint: disable=import-error,import-outside-toplevel

        testmon = collector_class(rootdir=str(testdir.tmpdir))
        results = {}
        for name, nxt in (("1", "2"), ("2", "3"), ("3", None)):
            testmon.start_testmon(name, next_test_name=nxt)
            if name != "2":
                one_line_dep.inc(1)
            results.update(testmon.get_batch_coverage_data())
        testmon.close()

        assert results["1"]["one_line_dep.py"] == {1}
        assert "one_line_dep.py" not in results["2"]
        assert results["3"]["one_line_dep.py"] == {1}

    @pytest.mark.parametrize("collector_class", COLLECTORS.values(), ids=COLLECTORS)
    def test_last_of_batch_keeps_its_lines(self, testdir, collector_class, monkeypatch):
        # The last test of a batch is still current when the next one starts.
        monkeypatch.setattr(
            sys.modules[collector_class.__module__], "TEST_BATCH_SIZE", 2
        )
        testdir.makepyfile(batch_dep="def inc(x):\n    return x + 1\n")
        testdir.syspathinsert()
        import batch_dep  # pylint: disable=import-error,import-outside-toplevel

        testmon = collector_class(rootdir=str(testdir.tmpdir))
        results = {}
        for name, nxt in (("1", "2"), ("2", "3"), ("3", None)):
            testmon.start_testmon(name, next_test_name=nxt)
            batch_dep.inc(1)
            results.update(testmon.get_batch_coverage_data())
        testmon.close()

        assert {name: results[name]["batch_dep.py"] for name in "123"} == {
            "1": {2},
            "2": {2},
            "3": {2},
        }

    @pytest.mark.skipif(
        sys.platform == "win32", reason="creating symlinks needs privileges"
    )
    @pytest.mark.parametrize("collector_class", COLLECTORS.values(), ids=COLLECTORS)
    def test_file_imported_through_symlink(self, testdir, collector_class):
        # A module imported through a symlink to rootdir (macOS /var ->
        # /private/var, a symlinked PYTHONPATH or editable install) must be
        # reported relative to rootdir, as coverage does after realpath().
        project = testdir.mkdir("project")
        project.join("sym_dep.py").write("def f(x):\n    return x + 1\n")
        link = testdir.tmpdir.join("link")
        link.mksymlinkto(project)
        sys.path.insert(0, str(link))
        try:
            import sym_dep  # pylint: disable=import-error,import-outside-toplevel

            assert sym_dep.__file__.startswith(str(link))
            testmon = collector_class(rootdir=str(project))
            testmon.start_testmon("1", next_test_name=None)
            sym_dep.f(1)
            nodes_files_lines = testmon.get_batch_coverage_data()
            testmon.close()
        finally:
            sys.path.remove(str(link))
            sys.modules.pop("sym_dep", None)

        assert nodes_files_lines["1"]["sym_dep.py"] == {2}

    @pytest.mark.parametrize("collector_class", COLLECTORS.values(), ids=COLLECTORS)
    def test_lines_run_by_concurrent_threads(self, testdir, collector_class):
        # Several threads of one test run the same fresh code at once. On a
        # free-threaded build (3.13t+) they really run in parallel, and racy
        # bookkeeping in the callbacks silently loses lines.
        n_mods, n_funcs, n_threads, n_tests = 10, 50, 8, 10
        for m in range(n_mods):
            testdir.makepyfile(
                **{
                    f"thr_dep{m}": "".join(
                        f"def f{i}(x):\n    return x + {i}\n" for i in range(n_funcs)
                    )
                }
            )
        testdir.syspathinsert()
        mods = [importlib.import_module(f"thr_dep{m}") for m in range(n_mods)]
        funcs = [getattr(mod, f"f{i}") for mod in mods for i in range(n_funcs)]

        testmon = collector_class(rootdir=str(testdir.tmpdir))
        results = {}
        for t in range(n_tests):
            last = t == n_tests - 1
            testmon.start_testmon(str(t), next_test_name=None if last else str(t + 1))
            barrier = threading.Barrier(n_threads)

            def run(k, barrier=barrier):
                barrier.wait()
                for func in funcs if k % 2 else funcs[::-1]:
                    func(k)

            threads = [
                threading.Thread(target=run, args=(k,)) for k in range(n_threads)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            results.update(testmon.get_batch_coverage_data())
        testmon.close()

        expected = {2 * i + 2 for i in range(n_funcs)}
        for t in range(n_tests):
            for m in range(n_mods):
                assert results[str(t)][f"thr_dep{m}.py"] == expected, (t, m)

    @pytest.mark.parametrize("collector_class", COLLECTORS.values(), ids=COLLECTORS)
    def test_thread_outliving_its_test(self, testdir, collector_class):
        # Background threads keep running new code while tests switch: the
        # collector must not iterate over a dict another thread is growing.
        n_mods, n_funcs = 50, 20
        for m in range(n_mods):
            testdir.makepyfile(
                **{
                    f"bg_dep{m}": "".join(
                        f"def f{i}(x):\n    return x + {i}\n" for i in range(n_funcs)
                    )
                }
            )
        testdir.syspathinsert()
        mods = [importlib.import_module(f"bg_dep{m}") for m in range(n_mods)]
        funcs = [getattr(mod, f"f{i}") for mod in mods for i in range(n_funcs)]
        stop = threading.Event()

        def spin():
            while not stop.is_set():
                for func in funcs:
                    func(1)

        testmon = collector_class(rootdir=str(testdir.tmpdir))
        testmon.start_testmon("0", next_test_name="1")
        threads = [threading.Thread(target=spin, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        try:
            n_tests = 300
            for t in range(1, n_tests):
                last = t == n_tests - 1
                testmon.start_testmon(
                    str(t), next_test_name=None if last else str(t + 1)
                )
                testmon.get_batch_coverage_data()
        finally:
            stop.set()
            for thread in threads:
                thread.join()
            testmon.close()

    def test_easy(self, testdir):
        testdir.makepyfile(
            test_a="""
            import os
            from testmon.collector.ctrace import CtraceCollector as CoreTestmon

            def one():
                return getframeinfo(currentframe()).lineno

            def two():
                return getframeinfo(currentframe()).lineno

            from inspect import getframeinfo, currentframe

            def test_1():
                relpath = os.path.relpath(__file__).replace(os.sep, "/")

                def nested():
                    nested_testmon = CoreTestmon("")
                    nested_testmon.setup_coverage()
                    nested_testmon.start_testmon("1")
                    one()
                    nested_coverage = nested_testmon.get_batch_coverage_data()["1"][relpath]
                    nested_testmon.close()
                    assert {one()} == nested_coverage
                    assert one() in testmon.cov.get_data().lines(__file__)
                    two()
                    return nested_coverage

                testmon = CoreTestmon("")
                testmon.setup_coverage(subprocess=False)
                testmon.start_testmon(
                    "2"
                )  # coverage really starts only after a method call or return
                nested_coverage = nested()

                testmon.cov.get_data().set_query_contexts(None)
                this_coverage = testmon.cov.get_data().lines(os.path.abspath(__file__))
                assert nested_coverage == {one()}, f"nested_coverage={nested_coverage}"
                assert (
                    one() in this_coverage and two() in this_coverage
                       ), f"this_coverage={this_coverage}"
                testmon.close()
                """
        )
        result = testdir.runpytest_inprocess("")
        result.assert_outcomes(passed=1)


DEFAULT_DURATION = 0.1


class TestData:
    def test_read_nonexistent(self, testdir):
        with CoreTestmonData.for_local_run("", environment="V2") as td:
            assert td.db.fetch_attribute("1") is None

    def test_write_read_attribute(self, testdir):
        with CoreTestmonData.for_local_run("", environment="V1") as td:
            td.db.write_attribute("1", {"a": 1})
            with CoreTestmonData.for_local_run("", environment="V1") as td2:
                assert td2.db.fetch_attribute("1") == {"a": 1}

    def test_write_read_nodedata(self, tmdata):
        tmdata.write_fixture("test_a.py::n1", {"test_a.py": FINGERPRINT1})
        assert tmdata.all_tests == {
            "test_a.py::n1": {"duration": 0.1, "failed": 0, "forced": None}
        }
        assert tmdata.all_files == ["test_a.py"]

    def test_write_and_clean_tests_simultaneously(self, tmdata):
        tmdata.write_fixture("test_a.py::n1", {"test_a.py": FINGERPRINT1})
        with CoreTestmonDataForTest(system_packages="default") as tmdata2:
            tmdata2.determine_stable()
            tmdata2.sync_db_fs_tests(retain=set())
            tmdata2.db.finish_execution(tmdata.exec_id)
            tmdata.write_fixture("test_a.py::n2", {"test_a.py": FINGERPRINT1})

    def test_filenames_fingerprints(self, tmdata):
        tmdata.write_fixture("test_1.py::test_1", {"test_1.py": FINGERPRINT1}, failed=1)

        fps = tuple(tmdata.db.filenames_fingerprints(tmdata.exec_id)[0].values())
        assert fps == (
            "test_1.py",
            None,
            "100",
            1,
            1,
        )

    def test_write_get_changed_file_data(self, tmdata):
        tmdata.write_fixture("test_1.py::test_1", {"test_1.py": FINGERPRINT1}, failed=1)

        node_data = tmdata.db.fetch_changed_file_data([1], tmdata.exec_id)

        assert node_data == [
            ["test_1.py", "test_1.py::test_1", FINGERPRINT1, 1, 1, DEFAULT_DURATION]
        ]

    def test_determine_stable_flow(self, tmdata):
        tmdata.write_fixture("test_1.py::test_1", {"test_1.py": FINGERPRINT1})

        tmdata.source_tree.cache["test_1.py"].mtime = 1100.0
        tmdata.source_tree.cache["test_1.py"].fsha = "100" + "missing"
        del tmdata.source_tree.cache["test_1.py"]

        filenames_fingerprints = tmdata.db.filenames_fingerprints(tmdata.exec_id)

        assert tuple(filenames_fingerprints[0].values()) == (
            "test_1.py",
            None,
            "100",
            1,
            0,
        )

        _, mtime_misses = split_filter(
            tmdata.source_tree, check_mtime, filenames_fingerprints
        )

        fsha_hits, fsha_misses = split_filter(
            tmdata.source_tree, check_fsha, mtime_misses
        )

        changed_files = [fsha_miss["fingerprint_id"] for fsha_miss in fsha_misses]

        assert changed_files == [1]

        changed_file_data = tmdata.db.fetch_changed_file_data(
            changed_files, tmdata.exec_id
        )

        assert changed_file_data == [
            ["test_1.py", "test_1.py::test_1", FINGERPRINT1, 1, 0, DEFAULT_DURATION]
        ]

        hits, misses = split_filter(
            tmdata.source_tree, check_fingerprint, changed_file_data
        )
        assert misses == changed_file_data

    def test_new_determine_stable_flow(self, tmdata):
        tmdata.write_fixture("test_1.py::test_1", {"test_1.py": FINGERPRINT1})
        del tmdata.source_tree.cache["test_1.py"]

        filenames = tmdata.db.filenames(tmdata.exec_id)

        assert filenames == ["test_1.py"]

        assert (
            len(
                tmdata.db.fetch_unknown_files(
                    files_fshas={"test_1.py": "100"},
                    exec_id=tmdata.exec_id,
                )
            )
            == 0
        )
        changed_file_data = tmdata.db.fetch_unknown_files(
            files_fshas={"test_1.py": "101"}, exec_id=tmdata.exec_id
        )

        assert changed_file_data == ["test_1.py"]

        misses = tmdata.db.determine_tests(
            tmdata.exec_id, collect_mhashes(tmdata.source_tree, changed_file_data)
        )["affected"]

        assert misses == ["test_1.py::test_1"]

    def test_new_determine_stable_flow_missing_file(self, tmdata):
        tmdata.write_fixture("test_1.py::test_1a", {"test_1.py": FINGERPRINT1})
        tmdata.write_fixture("test_2.py::test_2a", {"test_2.py": FINGERPRINT1})

        filenames = tmdata.db.filenames(tmdata.exec_id)

        assert filenames == ["test_1.py", "test_2.py"]

        del tmdata.source_tree.cache["test_2.py"]

        changed_file_data = tmdata.db.fetch_unknown_files(
            {"test_1.py": "100"}, tmdata.exec_id
        )

        assert changed_file_data == ["test_2.py"]

        assert tmdata.db.determine_tests(
            tmdata.exec_id,
            {"test_1.py": FINGERPRINT1, "test_2.py": None},
        )["affected"] == ["test_2.py::test_2a"]

    def test_garbage_retain_stable(self, tmdata):
        tmdata.write_fixture("test_1.py::test_1", {"test_1.py": FINGERPRINT1})
        tmdata.determine_stable()

        tmdata.sync_db_fs_tests(retain=set())
        assert set(tmdata.all_tests) == {"test_1.py::test_1"}

    def test_write_data2(self, tmdata):
        tmdata.determine_stable()

        node_data = {
            "test_1.py::test_1": {
                "test_1.py": FPF1,
                "a.py": FPFA,
            },
            "test_1.py::test_2": {
                "test_1.py": FPF1,
                "a.py": FPFA2,
            },
            "test_1.py::test_3": {"a.py": FPFA},
        }

        tmdata.sync_db_fs_tests(set(node_data.keys()))
        for node, files in node_data.items():
            tmdata.write_fixture(node, files)

        result = defaultdict(dict)

        compare_to = copy.deepcopy(node_data)
        for (
            filename,
            node_name,
            fingerprint,
            _,
            _,
            _,
        ) in tmdata.db.fetch_changed_file_data(list(range(10)), tmdata.exec_id):
            result[node_name][filename] = fingerprint if fingerprint != [""] else []

        assert result == node_data

        change = {
            "test_1.py::test_1": {
                "a.py": FPFA2,
                "test_1.py": FPF1,
            }
        }

        node_data.update(change)
        tmdata.write_fixture(
            "test_1.py::test_1",
            {
                "a.py": FPFA2,
                "test_1.py": FPF1,
            },
        )

        for (
            filename,
            node_name,
            fingerprint,
            _,
            _,
            _,
        ) in tmdata.db.fetch_changed_file_data(list(range(10)), tmdata.exec_id):
            result[node_name][filename] = fingerprint if fingerprint != [""] else []

        assert result == node_data

    def test_collect_garbage(self, tmdata):
        tmdata = tmdata
        tmdata.write_fixture("test_1", {"test_1.py": FINGERPRINT1})

        tmdata.source_tree.cache["test_1.py"] = Module(source_code="")
        tmdata.source_tree.cache["test_1.py"].mtime = 1100.0
        tmdata.source_tree.cache["test_1.py"].fs_fsha = "600"
        tmdata.source_tree.cache["test_1.py"].fingerprint = "FINGERPRINT2"

        tmdata.determine_stable()
        assert set(tmdata.all_tests)
        tmdata.sync_db_fs_tests(retain=set())
        tmdata.close_connection()

        with CoreTestmonData.for_local_run("") as td2:
            td2.determine_stable()
            assert set(td2.all_tests) == set()

    def test_remove_unused_fingerprints(self, tmdata):
        tmdata.write_fixture("n1", {"test_a.py": FINGERPRINT1})

        tmdata.source_tree.cache["test_a.py"] = None
        tmdata.determine_stable()

        tmdata.sync_db_fs_tests(set())
        tmdata.db.finish_execution(tmdata.exec_id)

        c = tmdata.db.con
        assert c.execute("SELECT * FROM file_fp").fetchall() == []

    def test_one_failed_in_fingerprints(self, tmdata):
        tmdata.write_fixture(
            "test_1.py::test_1", {"test_1.py": FINGERPRINT1}, failed=True
        )

        tmdata.write_fixture(
            "test_1.py::test_2", {"test_1.py": FINGERPRINT1}, failed=False
        )
        assert tmdata.db.filenames_fingerprints(tmdata.exec_id)[0]["sum(failed)"] == 1

    def test_nodes_classes_modules_durations(self, tmdata: CoreTestmonDataForTest):
        tmdata.create_report(2, 3, "test_a1", "tests.py", "TestA")
        tmdata.create_report(1, 4, "test_a2", "tests.py", "TestA")
        tmdata.create_report(1, 5, "test_b1", "tests.py", "TestB")

        avg_durations = tmdata.avg_durations
        print(avg_durations)
        assert avg_durations["tests.py::TestA::test_a1"] == 3
        assert avg_durations["tests.py::TestA::test_a2"] == 4
        assert avg_durations["tests.py::TestB::test_b1"] == 5
        assert avg_durations["TestA"] == 3.5
        assert avg_durations["TestB"] == 5
        assert avg_durations["tests.py"] == 4

    def test_environment_same(self, testdir):
        # same environment -> same execution id
        environemnt_name = "default"
        system_packages = "first_package 1.0.0, second_package 2.0.1, third_package 3.0 fourth_package 4"
        python_version = "3.11"
        with CoreTestmonData.for_local_run(
            "",
            environment=environemnt_name,
            system_packages=system_packages,
            python_version=python_version,
        ) as td:
            with CoreTestmonData.for_local_run(
                "",
                environment=environemnt_name,
                system_packages=system_packages,
                python_version=python_version,
            ) as td2:
                assert td.exec_id == td2.exec_id

    def test_environment_diff_name(self, testdir):
        # environment differs in name -> different execution id
        environemnt_name = "default"
        environemnt_name2 = "default2"
        system_packages = "first_package 1.0.0, second_package 2.0.0"
        python_version = "3.11"
        with CoreTestmonData.for_local_run(
            "",
            environment=environemnt_name,
            system_packages=system_packages,
            python_version=python_version,
        ) as td:
            with CoreTestmonData.for_local_run(
                "",
                environment=environemnt_name2,
                system_packages=system_packages,
                python_version=python_version,
            ) as td2:
                assert td.exec_id != td2.exec_id

    def test_environment_same_packages(self, testdir):
        # environment differs in system_packages -> different execution id
        environemnt_name = "default"
        system_packages = "first_package 1.0.0, second_package 2.0, third_package 3"
        system_packages2 = "first_package 1.0.1, second_package 2.0, third_package 3"
        python_version = "3.11"
        with CoreTestmonData.for_local_run(
            "",
            environment=environemnt_name,
            system_packages=system_packages,
            python_version=python_version,
        ) as td:
            with CoreTestmonData.for_local_run(
                "",
                environment=environemnt_name,
                system_packages=system_packages2,
                python_version=python_version,
            ) as td2:
                assert td.exec_id == td2.exec_id

    def test_environment_diff_packages(self, testdir):
        # environment differs in system_packages -> different execution id
        environemnt_name = "default"
        system_packages = "first_package 1.0.0, second_package 2.0, third_package 3"
        system_packages2 = "first_package 1.1.0, second_package 2.0, third_package 3"
        python_version = "3.11"
        with CoreTestmonData.for_local_run(
            "",
            environment=environemnt_name,
            system_packages=system_packages,
            python_version=python_version,
        ) as td:
            with CoreTestmonData.for_local_run(
                "",
                environment=environemnt_name,
                system_packages=system_packages2,
                python_version=python_version,
            ) as td2:
                assert td.exec_id != td2.exec_id

    def test_environment_diff_pyversion(self, testdir):
        # environment differs in python_version -> different execution id
        environemnt_name = "default"
        system_packages = "first_package 1.0.0, second_package 2.0.0"
        python_version = "3.11"
        python_version2 = "3.7"

        with CoreTestmonData.for_local_run(
            "",
            environment=environemnt_name,
            system_packages=system_packages,
            python_version=python_version,
        ) as td:
            with CoreTestmonData.for_local_run(
                "",
                environment=environemnt_name,
                system_packages=system_packages,
                python_version=python_version2,
            ) as td2:
                assert td.exec_id != td2.exec_id


class TestCoreTestmon:
    def test_check_mtime(self):
        fs = SourceTree("")
        fs.cache["test_a.py"] = Module("", mtime=1)

        assert check_mtime(fs, {"filename": "test_a.py", "mtime": 1})
        assert not check_mtime(fs, {"filename": "test_a.py", "mtime": 2})
        pytest.raises(Exception, check_mtime, fs, ("test_a.py",))

    def test_mtime_filter(self):
        fs = SourceTree("")
        fs.cache["test_a.py"] = Module("", mtime=1)

        record = {"filename": "test_a.py", "mtime": 1}
        assert split_filter(fs, check_mtime, (record,)) == ([record], [])

        record2 = {"filename": "test_a.py", "mtime": 2}
        assert split_filter(fs, check_mtime, (record2,)) == ([], [record2])

    def test_split_filter(self):
        assert split_filter(None, lambda disk, x: x == 1, (1, 2)) == ([1], [2])

    def test_get_new_mtimes(self, testdir):
        a_py = testdir.makepyfile(
            a="""\
                def test_a():
                    return 0
                """
        )
        fs = SourceTree(testdir.tmpdir.strpath)

        assert next(get_new_mtimes(fs, (("a.py", None, None, 2),))) == (
            a_py.mtime(),
            "fa6a227f99876e05a03e5b9a522777f053d76b94",
            2,
        )


def one():
    return getframeinfo(currentframe()).lineno


def two():
    return getframeinfo(currentframe()).lineno


class TestSourceTree:
    def test_get_file(self, testdir):
        sc = """\
                def test_a():
                    return 0
                    """
        a_py = testdir.makepyfile(a=sc)
        file_system = SourceTree(rootdir=testdir.tmpdir.strpath)
        module = file_system.get_file("a.py")
        assert module.mtime == a_py.mtime()
        assert module._source_code == textwrap.dedent(sc)

    def test_nonexistent_file(self, testdir):
        file_system = SourceTree(rootdir=testdir.tmpdir.strpath)
        assert file_system.get_file("jdslkajfnoweijflaohdnoviwn.py") is None

    def test_empty_file(self, testdir):
        file_system = SourceTree(rootdir=testdir.tmpdir.strpath)
        testdir.makepyfile(__init__="")
        module = file_system.get_file("__init__.py")
        assert module._source_code == ""
