import ast
import hashlib
import textwrap
import zlib
import os

import re

from coverage.parser import PythonParser
from coverage.python import get_python_source

END_OF_FILE_MARK = '=END OF FILE='
GAP_UNTIL_INDENT = '=GAP='

blank_re = re.compile(r"\s*(#|$)")


class Block():
    def __init__(self, start, end, code=0, name=''):
        # assert start <= end
        self.start = start
        self.end = end
        self.name = name
        self.code = code

    @property
    def checksum(self):
        if isinstance(self.code, int):
            return str(self.code)
        else:
            return zlib.adler32(self.code.encode('UTF-8')) & 0xffffffff

    def __repr__(self):
        return "{}-{} h: {}, n:{}, repr:{}".format(self.start,
                                                   self.end,
                                                   self.checksum,
                                                   self.name,
                                                   self.code)

    def __eq__(self, other):
        return (self.start,
                self.end,
                self.checksum,
                self.name) == (other.start,
                               other.end,
                               other.checksum,
                               other.name)

    def __ne__(self, other):
        return not self.__eq__(other)


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
            try:
                tree = ast.parse(source_code, file_name)
                self.dump_and_block(tree, len(self.lines), name=file_name)
            except SyntaxError as e:
                pass

    def dump_and_block(self, node, end, name='unknown', into_block=False):
        """Frame of this method is taken from ast.dump
        Objective is to return a representation of python source code where
        all of the bodies of functions are replaced with 'transformed_into_block'
        string. The rest of the syntax tree is represented in the same way as
        in ast.dump(tree, annotate_fields=False). Of course the bodies of functions
        are not completely thrown away, they are transformed into Block() objects
        and appended to self.blocks. More can be probably understood from
        (at the time rather messy) test_process_code.py examples.
        """

        def _next_lineno(i, end):
            try:
                return node[i + 1].lineno - 1
            except IndexError:
                return end
            except AttributeError:
                return None

        if isinstance(node, ast.AST):
            class_name = node.__class__.__name__
            fields = []
            for field_name, field_value in ast.iter_fields(node):
                transform_into_block = ((class_name in ('FunctionDef', 'Module'))
                                        and field_name == 'body')
                fields.append((field_name,
                               self.dump_and_block(field_value,
                                                   end,
                                                   name=getattr(node, 'name', 'unknown'),
                                                   into_block=transform_into_block)))
            return '%s(%s)' % (class_name,
                               ', '.join((field_value for field_name, field_value in fields))
                               )
        elif isinstance(node, list):
            representations = []
            for i, item in enumerate(node):
                representations.append(self.dump_and_block(item, _next_lineno(i, end)))
            if into_block and node:
                self.blocks.append(Block(node[0].lineno,
                                         end,
                                         code=str(self.counter) + ":" + ", ".join(representations), name=name))
                self.counter += 1
                return 'transformed_into_block'
            else:
                return ", ".join(representations)
        return repr(node)

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


def checksum_coverage(blocks, lines):
    result = []
    line_index = 0
    sorted_lines = sorted(list(lines))

    for current_block in sorted(blocks, key=lambda x: x.start):
        try:
            while sorted_lines[line_index] < current_block.start:
                line_index += 1
            if sorted_lines[line_index] <= current_block.end:
                result.append(current_block.checksum)
        except IndexError:
            break

    return result


def read_file_with_checksum(absfilename):
    hasher = hashlib.sha1()
    source = get_python_source(absfilename)
    hasher.update(source.encode('utf-8'))
    return source, hasher.hexdigest()


blank_re = re.compile(r"\s*(#|$)")
else_finally_re = re.compile(r"\s*(else|finally)\s*:\s*(#|$)")


def human_coverage(source, statements, missing):
    result = set()

    i = 0
    j = 0
    covered = True
    for lineno, line in enumerate(source.splitlines(True), start=1):
        while i < len(statements) and statements[i] < lineno:
            i += 1
        while j < len(missing) and missing[j] < lineno:
            j += 1
        if i < len(statements) and statements[i] == lineno:
            covered = j >= len(missing) or missing[j] > lineno
        if blank_re.match(line):
            result.add(lineno)
        if else_finally_re.match(line):
            # Special logic for lines containing only 'else:'.
            if i >= len(statements) or j >= len(missing):
                result.add(lineno)
            elif statements[i] == missing[j]:
                pass
            else:
                result.add(lineno)
        elif covered:
            result.add(lineno)
        else:
            pass

    return result


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


def file_has_lines(afile, fingerprints):
    file_idx = 0
    fingerprint_idx = 0

    while file_idx < len(afile) and fingerprint_idx < len(fingerprints):

        if blank_re.match(afile[file_idx]):
            file_idx += 1
            continue

        if fingerprints[fingerprint_idx] == GAP_UNTIL_INDENT:
            fingerprint_idx += 1
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
