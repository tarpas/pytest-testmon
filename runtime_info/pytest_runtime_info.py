# -*- coding: utf-8 -*-

from collections import defaultdict
import os
import tempfile
import sqlite3

marks = list()

def pytest_sessionstart(session):
    conn = sqlite3.connect(os.path.join(str(session.config.rootdir), "runtime_test_report.db"))
    init_table(conn.cursor())
    conn.close()


def pytest_runtest_makereport(call, item):
    conn = sqlite3.connect(os.path.join(str(item.config.rootdir), "runtime_test_report.db"))
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys=on")

    with conn:
        if call.excinfo:
            last_mark_info = None
            exception_text = get_exception_text(call.excinfo)
            for traceback_entry in call.excinfo.traceback:
                if not is_project_path(traceback_entry.path, item.config.rootdir):
                    continue  # skiping files outside of project path
                striped_statement = str(traceback_entry.statement).lstrip()
                start = len(str(traceback_entry.statement)) - len(striped_statement)
                mark_info = {
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
                marks.append(mark_info)
                last_mark_info = mark_info
            if last_mark_info and not contains_exception(c, item.nodeid + ": " + exception_text):
                exception = {
                    "path": last_mark_info["path"],
                    "description": item.nodeid + ": " + exception_text,
                    "line": last_mark_info["line"],
                    "exception_text": exception_text
                }
                exception_id = insert_exception(c, exception)
                insert_file_mark(c, marks, exception_id)
        else:
            exception_id = contains_item(c, item.nodeid)
            if call.when == "call" and exception_id:
                remove_exception_by_nodeid(c, exception_id[0])
    marks.clear()
    conn.close()


def is_project_path(path, cwd):
    prefix = os.path.commonprefix([str(path), str(cwd)])
    if cwd == prefix:
        return True
    return False


def get_exception_text(excinfo):
    reason = str(excinfo.value)
    typename = str(excinfo.typename)
    return "{}: {}".format(typename, reason)

def contains_item(c, nodeid):
    c.execute("""SELECT exception_id,
                INSTR(description, :nodeid) found
                FROM Exception
                WHERE found > 0
    """, {"nodeid": nodeid})

    return c.fetchone()


def remove_exception_by_nodeid(c, exception_id):
    c.execute("""DELETE FROM Exception
                WHERE exception_id=:exception_id
    """, {"exception_id": exception_id})


def contains_exception(c, description):
    c.execute("""SELECT *
                FROM Exception
                WHERE description=:description
    """, {"description":description})

    if c.fetchall():
        return True
    return False


def init_table(c):
    # check if there is a table named FileMark in the database, if not: create
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='FileMark'")

    if c.fetchone() is None:
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


def insert_exception(c, excep):
    c.execute("""INSERT INTO Exception (
                file_name,
                line,
                description,
                exception_text
                )
                VALUES (:path, :line, :description, :exception_text)""", excep)

    return c.lastrowid


def insert_file_mark(c, mark_list, exception_id):
    for mark in mark_list:
        for mark_type in ["RedUnderLineDecoration", "Suffix"]:
            c.execute("""INSERT INTO FileMark (
                        type,
                        text,
                        file_name,
                        begin_line,
                        begin_character,
                        end_line,
                        end_character,
                        check_content,
                        exception_id)
                        VALUES (:type, :text, :file_name, :begin_line, :begin_character,
                                :end_line, :end_character, :check_output, :exception_id)""", {
                                    "type": mark_type,
                                    "text": mark["exception_text"],
                                    "file_name": mark["path"],
                                    "begin_line": mark["line"],
                                    "begin_character": mark["start"],
                                    "end_line": mark["line"],
                                    "end_character": mark["end"],
                                    "check_output": mark["check_output"],
                                    "exception_id": exception_id
                })

        if "prev" in mark:
            c.execute("""INSERT INTO FileMark
                        VALUES (:id, :type, :text, :file_name, :begin_line, :begin_character,
                                :end_line, :end_character, :check_output, :target_path,
                                :target_line, :target_character, :gutterLinkType, :exception_id)""", {
                                    "id": None,
                                    "type": "GutterLink",
                                    "text": mark["exception_text"],
                                    "file_name": mark["path"],
                                    "begin_line": mark["line"],
                                    "begin_character": mark["start"],
                                    "end_line": mark["line"],
                                    "end_character": mark["end"],
                                    "target_path": mark["prev"]["path"],
                                    "target_line": mark["prev"]["line"],
                                    "target_character": mark["prev"]["start"],
                                    "gutterLinkType": "U",
                                    "check_output": mark["check_output"],
                                    "exception_id": exception_id
                })

        if "next" in mark:
            c.execute("""INSERT INTO FileMark
                        VALUES (:id, :type, :text, :file_name, :begin_line, :begin_character,
                                :end_line, :end_character, :check_output,
                                :target_path, :target_line, :target_character, :gutterLinkType, :exception_id)""", {
                                    "id": None,
                                    "type": "GutterLink",
                                    "text": mark["exception_text"],
                                    "file_name": mark["path"],
                                    "begin_line": mark["line"],
                                    "begin_character": mark["start"],
                                    "end_line": mark["line"],
                                    "end_character": mark["end"],
                                    "target_path": mark["next"]["path"],
                                    "target_line": mark["next"]["line"],
                                    "target_character": mark["next"]["start"],
                                    "gutterLinkType": "D",
                                    "check_output": mark["check_output"],
                                    "exception_id": exception_id
                })
