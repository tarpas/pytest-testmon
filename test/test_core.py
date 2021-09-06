import pytest
import sqlite3
from collections import defaultdict

from testmon.db import (
    ChangedFileData,
)
from testmon.process_code import Module, encode_lines
from testmon.testmon_core import (
    TestmonData as CoreTestmonData,
    SourceTree,
    CHECKUMS_ARRAY_TYPE,
    is_python_file,
    check_mtime,
    split_filter,
    check_fingerprint,
    check_checksum,
    get_new_mtimes,
    Testmon as CoreTestmon,
)

from testmon.process_code import checksums_to_blob, blob_to_checksums


pytest_plugins = ("pytester",)

from array import array


class CoreTestmonDataForTest(CoreTestmonData):
    def create_report_phase(self, duration, location=()):
        return {"duration": duration, "location": location}

    def create_report(
        self, phases_count, duration, node_name, node_module, node_class=None
    ):
        phases = ["setup", "call", "teardown"]
        result = {}
        name = "".join(
            [
                node_module,
                "::",
                f"{node_class}::{node_name}" if node_class else node_name,
            ]
        )
        location = (
            node_module,
            1,
            f"{node_class}.{node_name}" if node_class else node_name,
        )

        for i in range(0, phases_count):
            result[phases[i]] = self.create_report_phase(
                duration / phases_count, location
            )

        self.write(name, {node_module: encode_lines([""])}, result)

    def write(self, node, files, result=None, failed=False):
        records = []
        for filename in files:
            records.append(
                {
                    "fingerprint": checksums_to_blob(files[filename]),
                    "filename": filename,
                    "mtime": 1.0,
                    "checksum": "100",
                }
            )

        if result:
            if failed:
                raise Exception("result and failed not allowed simultaneously")
            r1 = result
        else:
            if failed:
                r1 = {"run": {"outcome": "failed"}}
            else:
                r1 = {}

        self.db.insert_node_fingerprints(node, records, r1)


@pytest.fixture
def tmdata(testdir):
    return CoreTestmonDataForTest(rootdir="")


class TestMisc(object):
    def test_is_python_file(self):
        assert is_python_file("/dir/file.py")
        assert is_python_file("f.py")
        assert not is_python_file("/notpy/file.p")

    def test_sqlite_assumption_foreign_key(self, tmdata):
        def node_fingerprint_count(nodeid):
            return con.execute(
                "SELECT count(*) FROM node_fingerprint where node_id = ?",
                (nodeid,),
            ).fetchone()[0]

        record = {
            "filename": "test_a.py",
            "fingerprint": "fingerprint",
            "mtime": None,
            "checksum": None,
        }
        tmdata.db.insert_node_fingerprints("test_a.py::n1", [record])
        con = tmdata.db.con
        first_nodeid = con.execute("SELECT id FROM node").fetchone()[0]

        tmdata.db.insert_node_fingerprints("test_a.py::n1", [record])
        second_nodeid = con.execute("SELECT max(id) FROM node").fetchone()[0]
        assert first_nodeid != second_nodeid
        assert node_fingerprint_count(first_nodeid) == 0
        assert node_fingerprint_count(second_nodeid) == 1
        tmdata.db.con.execute("DELETE FROM node")
        assert node_fingerprint_count(second_nodeid) == 0


