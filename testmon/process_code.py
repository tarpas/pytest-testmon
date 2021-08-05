import ast
import hashlib
import textwrap
import os
import zlib
import re

from coverage.python import get_python_source

try:
    from coverage.exceptions import NoSource
except:
    from coverage.misc import NoSource
from array import array
import sqlite3

CHECKUMS_ARRAY_TYPE = "I"


def encode_lines(lines):
    checksums = []
    for line in lines:
        checksums.append(zlib.adler32(line.encode("UTF-8")))

    return checksums


def checksums_to_blob(checksums):
    blob = array(CHECKUMS_ARRAY_TYPE, checksums)
    data = blob.tobytes()
    return sqlite3.Binary(data)


def blob_to_checksums(blob):
    a = array(CHECKUMS_ARRAY_TYPE)
    a.frombytes(blob)
    return a.tolist()


GAP_MARKS = {i: f"{i}GAP" for i in range(-1, 64)}
INVERTED_GAP_MARKS_CHECKSUMS = {encode_lines([f"{i}GAP"])[0]: i for i in range(-1, 64)}

blank_re = re.compile(r"\s*(#|$)")


class Module(object):
    def __init__(
        self,
        source_code=None,
        file_name="<unknown>",
        rootdir="",
        mtime=None,
        checksum=None,
    ):

        if source_code is None:
            absfilename = os.path.join(rootdir, file_name)
            mtime = os.path.getmtime(absfilename)
            source_code, checksum = read_file_with_checksum(absfilename)
        else:
            source_code = textwrap.dedent(source_code)
        self.source_code = source_code
        self.checksum = checksum
        self.mtime = mtime
        self.lines = source_code.splitlines()
        self.full_lines = list(filter(lambda x: not blank_re.match(x), self.lines))
        self._full_lines_checksums = []

        try:
            self.ast = ast.parse(source_code)
            self.special_blocks = dict(function_lines(self.ast, len(self.lines)))
        except SyntaxError:
            pass

    @property
    def full_lines_checksums(self):
        if not self._full_lines_checksums:
            self._full_lines_checksums = encode_lines(self.full_lines)
        return self._full_lines_checksums


def function_lines(node, end):
    def _next_lineno(i, end):
        try:
            return node[i + 1].decorator_list[0].lineno - 1
        except (IndexError, AttributeError):
            pass

        try:
            return node[i + 1].lineno - 1
        except IndexError:
            return end
        except AttributeError:
            return None

    result = []

    if isinstance(node, ast.AST):
        if node.__class__.__name__ == "FunctionDef":
            result.append((node.body[0].lineno, end))

        for field_name, field_value in ast.iter_fields(node):
            result.extend(function_lines(field_value, end))

    elif isinstance(node, list):
        for i, item in enumerate(node):
            result.extend(function_lines(item, _next_lineno(i, end)))

    return result


def read_file_with_checksum(absfilename):
    hasher = hashlib.sha1()
    try:
        source = get_python_source(absfilename)
    except NoSource:
        return None, None
    hasher.update(source.encode("utf-8"))
    return source, hasher.hexdigest()


def get_indent_level(line):
    space_count = 0
    for c in line:
        if c == " ":
            space_count += 1
            continue
        elif c == "\t":
            space_count += 8 - (space_count % 8)
        else:
            return space_count
    return space_count


def cover_subindented_multilines(lines, start, end, indent_threshold):
    fingerprints = []
    in_subindented_area = False
    while start < end - 1:
        start += 1
        line = lines[start]
        if blank_re.match(lines[start]):
            continue

        curr_indent = get_indent_level(line)
        if curr_indent <= indent_threshold:
            fingerprints.append(line)
            in_subindented_area = True
        else:
            if in_subindented_area:
                fingerprints.append(GAP_MARKS[curr_indent - 1])
                in_subindented_area = False

    if in_subindented_area:
        fingerprints.append(GAP_MARKS[0])
    return fingerprints


def gap_marks_until(lines, start, end):
    if start < len(lines):
        indent_threshold = get_indent_level(lines[start]) - 1
    else:
        indent_threshold = 0

    fingerprints = cover_subindented_multilines(lines, start, end, indent_threshold)
    return [GAP_MARKS[indent_threshold]] + fingerprints, end


def covered_unused_statement(start, end, coverage):
    while start <= end:
        if start in coverage:
            return True
        start += 1
    return False


def create_fingerprints(afile, special_blocks, coverage):
    line_idx = 0
    result = []
    while line_idx < len(afile):
        line_idx += 1
        line = afile[line_idx - 1]

        if blank_re.match(line):
            continue

        if (
            line_idx in special_blocks
            and line_idx not in coverage
            and not covered_unused_statement(
                line_idx + 1, special_blocks[line_idx], coverage
            )
        ):
            fingerprints, line_idx = gap_marks_until(
                afile, line_idx - 1, special_blocks[line_idx]
            )
            result.extend(fingerprints)
        else:
            result.append(line)
    return result


def file_has_lines(full_lines, fingerprints):
    file_idx = 0
    fingerprint_idx = 0

    while file_idx < len(full_lines) and fingerprint_idx < len(fingerprints):

        searching_indent = INVERTED_GAP_MARKS_CHECKSUMS.get(
            fingerprints[fingerprint_idx]
        )
        if searching_indent is not None:
            while (
                file_idx < len(full_lines)
                and get_indent_level(full_lines[file_idx]) > searching_indent
            ):
                file_idx += 1
        else:
            if encode_lines([full_lines[file_idx]])[0] != fingerprints[fingerprint_idx]:
                return False
            file_idx += 1

        fingerprint_idx += 1

    if file_idx >= len(full_lines) and fingerprint_idx >= len(fingerprints):
        return True
    else:
        return False
