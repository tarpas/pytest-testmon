# -*- coding: utf-8 -*-

from collections import defaultdict
import os
import sqlite3

marks = list()


def get_db_path(config):
    return os.path.join(config.rootdir.strpath, ".runtime_info0")


def should_run(config):
    return config.getoption('--runtime-info') or os.path.exists(get_db_path(config))


def pytest_configure(config):
    if should_run(config):
        config.pluginmanager.register(RuntimeInfo(), "RuntimeInfo")


def pytest_addoption(parser):
    parser.addoption(
        "--runtime-info", action="store_true", default=False, help="Run with runtime-info plugin."
    )


class RuntimeInfo(object):

    def pytest_sessionstart(self, session):
        db_path = get_db_path(session.config)
        db_exists = os.path.exists(db_path)

        conn = sqlite3.connect(db_path)

        if not db_exists:
            init_tables(conn)
            session.config.db_created = True

        conn.execute("PRAGMA recursive_triggers = TRUE ")
        conn.execute("PRAGMA foreign_keys=on")

        session.config.conn = conn

    def pytest_report_header(self, config, startdir):
        if hasattr(config, 'db_created'):
            return ['Database for runtime-info plugin created']
        else:
            return []

    def pytest_collection_modifyitems(self, session, config, items):
        conn = config.conn
        c = conn.cursor()
        nodeids = get_all_nodeids(c)
        config.nodeids = nodeids

    def pytest_runtest_makereport(self, call, item):
        conn = item.config.conn
        c = conn.cursor()

        with conn:
            if call.excinfo:
                stacktrace_length = 0
                last_mark_info = None
                exception_text = get_exception_text(call.excinfo)
                for traceback_entry in call.excinfo.traceback:
                    if not is_project_path(traceback_entry.path, item.config.rootdir):
                        continue  # skiping files outside of project path
                    statement = str(traceback_entry.statement)
                    start = len(str(traceback_entry.statement)) - len(statement)
                    mark_info = {
                        "exception_text": exception_text,
                        "path": str(os.path.relpath(traceback_entry.path.strpath, item.config.rootdir.strpath)),
                        "line": traceback_entry.lineno,
                        "start": start,
                        "end": len(str(traceback_entry.statement)),
                        "check_content": statement
                    }
                    if last_mark_info:
                        mark_info["prev"] = last_mark_info
                        last_mark_info["next"] = mark_info
                    marks.append(mark_info)
                    last_mark_info = mark_info
                    stacktrace_length += 1
                if last_mark_info:
                    exception_id = insert_exception(c,
                                                    item.nodeid,
                                                    exception_text,
                                                    last_mark_info,
                                                    stacktrace_length)
                    insert_file_mark(c, marks, exception_id)
            elif call.when == 'setup' and item.nodeid in item.config.nodeids:
                remove_exception_by_nodeid(c, item.nodeid)
        marks.clear()


def get_all_nodeids(c):
    c.execute("SELECT nodeid FROM Exception")
    return {nodeid[0] for nodeid in c.fetchall()}


def is_project_path(path, cwd):
    prefix = os.path.commonprefix([str(path), str(cwd)])
    if cwd == prefix:
        return True
    return False


def get_exception_text(excinfo):
    reason = str(excinfo.value)
    typename = str(excinfo.typename)
    return "{}: {}".format(typename, reason)


def remove_exception_by_nodeid(c, nodeid):
    c.execute("""DELETE FROM Exception
                WHERE nodeid=:nodeid
    """, {"nodeid": nodeid})


def init_tables(conn):
    # check if there is a table named FileMark in the database, if not: create

    for statement in CREATE_STATEMENTS:
        conn.execute(statement)


def insert_exception(c, nodeid, text, mark, stacktrace_length):
    query_parameters = [nodeid, mark["path"], mark["line"], text, stacktrace_length]
    c.execute("""INSERT OR REPLACE INTO Exception (
                nodeid,
                file_name,
                line,
                exception_text,
                stacktrace_length
                )
                VALUES (:nodeid, :file_name, :line, :exception_text, :stacktrace_length)""", query_parameters)

    return c.lastrowid


def insert_file_mark(c, mark_list, exception_id):
    for mark in mark_list:
        param_list = []

        common_params = {
            "file_name": mark["path"],
            "begin_line": mark["line"],
            "check_content": mark["check_content"],
            "exception_id": exception_id
        }

        for mark_type in ["RedUnderLineDecoration", "Suffix"]:
            param_list.append(dict(
                common_params,
                **{
                    "type": mark_type,
                    "text": mark["exception_text"],
                    "begin_character": mark["start"],
                    "end_line": mark["line"],
                    "end_character": mark["end"],
                    "exception_id": exception_id
                }))

        if "prev" in mark:
            up = dict(common_params,
                      **{"type": "GutterLink",
                         "gutterLinkType": "U",
                         "target_path": mark["prev"]["path"],
                         "target_line": mark["prev"]["line"],
                         "target_character": mark["prev"]["start"],
                         })
            param_list.append(up)

        if "next" in mark:
            down = dict(common_params,
                        **{
                            "type": "GutterLink",
                            "gutterLinkType": "D",
                            "target_path": mark["next"]["path"],
                            "target_line": mark["next"]["line"],
                            "target_character": mark["next"]["start"],
                        })
            param_list.append(down)

        for params in param_list:
            c.execute("""INSERT INTO FileMark
                         VALUES (:id, :type, :text, :file_name, :begin_line, :begin_character,
                                :end_line, :end_character, :check_content, :target_path,
                                :target_line, :target_character, :gutterLinkType, :exception_id)""",
                      defaultdict(lambda: None, params))


# These constitute the protocol towards front-end, don't forget to change front-end when changing this.
CREATE_STATEMENTS = [
    """        
    CREATE TABLE Exception (
    exception_id INTEGER PRIMARY KEY,
    nodeid text UNIQUE, -- any "test/nodeid" can have at most one exception 
    file_name text, -- file_name:line is used in a list of exceptions. It's the most sensible place where user 
                    -- should be navigated when double-clicking the exception.  (Not implemented yet)  
    line integer, -- see above
    exception_text text, -- eg "ZeroDivisionError: division by zero"
    stacktrace_length integer
    )
    """
    ,
    """
    CREATE TABLE FileMark (
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
            ON DELETE CASCADE)
    """
]
