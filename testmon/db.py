import json
import os
import sqlite3

from collections import namedtuple
from functools import lru_cache

from testmon.process_code import blob_to_checksums, checksums_to_blob


DATA_VERSION = 12

ChangedFileData = namedtuple(
    "ChangedFileData", "filename name method_checksums id failed"
)


class TestmonDbException(Exception):
    pass


def connect(datafile, connect_timeout, readonly=False):
    connection = sqlite3.connect(
        f"file:{datafile}{'?mode=ro' if readonly else ''}", uri=True, timeout=connect_timeout
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
    def __init__(self, datafile, connect_timeout):
        new_db = not os.path.exists(datafile)
        self.connect_timeout = connect_timeout

        connection = connect(datafile, self.connect_timeout)
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
        self.con = connect(datafile, self.connect_timeout)
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
                "UPDATE file_fp SET mtime=?, fsha=? WHERE id = ?", new_mtimes
            )

    def finish_execution(self, exec_id, duration=None, select=True):
        self.update_saving_stats(exec_id, select)
        self.fetch_or_create_file_fp.cache_clear()
        with self.con as con:
            self.vacuum_file_fp(con)

    def vacuum_file_fp(self, con):
        con.execute(
            """ DELETE FROM file_fp
                WHERE id NOT IN (
                    SELECT DISTINCT fingerprint_id FROM test_execution_file_fp) """
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
    def fetch_or_create_file_fp(self, filename, fsha, method_checksums):
        cursor = self.con.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO file_fp
                (filename, method_checksums, fsha)
                VALUES (?, ?, ?)
                """,
                (filename, method_checksums, fsha),
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
                te_id = self._insert_test_execution(
                    con,
                    exec_id,
                    test_name,
                    deps_n_outcomes.get("duration", None),
                    deps_n_outcomes.get("failed", None),
                    deps_n_outcomes.get("forced", None),
                )

                fingerprints = deps_n_outcomes["deps"]
                files_fshas = set()
                for record in fingerprints:
                    fingerprint_id = self.fetch_or_create_file_fp(
                        record["filename"],
                        record["fsha"],
                        checksums_to_blob(record["method_checksums"]),
                    )

                    test_execution_file_fps.append((te_id, fingerprint_id))
                    files_fshas.add((record["filename"], record["fsha"]))
            if test_execution_file_fps:
                cursor.executemany(
                    "INSERT INTO test_execution_file_fp VALUES (?, ?)",
                    test_execution_file_fps,
                )
                self.fetch_or_create_file_fp.cache_clear()
                self.insert_into_suite_files_fshas(con, exec_id, files_fshas)

    def insert_into_suite_files_fshas(self, con, exec_id, files_fshas):
        pass

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

                CREATE TABLE changed_files_fshas (exec_id INTEGER, filename TEXT, fsha TEXT);
                CREATE INDEX changed_files_fshas_mcall ON changed_files_fshas (exec_id, filename, fsha);

                CREATE TABLE changed_files_mhashes (exec_id INTEGER, filename TEXT, mhashes BLOB);
                CREATE INDEX changed_files_mhashes_eid ON changed_files_mhashes (exec_id);
            """

    def _create_file_fp_statement(self):
        return """
            CREATE TABLE file_fp
            (
                id INTEGER PRIMARY KEY,
                filename TEXT,
                method_checksums BLOB,
                mtime FLOAT,
                fsha TEXT,
                UNIQUE (filename, fsha, method_checksums)
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
            -- the following table stores the same data coarsely, but is used for faster queries
            CREATE TABLE suite_execution_file_fsha (
                suite_execution_id INTEGER,
                filename TEXT,
                fsha text,
                FOREIGN KEY(suite_execution_id) REFERENCES suite_execution(id)
                );
                CREATE UNIQUE INDEX sefch_suite_id_filename_sha ON suite_execution_file_fsha(suite_execution_id, filename, fsha);
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

    def fetch_unknown_files(self, files_fshas, exec_id):
        with self.con as con:
            con.execute("DELETE FROM changed_files_fshas WHERE exec_id = ?", (exec_id,))
            con.executemany(
                "INSERT INTO changed_files_fshas VALUES (?, ?, ?)",
                [(exec_id, file, fsha) for file, fsha in files_fshas.items()],
            )
            return self._fetch_unknown_files_from_one_v(con, exec_id, exec_id)

    def _fetch_unknown_files_from_one_v(self, con, exec_id, files_shas_id):
        result = []
        for row in con.execute(
            f"""
                SELECT DISTINCT
                    f.filename
                FROM test_execution te, test_execution_file_fp te_ffp, file_fp f
                LEFT OUTER JOIN changed_files_fshas chff
                ON f.filename = chff.filename and f.fsha = chff.fsha AND chff.exec_id = :files_shas_id
                WHERE
                    te.{self._test_execution_fk_column()} = :exec_id AND
                    te.id = te_ffp.test_execution_id AND
                    te_ffp.fingerprint_id = f.id AND
                    (f.fsha IS NULL OR chff.fsha IS NULL)
                """,
            {"files_shas_id": files_shas_id, "exec_id": exec_id},
        ):
            result.append(row["filename"])
        return result

    def delete_filenames(self, con):
        con.execute("DELETE FROM changed_files_mhashes")

    def determine_tests(self, exec_id, files_mhashes):
        with self.con as con:
            con.execute(
                f"UPDATE test_execution set forced = NULL WHERE {self._test_execution_fk_column()} = ?",
                [exec_id],
            )
            self.delete_filenames(con)
            con.executemany(
                "INSERT INTO changed_files_mhashes VALUES (?, ?, ?)",
                [
                    (exec_id, file, checksums_to_blob(mhashes) if mhashes else None)
                    for file, mhashes in files_mhashes.items()
                ],
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
                FROM test_execution te, test_execution_file_fp te_ffp, file_fp f, changed_files_mhashes chfm
                WHERE
                    chfm.exec_id = ? AND
                    te.{self._test_execution_fk_column()} = ? AND
                    te.id = te_ffp.test_execution_id AND
                    te_ffp.fingerprint_id = f.id AND
                    chfm.filename = f.filename
                """,
                [exec_id, exec_id],
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

            failing_tests = [
                row["test_name"]
                for row in self.con.execute(
                    f"""
                    SELECT
                        te.test_name
                    FROM test_execution te
                    WHERE
                        te.{self._test_execution_fk_column()} = ? AND
                        te.failed = 1
                    """,
                    [exec_id],
                )
            ]

            return {"affected": new_method_misses, "failing": failing_tests}

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

    def filenames_fingerprints(self, exec_id):
        cursor = self.con.execute(
            f"""
            SELECT DISTINCT
                f.filename,
                f.mtime,
                f.fsha,
                f.id as fingerprint_id,
                sum(failed)
            FROM
                test_execution te, test_execution_file_fp te_ffp, file_fp f
            WHERE
                te.id = te_ffp.test_execution_id AND
                te_ffp.fingerprint_id = f.id AND
                {self._test_execution_fk_column()} = ?
            GROUP BY
                f.filename, f.mtime, f.fsha, f.id
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
        execution_metadata,
    ):
        exec_id, packages_changed = self.fetch_or_create_environment(
            environment_name, system_packages, python_version
        )
        return {
            "exec_id": exec_id,
            "filenames": self.all_filenames(),
            "packages_changed": packages_changed,
        }
