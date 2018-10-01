# -*- coding: utf-8 -*-

from collections import defaultdict
import os
import json
import tempfile

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
                "exception_text": json.dumps(exception_text),
                "path": json.dumps(str(traceback_entry.path)),
                "line": traceback_entry.lineno,
                "start": start,
                "end": len(str(traceback_entry.statement)),
                "check_output": json.dumps(striped_statement)
            }
            if last_mark_info:
                mark_info["prev"] = last_mark_info
                last_mark_info["next"] = mark_info
            files[str(traceback_entry.path)].append(mark_info)
            last_mark_info = mark_info
        if last_mark_info:
            exceptions.append({
                "path": last_mark_info["path"],
                "description": json.dumps(item.nodeid + ": " + exception_text),
                "line": last_mark_info["line"]
            })


def pytest_sessionfinish():
    file_marks = [get_file_mark_json(path, marks) for path, marks in files.items()]
    file_marks_string = ",".join(file_marks)
    exception_strings = [get_exception_json(e) for e in exceptions]
    exception_string = ",".join(exception_strings)
    json_output = FILE_TEMPLATE.format(file_marks_string, exception_string)
    with open(get_temp_file_path(), "w") as output_file:
        output_file.write(json_output)


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


def get_exception_json(exception):
    return EXCEPTION_TEMPLATE.format(exception["path"],
                                     exception["description"],
                                     exception["line"])


def get_file_mark_json(path, mark_list):
    marks = [get_marks_json(mark) for mark in mark_list]
    return FILE_MARK_TEMPLATE.format(json.dumps(path), ",".join(marks))


def get_marks_json(mark):
    marks = []
    range_json = RANGE_TEMPLATE.format(mark["line"], mark["start"],
                                       mark["line"], mark["end"])
    underline_mark = UNDERLINE_MARK_TEMPLATE.format(range_json,
                                                    mark["check_output"])
    marks.append(underline_mark)
    suffix_mark = SUFFIX_MARK_TEMPLATE.format(mark["exception_text"],
                                              range_json,
                                              mark["check_output"])
    marks.append(suffix_mark)
    if "prev" in mark:
        target_path = mark["prev"]["path"]
        gutter_mark = GUTTER_MARK_TEMPLATE.format("U", target_path,
                                                  mark["prev"]["line"],
                                                  mark["prev"]["start"],
                                                  range_json,
                                                  mark["check_output"])
        marks.append(gutter_mark)
    if "next" in mark:
        target_path = mark["next"]["path"]
        gutter_mark = GUTTER_MARK_TEMPLATE.format("D", target_path,
                                                  mark["next"]["line"],
                                                  mark["next"]["start"],
                                                  range_json,
                                                  mark["check_output"])
        marks.append(gutter_mark)
    return ",".join(marks)


FILE_TEMPLATE = """
{{
  "fileMarkList":[{}
  ],
  "exceptions":[{}
  ]
}}
"""

EXCEPTION_TEMPLATE = """
    {{
      "path": {},
      "description": {},
      "line": {}
    }}
"""

FILE_MARK_TEMPLATE = """
    {{
        "path": {},
        "marks": [{}
        ]
    }}"""

UNDERLINE_MARK_TEMPLATE = """
        {{
          "type": "RedUnderLineDecoration",
          "range": {},
          "checkContent": {}
        }}"""

SUFFIX_MARK_TEMPLATE = """
        {{
          "type": "Suffix",
          "text": {},
          "range": {},
          "checkContent": {}
        }}"""

GUTTER_MARK_TEMPLATE = """
        {{
          "type": "GutterLink",
          "gutterLinkType": "{}",
          "targetPath": {},
          "target": {{
            "line": {},
            "character": {}
          }},
          "range": {},
          "checkContent": {}
        }}"""

RANGE_TEMPLATE = """
            {{
              "start": {{
                "line": {},
                "character": {}
              }},
              "end": {{
                "line": {},
                "character": {}
              }}
            }}"""
