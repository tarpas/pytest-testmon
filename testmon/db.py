import json
import sqlite3
from functools import lru_cache
from collections import namedtuple

from testmon.process_code import blob_to_checksums

ChangedFileData = namedtuple("ChangedFileData", "file_name name checksums id failed")


def update_mtimes(connection, new_mtimes):
    with connection as con:
        con.executemany(
            "UPDATE fingerprint SET mtime=?, checksum=? WHERE id = ?", new_mtimes
        )


def remove_unused_fingerprints(connection):
    with connection as con:
        con.execute(
            """
            DELETE FROM fingerprint
            WHERE id NOT IN (
                SELECT DISTINCT fingerprint_id FROM node_fingerprint
            )
            """
        )


@lru_cache(None)
def fetch_or_create_fingerprint(connection, filename, mtime, checksum, fingerprint):
    cursor = connection.cursor()
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

        update_mtimes(connection, [(mtime, checksum, fingerprint_id)])
    return fingerprint_id


def insert_node_fingerprints(
    connection, environment, nodeid, fingerprint_records, result={}
):
    with connection as con:
        failed = any(r.get("outcome") == "failed" for r in result.values())
        cursor = con.cursor()
        cursor.execute(
            """ 
            INSERT OR REPLACE INTO node 
            (environment, name, result, failed) 
            VALUES (?, ?, ?, ?)
            """,
            (environment, nodeid, json.dumps(result), failed),
        )
        node_id = cursor.lastrowid

        for record in fingerprint_records:
            fingerprint_id = fetch_or_create_fingerprint(
                connection,
                record["filename"],
                record["mtime"],
                record["checksum"],
                record["fingerprint"],
            )

            cursor.execute(
                "INSERT INTO node_fingerprint VALUES (?, ?)",
                (node_id, fingerprint_id),
            )


def _write_attribute(connection, attribute, data, environment="default"):
    dataid = environment + ":" + attribute
    with connection as con:
        con.execute(
            "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
            [dataid, json.dumps(data)],
        )


def _fetch_attribute(connection, attribute, default=None, environment="default"):
    cursor = connection.execute(
        "SELECT data FROM metadata WHERE dataid=?",
        [environment + ":" + attribute],
    )
    result = cursor.fetchone()
    if result:
        return json.loads(result[0])
    else:
        return default


def init_tables(connection, DATA_VERSION, environment):
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

    _write_attribute(
        connection,
        "__data_version",
        str(DATA_VERSION),
        environment=environment or "default",
    )


def get_changed_file_data(
    connection, environment, changed_fingerprints
) -> [ChangedFileData]:
    in_clause_questionsmarks = ", ".join("?" * len(changed_fingerprints))
    result = []
    for row in connection.execute(
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
            environment,
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
