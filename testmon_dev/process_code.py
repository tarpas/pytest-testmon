import ast
import hashlib
import textwrap
import zlib
import os

import re

from coverage.python import get_python_source

GAP_UNTIL_INDENT = '=GAP='

blank_re = re.compile(r"\s*(#|$)")


class Module(object):
    def __init__(self, source_code=None, file_name='<unknown>', rootdir='', fingerprints=None):
        self.blocks = []
        self.counter = 0
        self.source_code = source_code
        if fingerprints is not None:
            self._fingerprints = fingerprints
        else:
            self._fingerprints = None
            if source_code is None:
                source_code, _ = read_file_with_checksum(os.path.join(rootdir, file_name))
            else:
                source_code = textwrap.dedent(source_code)
            self.lines = source_code.splitlines()

    @property
    def checksums(self):
        return [block.checksum for block in self.blocks]

    @property
    def fingerprints(self):
        if self._fingerprints is not None:
            return self._fingerprints
        else:
            return self.lines


def function_lines(node, end, name='unknown'):
    def _next_lineno(i, end):
        try:
            return node[i + 1].lineno - 1
        except IndexError:
            return end
        except AttributeError:
            return None

    result = []

    if isinstance(node, ast.AST):
        for field_name, field_value in ast.iter_fields(node):
            result.extend(
                function_lines(field_value,
                               end,
                               name=node.__class__.__name__))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            result.extend(function_lines(item, _next_lineno(i, end)))
        if node and name == 'FunctionDef':
            result.append((node[0].lineno, end))
    return result


def read_file_with_checksum(absfilename):
    hasher = hashlib.sha1()
    source = get_python_source(absfilename)
    hasher.update(source.encode('utf-8'))
    return source, hasher.hexdigest()


def get_indent_spaces_count(line):
    space_count = 0
    for c in line:
        if c == ' ':
            space_count += 1
            continue
        elif c == '\t':
            space_count += 8 - (space_count % 8)
        else:
            return space_count


def block_list_list(afile, coverage):
    def gap_marks_until(body_start, body_end):
        while body_end < len(afile) and blank_re.match(afile[body_end]):
            body_end += 1

        # TODO implement check for subindeted multilines
        if body_end < len(afile):
            indent = get_indent_spaces_count(afile[body_end])
        else:
            indent = -1
        return [GAP_UNTIL_INDENT, indent], body_end

    function_begin_ends = dict(function_lines(ast.parse("\n".join(afile)), len(afile)))

    line_idx = 0

    result = []

    while line_idx < len(afile):
        line_idx += 1
        line = afile[line_idx - 1]

        if blank_re.match(line):
            continue

        if line_idx in function_begin_ends and line_idx not in coverage:
            # process function
            fingerprints, line_idx = gap_marks_until(line_idx, function_begin_ends[line_idx])
            result.extend(fingerprints)
        else:
            result.append(line)

    return result


def file_has_lines(afile, fingerprints):
    file_idx = 0
    fingerprint_idx = 0

    while file_idx < len(afile) and fingerprint_idx < len(fingerprints):

        if blank_re.match(afile[file_idx]):
            file_idx += 1
            continue

        if fingerprints[fingerprint_idx] == GAP_UNTIL_INDENT:
            fingerprint_idx += 1 # consume the GAP_UNTIL_INDENT parameter (indent_level)
            while file_idx < len(afile) and get_indent_spaces_count(afile[file_idx]) != fingerprints[fingerprint_idx]:
                file_idx += 1
            fingerprint_idx += 1
        else:
            if afile[file_idx] != fingerprints[fingerprint_idx]:
                return False

        file_idx += 1
        fingerprint_idx += 1

    if file_idx >= len(afile) and fingerprint_idx >= len(fingerprints):
        return True
    else:
        return False
