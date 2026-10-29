# # ifdef SERVER
import base64
import os
import random
import sqlite3
import timeit
import pytest
import sys

pytest_plugins = ("pytester",)

WIDTH = 999
VERSIONS = 250
TIME_LIMIT = 0.5


def bytes_to_word(bytes_input):
    return (base64.b32encode(bytes_input).decode("utf-8")).lower().replace("=", "9")


def file_versions_to_words(file_versions):
    return [bytes_to_word(file_version) for file_version in file_versions]


def add_version_index_fts(con):
    con.execute("CREATE VIRTUAL TABLE version USING fts5 (version_id, file_versions)")


def insert_version_fts(con, version_id, version):
    con.execute(
        "INSERT INTO version VALUES (?, ?)",
        [version_id, " ".join(file_versions_to_words(version))],
    )


def pick_best_version_fts(con, look_for):
    return con.execute(
        "SELECT version_id FROM version WHERE file_versions"
        + " MATCH ? "
        + " ORDER BY bm25(version) limit 1",
        (" OR ".join(file_versions_to_words(look_for)),),
    ).fetchall()[0][0]


def random_32B():
    return os.urandom(32)


def repo_n_version():
    version = [random_32B() for _ in range(WIDTH)]
    all_versions = []
    for version_id in range(VERSIONS):
        for _ in range(random.randint(1, 5)):
            version[random.randint(0, WIDTH - 1)] = random_32B()

        all_versions.append(version[:])

        if version_id == VERSIONS - 5:
            look_for = version[:]
    return all_versions, look_for


@pytest.mark.skipif(sys.platform == "win32", reason="Windows platform")
def test_sqlite_fts5_version_pick(testdir):
    con = sqlite3.connect(".test_pick_version_fts5.db")
    add_version_index_fts(con)

    start = timeit.default_timer()
    all_versions, look_for = repo_n_version()
    for id, version in enumerate(all_versions):
        insert_version_fts(con, id, version)

    stop = timeit.default_timer()
    print("Inserting 1 row took: ", (stop - start) / VERSIONS)

    start = timeit.default_timer()
    result = pick_best_version_fts(con, look_for)
    stop = timeit.default_timer()

    print("fts5 time to find best version: ", stop - start)
    assert result == VERSIONS - 5
    assert (stop - start) < TIME_LIMIT


def add_version_index(con):
    con.execute("CREATE TABLE version (version_id int, file_version blob) ")
    con.execute("CREATE INDEX version_id_in ON version(version_id)")
    con.execute("CREATE INDEX file_version_in ON version(file_version)")

    con.execute("CREATE TABLE look_for (file_version blob)")
    con.execute("CREATE INDEX look_for_in ON look_for(file_version)")


def insert_version(con, version_id, version):
    con.executemany(
        "INSERT INTO version VALUES (?, ?)",
        [
            (
                version_id,
                file_version,
            )
            for file_version in version
        ],
    )


def pick_best_version(con, look_for):
    con.executemany("INSERT INTO look_for VALUES (?)", [(x,) for x in look_for])
    results = con.execute(
        "SELECT count(*), version_id FROM version v, look_for lf WHERE "
        + "v.file_version = lf.file_version GROUP BY version_id ORDER BY version_id DESC"
    ).fetchmany(200)
    con.execute("delete from look_for")

    by_count = dict(results)
    return by_count[max(by_count)] if by_count else None


def test_sqlite_normal_index(testdir):
    con = sqlite3.connect(".test_pick_version_fts5.db")
    add_version_index(con)

    all_versions, look_for = repo_n_version()
    start = timeit.default_timer()
    with con:
        for id, version in enumerate(all_versions):
            insert_version(con, id, version)
    stop = timeit.default_timer()
    print("Inserting 1 row took: ", (stop - start) / VERSIONS)

    start = timeit.default_timer()
    result = pick_best_version(con, look_for)
    stop = timeit.default_timer()

    print("plain sqlite index time to find best version: ", stop - start)
    assert result == VERSIONS - 5
    assert (stop - start) < TIME_LIMIT


def test_python():
    """This doesn't contain any real serialization, store, load, deserialize so
    it's not apples to apples comparison"""

    all_versions, look_for = repo_n_version()

    all_versions_sets = [set(version) for version in all_versions]

    start = timeit.default_timer()
    counts = {}
    look_for_set = set(look_for)
    for version_id in range(VERSIONS):
        counts[len(look_for_set.intersection(all_versions_sets[version_id]))] = (
            version_id
        )
    print(counts[max(counts)])
    stop = timeit.default_timer()
    print("Python time to find best version: ", stop - start)


# # endif
