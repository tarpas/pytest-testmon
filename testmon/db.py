import json
import os
import sqlite3

from collections import namedtuple
from functools import lru_cache

from testmon.process_code import blob_to_checksums, checksums_to_blob

DATA_VERSION = 0

ChangedFileData = namedtuple(
    "ChangedFileData", "filename name method_checksums id failed"
)


class CachedProperty:
    def __init__(self, func):
        self.__doc__ = getattr(func, "__doc__")
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


class TestmonDbException(Exception):
    pass


def connect(datafile, readonly=False):
    connection = sqlite3.connect(
        f"file:{datafile}{'?mode=ro' if readonly else ''}", uri=True
    )

    connection.execute("PRAGMA synchronous = OFF")
    connection.execute("PRAGMA foreign_keys = TRUE ")
    connection.execute("PRAGMA recursive_triggers = TRUE ")
    connection.row_factory = sqlite3.Row
    return connection


class DB:
    def __init__(self, datafile):
        new_db = not os.path.exists(datafile)

        connection = connect(datafile)
        self.con = connection
        old_format = self._check_data_version(datafile)

        if new_db or old_format:
            self.init_tables()

        self.con.execute(
            "CREATE TEMPORARY TABLE temp_files_checksums (filename TEXT, checksum TEXT)"
        )

    def _check_data_version(self, datafile):
        stored_data_version = self._fetch_data_version()

        if int(stored_data_version) == DATA_VERSION:
            return False

        self.con.close()
        os.remove(datafile)
        self.con = connect(datafile)
        return True

    def __enter__(self):
        self.con = self.con.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.con.__exit__(*args, **kwargs)

    def _test_execution_fk_column(self):
        return "environment_id"

    def _test_execution_fk_table(self):
        return "environment"

    def update_mtimes(self, new_mtimes):
        with self.con as con:
            con.executemany(
                "UPDATE file_fp SET mtime=?, checksum=? WHERE id = ?", new_mtimes
            )

    def remove_unused_file_fps(self):
        with self.con as con:
            con.execute(
                """
                DELETE FROM file_fp
                WHERE id NOT IN (
                    SELECT DISTINCT fingerprint_id FROM test_execution_file_fp
                )
                """
            )

    def fetch_or_create_file_fp(self, filename, mtime, checksum, method_checksums):
        cursor = self.con.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO file_fp
                (filename, method_checksums, mtime, checksum)
                VALUES (?, ?, ?, ?)
                """,
                (filename, method_checksums, mtime, checksum),
            )

            fingerprint_id = cursor.lastrowid
        except sqlite3.IntegrityError:

            fingerprint_id, *_ = cursor.execute(
                """
                SELECT
                    id,
                    mtime,
                    checksum
                FROM
                    file_fp
                WHERE
                    filename = ? AND method_checksums = ?
                """,
                (filename, method_checksums),
            ).fetchone()

            self.update_mtimes([(mtime, checksum, fingerprint_id)])
        return fingerprint_id

    def _insert_test_execution(
        self,
        test_name,
        duration,
        failed,
        exec_id,
    ):
        with self.con as con:
            cursor = con.cursor()
            cursor.execute(
                f"""
                    INSERT OR REPLACE INTO test_execution
                    ({self._test_execution_fk_column()}, test_name, duration, failed)
                    VALUES (?, ?, ?, ?)
                    """,
                (
                    exec_id,
                    test_name,
                    duration,
                    1 if failed else 0,
                ),
            )
            return cursor.lastrowid

    def insert_test_file_fps(self, tests_fingerprints, fa_durs=None, exec_id=None):
        assert exec_id
        if fa_durs is None:
            fa_durs = {}
        with self.con as con:
            cursor = con.cursor()
            for test_name in tests_fingerprints:
                fingerprints = tests_fingerprints[test_name]
                failed, duration = fa_durs.get(test_name, (0, None))
                te_id = self._insert_test_execution(
                    test_name, duration, failed, exec_id=exec_id
                )

                for record in fingerprints:
                    fingerprint_id = self.fetch_or_create_file_fp(
                        record["filename"],
                        None,
                        record["checksum"],
                        checksums_to_blob(record["method_checksums"]),
                    )

                    cursor.execute(
                        "INSERT INTO test_execution_file_fp VALUES (?, ?)",
                        (te_id, fingerprint_id),
                    )

    def _fetch_data_version(self):
        con = self.con

        return con.execute("PRAGMA user_version").fetchone()[0]

    def write_attribute(self, attribute, data, exec_id=None):
        dataid = f"{exec_id}:{attribute}"
        with self.con as con:
            con.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
                [dataid, json.dumps(data)],
            )

    def fetch_attribute(self, attribute, default=None, exec_id=None):
        cursor = self.con.execute(
            "SELECT data FROM metadata WHERE dataid=?",
            [f"{exec_id}:{attribute}"],
        )
        result = cursor.fetchone()
        if result:
            return json.loads(result[0])
        return default

    def create_metadata_statement(self):
        return """CREATE TABLE metadata (dataid TEXT PRIMARY KEY, data TEXT);"""

    def create_environment_statement(self):
        return """
                CREATE TABLE environment (
                id INTEGER PRIMARY KEY ASC,
                environment_name TEXT,
                system_packages TEXT,
                python_version TEXT,
                UNIQUE (environment_name, system_packages, python_version)
            );"""

    def create_test_execution_statement(self):
        return f"""
                CREATE TABLE test_execution (
                id INTEGER PRIMARY KEY ASC,
                {self._test_execution_fk_column()} INTEGER,
                test_name TEXT,
                duration FLOAT,
                failed BIT,
                UNIQUE ({self._test_execution_fk_column()}, test_name),
                FOREIGN KEY({self._test_execution_fk_column()}) REFERENCES {self._test_execution_fk_table()}(id)
            );"""

    def create_file_fp_statement(self):
        return """
            CREATE TABLE file_fp
            (
                id INTEGER PRIMARY KEY,
                filename TEXT,
                method_checksums BLOB,
                mtime FLOAT,
                checksum TEXT,
                UNIQUE (filename, method_checksums)
            );"""

    def create_test_execution_ffp_statement(
        self,
    ):
        return """
            CREATE TABLE test_execution_file_fp (
                test_execution_id INTEGER,
                fingerprint_id INTEGER,
                FOREIGN KEY(test_execution_id) REFERENCES test_execution(id) ON DELETE CASCADE,
                FOREIGN KEY(fingerprint_id) REFERENCES file_fp(id)
            );
            """

    def init_tables(self):
        connection = self.con

        connection.executescript(
            self.create_metadata_statement()
            + self.create_environment_statement()
            + self.create_test_execution_statement()
            + self.create_file_fp_statement()
            + self.create_test_execution_ffp_statement()
        )

        connection.execute(f"PRAGMA user_version = {DATA_VERSION}")

    def fetch_changed_file_data(self, changed_fingerprints, exec_id):
        in_clause_questionsmarks = ", ".join("?" * len(changed_fingerprints))
        result = []
        for row in self.con.execute(
            f"""
            SELECT
                f.filename,
                te.test_name,
                f.method_checksums,
                f.id,
                te.failed,
                te.duration
            FROM test_execution te, test_execution_file_fp te_ffp, file_fp f
            WHERE
                te.{self._test_execution_fk_column()} = ? AND
                te.id = te_ffp.test_execution_id AND
                te_ffp.fingerprint_id = f.id AND
                f.id IN ({in_clause_questionsmarks})
            """,
            [
                exec_id,
            ]
            + list(changed_fingerprints),
        ):
            result.append(
                [
                    row["filename"],
                    row["test_name"],
                    blob_to_checksums(row["method_checksums"]),
                    row["id"],
                    row["failed"],
                    row["duration"],
                ]
            )

        return result

    def new_fetch_changed_file_data(self, files_checksums, exec_id):
        with self.con:
            self.con.execute("DELETE FROM temp_files_checksums")
            self.con.executemany(
                "INSERT INTO temp_files_checksums VALUES (?, ?)",
                files_checksums.items(),
            )
            result = []
            for row in self.con.execute(
                f"""
                SELECT
                    f.filename,
                    te.test_name,
                    f.method_checksums,
                    f.id,
                    te.failed,
                    te.duration
                FROM test_execution te, test_execution_file_fp te_ffp, file_fp f
                LEFT OUTER JOIN temp_files_checksums tfc
                ON f.filename = tfc.filename and f.checksum = tfc.checksum
                WHERE
                    te.{self._test_execution_fk_column()} = ? AND
                    te.id = te_ffp.test_execution_id AND
                    te_ffp.fingerprint_id = f.id AND
                    (f.checksum IS NULL OR tfc.checksum IS NULL OR f.checksum <> tfc.checksum)
                """,
                [exec_id],
            ):
                result.append(
                    [
                        row["filename"],
                        row["test_name"],
                        blob_to_checksums(row["method_checksums"]),
                        row["id"],
                        row["failed"],
                        row["duration"],
                    ]
                )

            return result

    def delete_test_executions(self, test_names, exec_id):
        self.con.executemany(
            f"""
            DELETE
            FROM test_execution
            WHERE {self._test_execution_fk_column()} = ?
              AND test_name = ?""",
            [(exec_id, test_name) for test_name in test_names],
        )

    def all_test_executions(self, exec_id):
        return {
            row[0]: {
                "duration": row[1],
                "failed": row[2],
            }
            for row in self.con.execute(
                f"""
                SELECT
                    test_name, duration, failed
                FROM test_execution
                WHERE {self._test_execution_fk_column()} = ?
                """,
                (exec_id,),
            )
        }

    def filenames(self, exec_id):
        cursor = self.con.execute(
            f"""
            SELECT DISTINCT
                f.filename
            FROM
                file_fp f, test_execution_file_fp te_ffp, test_execution te
            WHERE
                te.id = te_ffp.test_execution_id AND
                te_ffp.fingerprint_id = f.id AND
                te.{self._test_execution_fk_column()} = ?
                """,
            (exec_id,),
        )

        return [row[0] for row in cursor]

    @lru_cache(128)
    def filenames_fingerprints(self, exec_id):
        cursor = self.con.execute(
            f"""
            SELECT DISTINCT
                f.filename,
                f.mtime,
                f.checksum,
                f.id as fingerprint_id,
                sum(failed)
            FROM
                test_execution te, test_execution_file_fp te_ffp, file_fp f
            WHERE
                te.id = te_ffp.test_execution_id AND
                te_ffp.fingerprint_id = f.id AND
                {self._test_execution_fk_column()} = ?
            GROUP BY
                f.filename, f.mtime, f.checksum, f.id
            """,
            (exec_id,),
        )

        return [dict(row) for row in cursor]

    def fetch_or_create_environment(
        self, environment_name, system_packages, python_version
    ):
        with self.con as con:
            try:
                cursor = con.cursor()
                cursor.execute(
                    """
                    INSERT INTO environment VALUES (?, ?, ?, ?)
                    """,
                    (
                        None,
                        environment_name,
                        system_packages,
                        python_version,
                    ),
                )
                environment_id = cursor.lastrowid
                count = cursor.execute(
                    """
                    SELECT count(*) as count FROM environment WHERE environment_name = ?
                    """,
                    (environment_name,),
                ).fetchone()
                packages_changed = count["count"] > 1
            except sqlite3.IntegrityError:
                environment = con.execute(
                    """
                    SELECT
                    id as id, environment_name as name, system_packages as packages
                    FROM environment
                    WHERE environment_name = ?
                    """,
                    (environment_name,),
                ).fetchone()
                environment_id = environment["id"]
                packages_changed = False
        return environment_id, packages_changed

    def initiate_execution(
        self,
        environment_name,
        system_packages,
        python_version,
    ):
        exec_id, packages_changed = self.fetch_or_create_environment(
            environment_name, system_packages, python_version
        )
        return {
            "exec_id": exec_id,
            "filenames": self.filenames(exec_id),
            "packages_changed": packages_changed,
        }
