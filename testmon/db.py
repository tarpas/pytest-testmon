import json
import sqlite3
from functools import lru_cache
from collections import namedtuple

from testmon.process_code import blob_to_checksums

ChangedFileData = namedtuple("ChangedFileData", "file_name name checksums id failed")


class DB(object):
    def __init__(self, connection, environment="default"):
        self.con = connection
        self.env = environment

    def __enter__(self):
        self.other_con = self.con
        self.con = self.con.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.con.__exit__(*args, **kwargs)
        self.con = self.other_con

    def update_mtimes(self, new_mtimes):
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

    @lru_cache(None)
    def fetch_or_create_fingerprint(self, filename, mtime, checksum, fingerprint):
        cursor = self.con.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO fingerprint
                (file_name, fingerprint, mtime, checksum)
                VALUES (?, ?, ?, ?)
                """,
                (filename, fingerprint, mtime, checksum),
            )

            fingerprint_id = cursor.lastrowid
        except sqlite3.IntegrityError as e:

            fingerprint_id, db_mtime, db_checksum = cursor.execute(
                "SELECT id, mtime, checksum FROM fingerprint WHERE file_name = ? AND fingerprint = ?",
                (
                    filename,
                    fingerprint,
                ),
            ).fetchone()

            self.update_mtimes([(mtime, checksum, fingerprint_id)])
        return fingerprint_id

    def insert_node_fingerprints(self, nodeid: str, fingerprint_records, result={}):
        with self.con as con:
            failed = any(r.get("outcome") == "failed" for r in result.values())
            cursor = con.cursor()
            cursor.execute(
                """ 
                INSERT OR REPLACE INTO node 
                (environment, name, result, failed) 
                VALUES (?, ?, ?, ?)
                """,
                (self.env, nodeid, json.dumps(result), failed),
            )
            node_id = cursor.lastrowid

            for record in fingerprint_records:
                fingerprint_id = self.fetch_or_create_fingerprint(
                    record["filename"],
                    record["mtime"],
                    record["checksum"],
                    record["fingerprint"],
                )

                cursor.execute(
                    "INSERT INTO node_fingerprint VALUES (?, ?)",
                    (node_id, fingerprint_id),
                )

    def _write_attribute(self, attribute, data, environment=None):
        dataid = (environment or self.env) + ":" + attribute
        with self.con as con:
            con.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
                [dataid, json.dumps(data)],
            )

    def _fetch_attribute(self, attribute, default=None, environment=None):
        cursor = self.con.execute(
            "SELECT data FROM metadata WHERE dataid=?",
            [(environment or self.env) + ":" + attribute],
        )
        result = cursor.fetchone()
        if result:
            return json.loads(result[0])
        else:
            return default

    def init_tables(self, DATA_VERSION):
        connection = self.con

        connection.execute("CREATE TABLE metadata (dataid TEXT PRIMARY KEY, data TEXT)")

        connection.execute(
            """
            CREATE TABLE node (
                id INTEGER PRIMARY KEY ASC,
                environment TEXT,
                name TEXT,
                result TEXT,
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
                file_name TEXT,
                fingerprint TEXT,
                mtime FLOAT,
                checksum TEXT,
                UNIQUE (file_name, fingerprint)            
            )
            """
        )

        self._write_attribute(
            "__data_version",
            str(DATA_VERSION),
        )

    def get_changed_file_data(self, changed_fingerprints) -> [ChangedFileData]:
        in_clause_questionsmarks = ", ".join("?" * len(changed_fingerprints))
        result = []
        for row in self.con.execute(
            """
                                SELECT
                                    f.file_name,
                                    n.name,
                                    f.fingerprint,
                                    f.id,
                                    n.failed
                                FROM node n, node_fingerprint nfp, fingerprint f
                                WHERE 
                                    n.environment = ? AND
                                    n.id = nfp.node_id AND 
                                    nfp.fingerprint_id = f.id AND
                                    f.id IN (%s)"""
            % in_clause_questionsmarks,
            [
                self.env,
            ]
            + list(changed_fingerprints),
        ):
            result.append(
                ChangedFileData(
                    row["file_name"],
                    row["name"],
                    blob_to_checksums(row["fingerprint"]),
                    row["id"],
                    row["failed"],
                )
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
            row[0]: json.loads(row[1])
            for row in self.con.execute(
                """  SELECT name, result
                                    FROM node 
                                    WHERE environment = ?
                                   """,
                (self.env,),
            )
        }

    def filenames_fingerprints(self):
        return self.con.execute(
            """
                SELECT DISTINCT 
                    f.file_name, f.mtime, f.checksum, f.id as fingerprint_id, sum(failed) 
                FROM node n, node_fingerprint nfp, fingerprint f 
                WHERE n.id = nfp.node_id AND 
                      nfp.fingerprint_id = f.id AND 
                      environment = ?
                GROUP BY 
                    f.file_name, f.mtime, f.checksum, f.id""",
            (self.env,),
        ).fetchall()
