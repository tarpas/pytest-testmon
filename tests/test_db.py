import sqlite3

from testmon.db import DB

FINGERPRINT_INDEX = "test_execution_file_fp_fingerprint_id"


def index_names(datafile):
    con = sqlite3.connect(datafile)
    try:
        return {
            row[1] for row in con.execute("PRAGMA index_list(test_execution_file_fp)")
        }
    finally:
        con.close()


class TestFingerprintIndex:
    def test_new_datafile_has_index(self, tmp_path):
        datafile = str(tmp_path / ".testmondata")

        DB(datafile).con.close()

        assert FINGERPRINT_INDEX in index_names(datafile)

    def test_existing_datafile_without_index_gets_it_on_open(self, tmp_path):
        datafile = str(tmp_path / ".testmondata")
        DB(datafile).con.close()
        con = sqlite3.connect(datafile)
        con.execute(f"DROP INDEX {FINGERPRINT_INDEX}")
        con.commit()
        con.close()
        assert FINGERPRINT_INDEX not in index_names(datafile)

        DB(datafile).con.close()

        assert FINGERPRINT_INDEX in index_names(datafile)

    def test_readonly_open_does_not_write_index(self, tmp_path):
        datafile = str(tmp_path / ".testmondata")
        DB(datafile).con.close()
        con = sqlite3.connect(datafile)
        con.execute(f"DROP INDEX {FINGERPRINT_INDEX}")
        con.commit()
        con.close()

        DB(datafile, readonly=True).con.close()

        assert FINGERPRINT_INDEX not in index_names(datafile)
