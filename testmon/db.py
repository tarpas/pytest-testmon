import json
import os
import sqlite3

from collections import namedtuple
from functools import lru_cache

from testmon.process_code import blob_to_checksums, checksums_to_blob


DATA_VERSION = 8

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

    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = OFF")
    connection.execute("PRAGMA foreign_keys = TRUE ")
    connection.execute("PRAGMA recursive_triggers = TRUE ")
    connection.row_factory = sqlite3.Row
    return connection


def check_fingerprint_db(files_methods_checksums, record):
    file = record[0]
    fingerprint = record[2]

    if file in files_methods_checksums and files_methods_checksums[file]:
        if set(fingerprint) - set(files_methods_checksums[file]):
            return False
        return True
    return False


class DB:
    def __init__(self, datafile):
        new_db = not os.path.exists(datafile)

        connection = connect(datafile)
        self.con = connection
        old_format = self._check_data_version(datafile)

        if new_db or old_format:
            self.init_tables()

    def version_compatibility(self):
        return DATA_VERSION

    def _check_data_version(self, datafile):
        stored_data_version = self._fetch_data_version()

        if int(stored_data_version) == self.version_compatibility():
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

    def finish_execution(self, exec_id, duration=None, select=True):
        self.update_saving_stats(exec_id, select)
        self.fetch_or_create_file_fp.cache_clear()
        with self.con as con:
            con.execute(
                """
                DELETE FROM file_fp
                WHERE id NOT IN (
                    SELECT DISTINCT fingerprint_id FROM test_execution_file_fp
                )
                """
            )

    def fetch_current_run_stats(self, exec_id):
        with self.con as con:
            cursor = con.cursor()
            run_saved_tests, run_saved_time = cursor.execute(
                f"""
                    SELECT count(*), sum(te.duration) FROM test_execution te
                    WHERE te.forced IS NOT False
                    AND te.{self._test_execution_fk_column()} = ?
                """,
                (exec_id,),
            ).fetchone()
            run_all_tests, run_all_time = cursor.execute(
                f"""
                    SELECT count(*), sum(te.duration) FROM test_execution te
                    WHERE te.{self._test_execution_fk_column()} = ?
                """,
                (exec_id,),
            ).fetchone()

        return (
            run_saved_time,
            run_all_time,
            run_saved_tests,
            run_all_tests,
        )

    def update_saving_stats(self, exec_id, select):
        (
            run_saved_time,
            run_all_time,
            run_saved_tests,
            run_all_tests,
        ) = self.fetch_current_run_stats(exec_id)

        attribute_prefix = "" if select else "potential_"
        self.increment_attributes(
            {
                f"{attribute_prefix}time_saved": run_saved_time,
                f"{attribute_prefix}time_all": run_all_time,
                f"{attribute_prefix}tests_saved": run_saved_tests,
                f"{attribute_prefix}tests_all": run_all_tests,
            },
            exec_id=None,
        )

    def fetch_saving_stats(self, exec_id, select):
        (
            run_saved_time,
            run_all_time,
            run_saved_tests,
            run_all_tests,
        ) = self.fetch_current_run_stats(exec_id)
        attribute_prefix = "" if select else "potential_"
        total_saved_time = self.fetch_attribute(
            attribute=f"{attribute_prefix}time_saved", default=0, exec_id=None
        )
        total_all_time = self.fetch_attribute(
            attribute=f"{attribute_prefix}time_all", default=0, exec_id=None
        )
        total_saved_tests = self.fetch_attribute(
            attribute=f"{attribute_prefix}tests_saved", default=0, exec_id=None
        )
        total_all_tests = self.fetch_attribute(
            attribute=f"{attribute_prefix}tests_all", default=0, exec_id=None
        )

        return (
            run_saved_time,
            run_all_time,
            run_saved_tests,
            run_all_tests,
            total_saved_time,
            total_all_time,
            total_saved_tests,
            total_all_tests,
        )

    @lru_cache(1000)
    def fetch_or_create_file_fp(self, filename, checksum, method_checksums):
        cursor = self.con.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO file_fp
                (filename, method_checksums, checksum)
                VALUES (?, ?, ?)
                """,
                (filename, method_checksums, checksum),
            )

            fingerprint_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            fingerprint_id, *_ = cursor.execute(
                """
                SELECT
                    id
                FROM
                    file_fp
                WHERE
                    filename = ? AND method_checksums = ?
                """,
                (filename, method_checksums),
            ).fetchone()

        return fingerprint_id

    def _insert_test_execution(
        self,
        con,
        exec_id,
        test_name,
        duration,
        failed,
        forced,
    ):
        cursor = con.cursor()
        cursor.execute(
            f"""
                INSERT INTO test_execution
                ({self._test_execution_fk_column()}, test_name, duration, failed, forced)
                VALUES (?, ?, ?, ?, ?)
                """,
            (
                exec_id,
                test_name,
                duration,
                1 if failed else 0,
                forced,
            ),
        )
        return cursor.lastrowid

    def insert_test_file_fps(self, tests_deps_n_outcomes, exec_id=None):
        assert exec_id
        with self.con as con:
            cursor = con.cursor()

            cursor.executemany(
                f"DELETE FROM test_execution_file_fp "
                f"WHERE test_execution_id in "
                f"      (SELECT id FROM test_execution WHERE {self._test_execution_fk_column()}=? AND test_name=?)",
                [(exec_id, test_name) for test_name in tests_deps_n_outcomes],
            )

            cursor.executemany(
                f"DELETE FROM test_execution WHERE {self._test_execution_fk_column()}=? AND test_name=?",
                [(exec_id, test_name) for test_name in tests_deps_n_outcomes],
            )

            test_execution_file_fps = []
            for test_name, deps_n_outcomes in tests_deps_n_outcomes.items():
                failed = deps_n_outcomes.get("failed", None)
                duration = deps_n_outcomes.get("duration", None)
                forced = deps_n_outcomes.get("forced", None)
                te_id = self._insert_test_execution(
                    con,
                    exec_id,
                    test_name,
                    duration,
                    failed,
                    forced,
                )

                fingerprints = deps_n_outcomes["deps"]
                for record in fingerprints:
                    fingerprint_id = self.fetch_or_create_file_fp(
                        record["filename"],
                        record["checksum"],
                        checksums_to_blob(record["method_checksums"]),
                    )

                    test_execution_file_fps.append((te_id, fingerprint_id))
            cursor.executemany(
                "INSERT INTO test_execution_file_fp VALUES (?, ?)",
                test_execution_file_fps,
            )
            self.fetch_or_create_file_fp.cache_clear()
            cursor.execute(
                "DELETE FROM file_fp where id not in (select fingerprint_id from test_execution_file_fp)"
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

    def increment_attributes(self, attributes_to_increment, exec_id=None):
        def sum_with_none(*to_sum):
            return sum(filter(None, to_sum))

        for attribute_name in attributes_to_increment:
            dataid = f"{exec_id}:{attribute_name}"
            old_value = self.fetch_attribute(
                attribute=attribute_name, default=0, exec_id=exec_id
            )
            with self.con as con:
                con.execute(
                    "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
                    [
                        dataid,
                        sum_with_none(
                            old_value, attributes_to_increment[attribute_name]
                        ),
                    ],
                )

    def _create_metadata_statement(self):
        return """CREATE TABLE metadata (dataid TEXT PRIMARY KEY, data TEXT);"""

    def _create_environment_statement(self):
        return """
                CREATE TABLE environment (
                id INTEGER PRIMARY KEY ASC,
                environment_name TEXT,
                system_packages TEXT,
                python_version TEXT,
                UNIQUE (environment_name, system_packages, python_version)
            );"""

    def _create_test_execution_statement(self):
        return f"""
                CREATE TABLE test_execution (
                id INTEGER PRIMARY KEY ASC,
                {self._test_execution_fk_column()} INTEGER,
                test_name TEXT,
                duration FLOAT,
                failed BIT,
                forced BIT,
                FOREIGN KEY({self._test_execution_fk_column()}) REFERENCES {self._test_execution_fk_table()}(id));
                CREATE INDEX test_execution_fk_name ON test_execution ({self._test_execution_fk_column()}, test_name);
                                                
                CREATE TABLE mcall_id (id INTEGER PRIMARY KEY ASC, exec_id INTEGER);

                CREATE TABLE temp_files_checksums (mcall_id INTEGER, filename TEXT, checksum TEXT);
                CREATE INDEX temp_files_checksums_mcall ON temp_files_checksums (mcall_ID);
            
                CREATE TABLE temp_filenames (mcall_id INTEGER, filename TEXT);
                CREATE INDEX temp_filenames_mcall ON temp_filenames (mcall_id);
            """

    def _create_file_fp_statement(self):
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

    def _create_test_execution_ffp_statement(
        self,
    ):
        return """
            CREATE TABLE test_execution_file_fp (
                test_execution_id INTEGER,
                fingerprint_id INTEGER,
                FOREIGN KEY(test_execution_id) REFERENCES test_execution(id),                
                FOREIGN KEY(fingerprint_id) REFERENCES file_fp(id)
            );
            CREATE INDEX test_execution_file_fp_both ON test_execution_file_fp (test_execution_id, fingerprint_id);
            """

    def init_tables(self):
        connection = self.con

        connection.executescript(
            self._create_metadata_statement()
            + self._create_environment_statement()
            + self._create_test_execution_statement()
            + self._create_file_fp_statement()
            + self._create_test_execution_ffp_statement()
        )

        connection.execute(f"PRAGMA user_version = {self.version_compatibility()}")

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

    def fetch_unknown_files(self, files_checksums, exec_id):
        with self.con as con:
            con.execute(
                f"UPDATE test_execution set forced = NULL WHERE {self._test_execution_fk_column()} = ?",
                [exec_id],
            )
            cursor = con.cursor()
            cursor.execute("INSERT INTO mcall_id (exec_id) VALUES (?)", [exec_id])
            mcall_id = cursor.lastrowid
            self.con.execute("DELETE FROM temp_files_checksums")
            con.executemany(
                "INSERT INTO temp_files_checksums VALUES (?, ?, ?)",
                [
                    (mcall_id, file, checksum)
                    for file, checksum in files_checksums.items()
                ],
            )
            result = []
            for row in self.con.execute(
                f"""
                SELECT DISTINCT 
                    f.filename
                FROM test_execution te, test_execution_file_fp te_ffp, file_fp f
                LEFT OUTER JOIN temp_files_checksums tfc
                ON f.filename = tfc.filename and f.checksum = tfc.checksum AND tfc.mcall_id = ?
                WHERE
                    te.{self._test_execution_fk_column()} = ? AND
                    te.id = te_ffp.test_execution_id AND
                    te_ffp.fingerprint_id = f.id AND
                    (f.checksum IS NULL OR tfc.checksum IS NULL OR f.checksum <> tfc.checksum)
                """,
                [mcall_id, exec_id],
            ):
                result.append(row["filename"])

            return result

    def determine_tests(self, exec_id, files_mhashes):
        with self.con as con:
            cursor = con.cursor()
            cursor.execute("INSERT INTO mcall_id (exec_id) VALUES (?)", [exec_id])
            mcall_id = cursor.lastrowid
            con.execute("DELETE FROM temp_filenames")
            con.executemany(
                "INSERT INTO temp_filenames VALUES (?, ?)",
                list(
                    (
                        mcall_id,
                        k,
                    )
                    for k in files_mhashes
                ),
            )

            results = []
            for row in self.con.execute(
                f"""
                SELECT
                    f.filename,
                    te.test_name,
                    f.method_checksums,
                    te.failed,
                    te.duration
                FROM test_execution te, test_execution_file_fp te_ffp, file_fp f, temp_filenames tf
                WHERE
                    tf.mcall_id = ? AND
                    te.{self._test_execution_fk_column()} = ? AND
                    te.id = te_ffp.test_execution_id AND
                    te_ffp.fingerprint_id = f.id AND
                    tf.filename = f.filename
                """,
                [mcall_id, exec_id],
            ):
                results.append(
                    [
                        row["filename"],
                        row["test_name"],
                        blob_to_checksums(row["method_checksums"]),
                    ]
                )

            new_method_misses = []
            for result in results:
                if not check_fingerprint_db(files_mhashes, result):
                    new_method_misses.append(result[1])

            return {"affected": new_method_misses}

    def delete_test_executions(self, test_names, exec_id):
        self.con.executemany(
            f"""
            DELETE
            FROM test_execution_file_fp
            WHERE test_execution_id IN
                (SELECT id FROM test_execution WHERE {self._test_execution_fk_column()} = ? AND test_name = ?)
                """,
            [(exec_id, test_name) for test_name in test_names],
        )
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
            row[0]: {"duration": row[1], "failed": row[2], "forced": row[3]}
            for row in self.con.execute(
                f"""
                SELECT
                    test_name, duration, failed, forced
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

    def all_filenames(self):
        cursor = self.con.execute(
            """
            SELECT DISTINCT
                f.filename
            FROM
                file_fp f
                """,
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
