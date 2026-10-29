# # ifdef SERVER
import random
import sqlite3
import timeit

pytest_plugins = ("pytester",)

methods = 10000
VERSIONS = 50
TIME_LIMIT = 0.5


def random_32B():
    return random.randint(0, 2**31 - 1)


def repo_and_version():
    version = [random_32B() for _ in range(methods)]
    all_versions = []
    for version_id in range(VERSIONS):
        for _ in range(random.randint(1, 3)):
            version[random.randint(0, methods - 1)] = random_32B()

        all_versions.append(version[:])

        if version_id == VERSIONS - 5:
            look_for = version[:] + [random_32B() for _ in range(len(version) * 10)]
    return all_versions, look_for


def add_version_index(con):
    con.execute("CREATE TABLE version (version_id int, file_version int) ")
    con.execute("CREATE INDEX version_id_in ON version(version_id, file_version)")
    # con.execute("CREATE INDEX file_version_in ON version(file_version)")

    con.execute("CREATE TABLE look_for (file_version int)")
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
        "SELECT count(v.version_id) c1, count(lf.file_version) c2, version_id FROM version v left outer join look_for lf on v.file_version = lf.file_version   "
        + "GROUP BY version_id HAVING c1 < (c2+4)",
    ).fetchmany(200)
    con.execute("delete from look_for")

    print(results)


def test_sqlite_normal_index(testdir):
    con = sqlite3.connect(".test_pick_version_fts5.db")
    add_version_index(con)

    all_versions, look_for = repo_and_version()
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


# # endif