class TestData:
    def test_read_nonexistent(self, testdir):
        td = CoreTestmonData(testdir.tmpdir.strpath, "V2")
        assert td.db._fetch_attribute("1") == None

    def test_write_read_attribute(self, testdir):
        td = CoreTestmonData(testdir.tmpdir.strpath, "V1")
        td.db._write_attribute("1", {"a": 1})
        td2 = CoreTestmonData(testdir.tmpdir.strpath, "V1")
        assert td2.db._fetch_attribute("1") == {"a": 1}

    def test_write_read_nodedata(self, tmdata):
        tmdata.write("test_a.py::n1", {"test_a.py": encode_lines(["1"])})
        assert tmdata.all_nodes == {
            "test_a.py::n1": {
                "durations": {"call": 0.0, "setup": 0.0, "teardown": 0.0},
                "failed": 0,
            }
        }
        assert tmdata.all_files == {"test_a.py"}

    def test_filenames_fingerprints(self, tmdata):
        tmdata.write(
            "test_1.py::test_1", {"test_1.py": encode_lines("FINGERPRINT1")}, failed=1
        )

        fps = tuple(tmdata.filenames_fingerprints[0])
        assert fps == (
            "test_1.py",
            1.0,
            "100",
            1,
            1,
        )

    def test_write_get_changed_file_data(self, tmdata):
        tmdata.write(
            "test_1.py::test_1", {"test_1.py": encode_lines(["FINGERPRINT1"])}, failed=1
        )

        node_data = tmdata.db.get_changed_file_data({1})

        assert node_data == [
            ChangedFileData(
                "test_1.py", "test_1.py::test_1", encode_lines(["FINGERPRINT1"]), 1, 1
            )
        ]

    def test_determine_stable_flow(self, tmdata):
        tmdata.write("test_1.py::test_1", {"test_1.py": encode_lines(["FINGERPRINT1"])})

        filenames_fingerprints = tmdata.filenames_fingerprints

        assert tuple(filenames_fingerprints[0]) == ("test_1.py", 1.0, "100", 1, 0)

        _, mtime_misses = split_filter(
            tmdata.source_tree, check_mtime, filenames_fingerprints
        )

        checksum_hits, checksum_misses = split_filter(
            tmdata.source_tree, check_checksum, mtime_misses
        )

        changed_files = {checksum_miss[3] for checksum_miss in checksum_misses}

        assert changed_files == {1}

        changed_file_data = tmdata.db.get_changed_file_data(changed_files)

        assert changed_file_data == [
            ("test_1.py", "test_1.py::test_1", encode_lines(["FINGERPRINT1"]), 1, 0)
        ]

        hits, misses = split_filter(
            tmdata.source_tree, check_fingerprint, changed_file_data
        )
        assert misses == changed_file_data

    def test_garbage_retain_stable(self, tmdata):
        tmdata.write("test_1.py::test_1", {"test_1.py": encode_lines(["FINGERPRINT1"])})
        tmdata.determine_stable()

        tmdata.sync_db_fs_nodes(retain=set())
        assert set(tmdata.all_nodes) == {"test_1.py::test_1"}

    def test_write_data2(self, tmdata):

        tmdata.determine_stable()

        node_data = {
            "test_1.py::test_1": {
                "test_1.py": encode_lines(["F1"]),
                "a.py": encode_lines(["FA"]),
            },
            "test_1.py::test_2": {
                "test_1.py": encode_lines(["F1"]),
                "a.py": encode_lines(["FA2"]),
            },
            "test_1.py::test_3": {"a.py": encode_lines(["FA"])},
        }

        tmdata.sync_db_fs_nodes(set(node_data.keys()))
        for node, files in node_data.items():
            tmdata.write(node, files)

        result = defaultdict(dict)

        for (
            filename,
            node_name,
            fingerprint,
            _,
            _,
        ) in tmdata.db.get_changed_file_data(set(range(10))):
            result[node_name][filename] = fingerprint
        assert result == node_data

        change = {
            "test_1.py::test_1": {
                "a.py": encode_lines(["FA2"]),
                "test_1.py": encode_lines(["F1"]),
            }
        }

        node_data.update(change)
        tmdata.write(
            "test_1.py::test_1",
            {
                "a.py": encode_lines(["FA2"]),
                "test_1.py": encode_lines(["F1"]),
            },
        )

        for (
            filename,
            node_name,
            fingerprint,
            _,
            _,
        ) in tmdata.db.get_changed_file_data(set(range(10))):
            result[node_name][filename] = fingerprint
        assert result == node_data

    def test_collect_garbage(self, tmdata):
        tmdata.write("test_1", {"test_1.py": encode_lines(["FINGERPRINT1"])})

        tmdata.source_tree.cache["test_1.py"] = Module(source_code="")
        tmdata.source_tree.cache["test_1.py"].mtime = 1100.0
        tmdata.source_tree.cache["test_1.py"].checksum = 600
        tmdata.source_tree.cache["test_1.py"].fingerprint = "FINGERPRINT2"

        tmdata.determine_stable()
        assert set(tmdata.all_nodes)
        tmdata.sync_db_fs_nodes(retain=set())
        tmdata.close_connection()

        td2 = CoreTestmonData("")
        td2.determine_stable()
        assert set(td2.all_nodes) == set()

    def test_remove_unused_fingerprints(self, tmdata):
        tmdata.write("n1", {"test_a.py": encode_lines(["1"])})

        tmdata.source_tree.cache["test_a.py"] = None
        tmdata.determine_stable()

        tmdata.sync_db_fs_nodes(set())
        tmdata.db.remove_unused_fingerprints()

        c = tmdata.db.con
        assert c.execute("SELECT * FROM fingerprint").fetchall() == []

    def test_one_failed_in_fingerprints(self, tmdata):
        tmdata.write(
            "test_1.py::test_1",
            {"test_1.py": encode_lines(["FINGERPRINT1"])},
            failed=True,
        )

        tmdata.write(
            "test_1.py::test_2",
            {"test_1.py": encode_lines(["FINGERPRINT1"])},
            failed=False,
        )

        assert tmdata.filenames_fingerprints[0]["sum(failed)"] == 1

    def test_nodes_classes_modules_durations(self, tmdata: CoreTestmonDataForTest):
        tmdata.create_report(2, 3, "test_a1", "tests.py", "TestA")
        tmdata.create_report(1, 4, "test_a2", "tests.py", "TestA")
        tmdata.create_report(1, 5, "test_b1", "tests.py", "TestB")

        avg_durations = tmdata.nodes_classes_modules_avg_durations
        print(avg_durations)
        assert avg_durations["tests.py::TestA::test_a1"] == 3
        assert avg_durations["tests.py::TestA::test_a2"] == 4
        assert avg_durations["tests.py::TestB::test_b1"] == 5
        assert avg_durations["TestA"] == 3.5
        assert avg_durations["TestB"] == 5
        assert avg_durations["tests.py"] == 4


