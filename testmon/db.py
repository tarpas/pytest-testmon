import json
import os
import sqlite3

from collections import namedtuple
from sqlite3 import Binary
from typing import List, Optional

from testmon.process_code import (
    blob_to_checksums,
    checksums_to_blob,
    Fingerprint,
    Fingerprints,
)

DATA_VERSION = 0

ChangedFileData = namedtuple(
    "ChangedFileData", "filename name method_checksums id failed"
)


class TestmonDbException(Exception):
    pass


def connect(datafile: os.PathLike):
    connection = sqlite3.connect(datafile)

    connection.execute("PRAGMA synchronous = OFF")
    connection.execute("PRAGMA foreign_keys = TRUE ")
    connection.execute("PRAGMA recursive_triggers = TRUE ")
    connection.row_factory = sqlite3.Row
    return connection

def merge_dbs(merged_datafile, db_1: "DB", db_2: "DB") -> "DB":
    if db_1.env != db_2.env:
        raise

    merged_db = DB(merged_datafile, environment=db_1.env)
    with merged_db:
        with db_1:
            for data in db_1.all_data():
                merged_db.insert_node_fingerprints(data["name"], fingerprints=[data], failed=data["failed"],
                                                   duration=data["duration"])

        with db_2:
            for data in db_2.all_data():
                merged_db.insert_node_fingerprints(data["name"], fingerprints=[data], failed=data["failed"],
                                                   duration=data["duration"])

    return merged_db


