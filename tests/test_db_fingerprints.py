import sqlite3

import pytest

from testmon.db import DB
from testmon.process_code import Module, create_fingerprint

SOURCE = "def f():\n    return 1\n"
COMMENTED = "# a comment\ndef f():\n    return 1\n"
BODY_LINE = {SOURCE: 2, COMMENTED: 3}


def record(db, exec_id, test_name, source):
    module = Module(source_code=source)
    db.insert_test_file_fps(
        {
            test_name: {
                "deps": [
                    {
                        "filename": "a.py",
                        "fsha": module.fs_fsha,
                        "method_checksums": create_fingerprint(
                            module, {BODY_LINE[source]}
                        ),
                    }
                ]
            }
        },
        exec_id,
    )
    return module.fs_fsha


def stored_fsha(datafile, test_name):
    con = sqlite3.connect(datafile)
    try:
        return con.execute(
            """
            SELECT f.fsha FROM test_execution te
            JOIN test_execution_file_fp te_ffp ON te_ffp.test_execution_id = te.id
            JOIN file_fp f ON f.id = te_ffp.fingerprint_id
            WHERE te.test_name = ?
            """,
            (test_name,),
        ).fetchone()[0]
    finally:
        con.close()


class TestFingerprintAfterBytesOnlyChange:
    @pytest.mark.parametrize(
        "old_source, new_source", [(SOURCE, COMMENTED), (COMMENTED, SOURCE)]
    )
    def test_rerecorded_test_stores_current_fsha(
        self, tmp_path, old_source, new_source
    ):
        datafile = str(tmp_path / ".testmondata")
        db = DB(datafile)
        exec_id, _ = db.fetch_or_create_environment("default", "", "3")
        record(db, exec_id, "test_a.py::test_a", old_source)
        record(db, exec_id, "test_b.py::test_b", new_source)

        new_fsha = record(db, exec_id, "test_a.py::test_a", new_source)

        assert stored_fsha(datafile, "test_a.py::test_a") == new_fsha
        assert db.fetch_unknown_files({"a.py": new_fsha}, exec_id) == []
        db.con.close()
