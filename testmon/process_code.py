import ast
import hashlib
import textwrap
import os
import zlib

from coverage.python import get_python_source
from coverage.misc import NoSource


def encode_lines(lines):
    checksums = []
    for line in lines:
        checksums.append(zlib.adler32(line.encode("UTF-8")) & 0xffffffff)

    return checksums


GAP_MARKS = {i: "{}GAP".format(i) for i in range(-1, 64)}
INVERTED_GAP_MARKS_CHECKSUMS = {encode_lines(["{}GAP".format(i)])[0]: i for i in range(-1, 64)}


def is_blank_line(line):
    """
    Quite a bit faster than using re.compile and re.match, and this
    executes on hundreds of millions of lines:

    In [69]: timeit(lambda: is_blank_line('     # hi'), number=10000000)
    Out[69]: 2.4501168727874756

    In [70]: blank_re = re.compile(r"\s*(#|$)")
    In [71]: timeit(lambda: blank_re.match('     # hi'), number=10000000)
    Out[71]: 3.775568962097168
    """
    stripped_line = line.lstrip()
    return stripped_line == '' or stripped_line[0] == '#'


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
        self.full_lines = list(filter(lambda x: not is_blank_line(x), self.lines))
        self._full_lines_checksums = []

        self.special_blocks = {}
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
    line_expanded = line.expandtabs(8)
    return len(line_expanded) - len(line_expanded.lstrip())


def cover_subindented_multilines(lines, start, end, indent_threshold):
    fingerprints = []
    in_subindented_area = False
    while start < end - 1:
        start += 1
        line = lines[start]
        if is_blank_line(lines[start]):
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
    return any(i in coverage for i in range(start, end))


def create_fingerprints(lines, special_blocks, coverage):
    line_idx = 0
    result = []
    while line_idx < len(lines):
        line = lines[line_idx]
        line_idx += 1
        line = lines[line_idx - 1]

        if is_blank_line(line):
            continue

        if (
            line_idx in special_blocks
            and line_idx not in coverage
            and not covered_unused_statement(
                line_idx + 1, special_blocks[line_idx], coverage
            )
        ):
            fingerprints, line_idx = gap_marks_until(
                lines, line_idx - 1, special_blocks[line_idx]
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