class DB:
    def __init__(self, datafile: os.PathLike, environment: str = "default"):
        new_db = not os.path.exists(datafile)

        connection = connect(datafile)
        self.con = connection
        self.env = environment

        old_format = self._check_data_version(datafile)

        if new_db or old_format:
            self.init_tables()

    def _check_data_version(self, datafile: os.PathLike) -> bool:
        stored_data_version = self._fetch_data_version()

        if int(stored_data_version) == DATA_VERSION:
            return False

        self.con.close()
        os.remove(datafile)
        self.con = connect(datafile)
        return True

    def __enter__(self) -> "DB":
        self.con = self.con.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.con.__exit__(*args, **kwargs)

    def update_mtimes(self, new_mtimes: float):
        with self.con as con:
            con.executemany(
                "UPDATE fingerprint SET mtime=?, checksum=? WHERE id = ?", new_mtimes
            )

    def remove_unused_fingerprints(self):
        with self.con as con:
            con.execute(
                """
                DELETE FROM fingerprint
                WHERE id NOT IN (
                    SELECT DISTINCT fingerprint_id FROM node_fingerprint
                )
                """
            )

    def fetch_or_create_fingerprint(self, filename: str, mtime: float, checksum: str, method_checksums: Binary) -> int:
        cursor = self.con.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO fingerprint
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
                    fingerprint
                WHERE
                    filename = ? AND method_checksums = ?
                """,
                (filename, method_checksums),
            ).fetchone()

            self.update_mtimes([(mtime, checksum, fingerprint_id)])
        return fingerprint_id

    def insert_node_fingerprints(
        self, nodeid: str, fingerprints: Fingerprints, failed: bool = False, duration: Optional[float] = None
    ):
        with self.con as con:
            cursor = con.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO node
                (environment, name, duration, failed)
                VALUES (?, ?, ?, ?)
                """,
                (
                    self.env,
                    nodeid,
                    duration,
                    1 if failed else 0,
                ),
            )
            node_id = cursor.lastrowid

            # record: Fingerprint
            for record in fingerprints:
                fingerprint_id = self.fetch_or_create_fingerprint(
                    record["filename"],
                    record["mtime"],
                    record["checksum"],
                    checksums_to_blob(record["method_checksums"]),
                )

                cursor.execute(
                    "INSERT INTO node_fingerprint VALUES (?, ?)",
                    (node_id, fingerprint_id),
                )

    def _fetch_data_version(self):
        con = self.con

        return con.execute("PRAGMA user_version").fetchone()[0]

    def _write_attribute(self, attribute: str, data: dict, environment: Optional[str] = None):
        dataid = (environment or self.env) + ":" + attribute
        with self.con as con:
            con.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
                [dataid, json.dumps(data)],
            )

    def _fetch_attribute(self, attribute: str, default=None, environment=None):
        cursor = self.con.execute(
            "SELECT data FROM metadata WHERE dataid=?",
            [(environment or self.env) + ":" + attribute],
        )
        result = cursor.fetchone()
        if result:
            return json.loads(result[0])
        return default

    def init_tables(self):
        connection = self.con

        connection.execute("CREATE TABLE metadata (dataid TEXT PRIMARY KEY, data TEXT)")

        connection.execute(
            """
            CREATE TABLE node (
                id INTEGER PRIMARY KEY ASC,
                environment TEXT,
                name TEXT,
                duration FLOAT,
                failed BIT,
                UNIQUE (environment, name)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE node_fingerprint (
                node_id INTEGER,
                fingerprint_id INTEGER,
                FOREIGN KEY(node_id) REFERENCES node(id) ON DELETE CASCADE,
                FOREIGN KEY(fingerprint_id) REFERENCES fingerprint(id)
            )
            """
        )

        connection.execute(
            """
            CREATE table fingerprint
            (
                id INTEGER PRIMARY KEY,
                filename TEXT,
                method_checksums BLOB,
                mtime FLOAT,
                checksum TEXT,
                UNIQUE (filename, method_checksums)
            )
            """
        )

        connection.execute(f"PRAGMA user_version = {DATA_VERSION}")

    def get_changed_file_data(self, changed_fingerprints: Fingerprints):
        in_clause_questionsmarks = ", ".join("?" * len(changed_fingerprints))
        result = []
        for row in self.con.execute(
            f"""
            SELECT
                f.filename,
                n.name,
                f.method_checksums,
                f.id,
                n.failed,
                n.duration
            FROM node n, node_fingerprint nfp, fingerprint f
            WHERE
                n.environment = ? AND
                n.id = nfp.node_id AND
                nfp.fingerprint_id = f.id AND
                f.id IN ({in_clause_questionsmarks})
            """,
            [
                self.env,
            ]
            + list(changed_fingerprints),
        ):
            result.append(
                [
                    row["filename"],
                    row["name"],
                    blob_to_checksums(row["method_checksums"]),
                    row["id"],
                    row["failed"],
                    row["duration"],
                ]
            )

        return result

    def delete_nodes(self, nodeids):
        self.con.executemany(
            """
            DELETE
            FROM node
            WHERE environment = ?
              AND name = ?""",
            [(self.env, nodeid) for nodeid in nodeids],
        )

    def all_nodes(self):
        return {
            row[0]: {
                "duration": row[1],
                "failed": row[2],
            }
            for row in self.con.execute(
                """
                SELECT
                    name, duration, failed
                FROM node
                WHERE environment = ?
                """,
                (self.env,),
            )
        }

    def filenames_fingerprints(self):
        cursor = self.con.execute(
            """
            SELECT DISTINCT
                f.filename,
                f.mtime,
                f.checksum,
                f.id as fingerprint_id,
                sum(failed)
            FROM
                node n, node_fingerprint nfp, fingerprint f
            WHERE
                n.id = nfp.node_id AND
                nfp.fingerprint_id = f.id AND
                environment = ?
            GROUP BY
                f.filename, f.mtime, f.checksum, f.id
            """,
            (self.env,),
        )

        return [dict(row) for row in cursor]

    def all_data(self) -> List[dict]:
        cursor = self.con.execute(
            """
            SELECT 
                n.name,
                n.duration,
                n.failed,
                f.filename,
                f.method_checksums,
                f.mtime,
                f.checksum
            FROM
                node n, node_fingerprint nfp, fingerprint f
            WHERE
                n.id = nfp.node_id AND
                nfp.fingerprint_id = f.id AND
                environment = ?
            """,
            (self.env,),
        )
        return [dict(row) for row in cursor]