class TestCoreTestmon:
    def test_check_mtime(self):
        fs = SourceTree("")
        fs.cache["test_a.py"] = Module(
            "", file_name="test_a.py", mtime=1, checksum=1000
        )

        assert check_mtime(fs, {"file_name": "test_a.py", "mtime": 1})
        assert not check_mtime(fs, {"file_name": "test_a.py", "mtime": 2})
        pytest.raises(Exception, check_mtime, fs, ("test_a.py",))

    def test_check_checksum(self):
        fs = SourceTree("")
        fs.cache["test_a.py"] = Module(
            "", file_name="test_a.py", mtime=1, checksum=1000
        )
        assert check_checksum(fs, {"file_name": "test_a.py", "checksum": 1000})
        assert check_checksum(fs, {"file_name": "test_a.py", "checksum": 1001}) is False
        assert pytest.raises(
            Exception, check_checksum, fs, {"file_name": "test_a.py", "bla": None}
        )

    def test_mtime_filter(self):
        fs = SourceTree("")
        fs.cache["test_a.py"] = Module(
            "", file_name="test_a.py", mtime=1, checksum=1000
        )

        record = {"file_name": "test_a.py", "mtime": 1}
        assert split_filter(fs, check_mtime, (record,)) == ([record], [])

        record2 = {"file_name": "test_a.py", "mtime": 2}
        assert split_filter(fs, check_mtime, (record2,)) == ([], [record2])

    def test_split_filter(self):
        assert split_filter(None, lambda disk, x: x == 1, (1, 2)) == ([1], [2])

    def test_get_new_mtimes(self, testdir):
        a_py = testdir.makepyfile(
            a="""
                def test_a():
                    return 0
                """
        )
        fs = SourceTree(testdir.tmpdir.strpath)

        assert next(get_new_mtimes(fs, (("a.py", None, None, 2),))) == (
            a_py.mtime(),
            "de226b260917867990e4fb7aac70c5d6582266d4",
            2,
        )


class TestSourceTree:
    def test_get_file(self, testdir):
        a_py = testdir.makepyfile(
            a="""
                def test_a():
                    return 0
        """
        )
        file_system = SourceTree(rootdir=testdir.tmpdir.strpath)
        module = file_system.get_file("a.py")
        assert module.mtime == a_py.mtime()
        assert module.checksum == "de226b260917867990e4fb7aac70c5d6582266d4"

    def test_nonexistent_file(self, testdir):
        file_system = SourceTree(rootdir=testdir.tmpdir.strpath)
        assert file_system.get_file("jdslkajfnoweijflaohdnoviwn.py") is None

    def test_empty_file(self, testdir):
        file_system = SourceTree(rootdir=testdir.tmpdir.strpath)
        testdir.makepyfile(__init__="")
        module = file_system.get_file("__init__.py")
        assert module.checksum == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
