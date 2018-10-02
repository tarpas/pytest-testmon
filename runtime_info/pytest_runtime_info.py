# -*- coding: utf-8 -*-

from collections import defaultdict
import os
import json
import tempfile
import sqlite3

files = defaultdict(list)
exceptions = list()


def pytest_runtest_makereport(call, item):
    if call.excinfo:
        last_mark_info = None
        exception_text = get_exception_text(call.excinfo)
        for traceback_entry in call.excinfo.traceback:
            if not is_project_path(traceback_entry.path, item.config.rootdir):
                continue  # skiping files outside of project path
            striped_statement = str(traceback_entry.statement).lstrip()
            start = len(str(traceback_entry.statement)) - len(striped_statement)
            mark_info = {
                "description": item.nodeid + ": " + exception_text,
                "exception_text": exception_text,
                "path": str(traceback_entry.path),
                "line": traceback_entry.lineno,
                "start": start,
                "end": len(str(traceback_entry.statement)),
                "check_output": striped_statement
            }
            if last_mark_info:
                mark_info["prev"] = last_mark_info
                last_mark_info["next"] = mark_info
            files[str(traceback_entry.path)].append(mark_info)
            last_mark_info = mark_info
        if last_mark_info:
            exceptions.append({
                "path": last_mark_info["path"],
                "description": item.nodeid + ": " + exception_text,
                "line": last_mark_info["line"],
                "exception_text": exception_text
            })


def pytest_sessionfinish(session):
    # sqlite implementation
    conn = sqlite3.connect(os.path.join(str(session.config.rootdir), "runtime_test_report.db"))
    init_table(conn)

    for e in exceptions:
        insert_exception(conn, e["path"], e["line"], e["description"], e["exception_text"])

    for path, marks in files.items():
        insert_file_mark(conn, path, marks)
    conn.close()


def get_temp_file_path():
    tempdir = tempfile.gettempdir()
    return os.path.join(str(tempdir), "runtime_test_report.json")


def is_project_path(path, cwd):
    prefix = os.path.commonprefix([str(path), str(cwd)])
    if cwd == prefix:
        return True
    return False


def get_exception_text(excinfo):
    reason = str(excinfo.value)
    typename = str(excinfo.typename)
    return "{}: {}".format(typename, reason)


def init_table(conn):
    c = conn.cursor()

    # check if there is a table named FileMark in the database, if not: create
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='FileMark'")

    if c.fetchone() is None:
        with conn:
            c.execute("""CREATE TABLE Exception (
                        exception_id INTEGER PRIMARY KEY,
                        file_name text,
                        line integer,
                        description text,
                        exception_text text
            )""")

            c.execute("""CREATE TABLE FileMark (
                        file_mark_id INTEGER PRIMARY KEY,
                        type text,
                        text text,
                        file_name text,
                        begin_line integer,
                        begin_character integer,
                        end_line integer,
                        end_character integer,
                        check_content text,
                        target_path text,
                        target_line integer,
                        target_character integer,
                        gutterLinkType text,
                        exception_id integer NOT NULL,
                            FOREIGN KEY (exception_id) REFERENCES exception(exception_id)
                            ON DELETE CASCADE
            )""")
    # if tha tables are present, clear them
    else:
        with conn:
            c.execute("DELETE FROM Exception")
            c.execute("DELETE FROM FileMark")


def insert_exception(conn, path, line, description, exception_text):
    c = conn.cursor()
    with conn:
        c.execute("INSERT INTO Exception VALUES (?, ?, ?, ?, ?)", (None, path, line, description, exception_text))


def insert_file_mark(conn, path, mark_list):
    c = conn.cursor()

    for mark in mark_list:
        with conn:
            c.execute("""INSERT INTO FileMark VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, (
                        SELECT exception_id FROM Exception WHERE description = ?)
            )""", (None, "RedUnderLineDecoration", None, path, mark["line"], mark["start"],
                   mark["line"], mark["end"], mark["check_output"], None, None, None, None, mark["description"]))

            c.execute("""INSERT INTO FileMark VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, (
                        SELECT exception_id FROM Exception WHERE description = ?)
                        )""", (None, "Suffix", mark['exception_text'], path, mark["line"], mark["start"],
                               mark["line"], mark["end"], mark["check_output"], None, None, None, None,
                               mark["description"]))

            if "prev" in mark:
                c.execute("""INSERT INTO FileMark VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, (
                        SELECT exception_id FROM Exception WHERE description = ?)
                        )""", (None, "GutterLink", mark['exception_text'], path, mark["line"], mark["start"],
                               mark["line"], mark["end"], mark["check_output"], mark["prev"]["path"],
                               mark["prev"]["line"],
                               mark["prev"]["start"], "U", mark["description"]))

            if "next" in mark:
                c.execute("""INSERT INTO FileMark VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, (
                        SELECT exception_id FROM Exception WHERE description = ?)
                        )""", (None, "GutterLink", mark['exception_text'], path, mark["line"], mark["start"],
                               mark["line"], mark["end"], mark["check_output"], mark["next"]["path"],
                               mark["next"]["line"],
                               mark["next"]["start"], "D", mark["description"]))
