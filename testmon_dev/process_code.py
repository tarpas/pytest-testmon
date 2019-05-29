import ast
import hashlib
import textwrap
import zlib
import os

import re

from coverage.parser import PythonParser
from coverage.python import get_python_source

END_OF_FILE_MARK = '=END OF FILE='
GAP_MARK = '=GAP='

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

    def coverage_to_fingerprints(self, coverage):

        return block_list_list(self.fingerprints, coverage)


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


def create_emental(blocks):
    blocks = blocks.copy()
    module_level_block = blocks.pop()
    line_numbers = set(range(1, module_level_block.end + 1))
    for block in blocks:
        line_numbers.difference_update(set(range(block.start, block.end + 1)))
    return line_numbers


def is_end_of_block(line_indent, indents):
    # Cycle is needed due to 'test_block_end_with_more_indents2'
    while line_indent < indents[-1]:
        indents.pop()
        if not indents:
            return True
    return False


def block_list_list(afile, coverage, multilines=None):
    l2 = []
    l1 = []
    if not coverage:
        return l1

    indents = []
    if multilines is None:
        multilines = {}
    is_last_non_blank_line_covered = False

    for (line_idx, line) in enumerate(afile, 1):
        line_indent = get_indent_spaces_count(line)

        # Skip blank lines
        if blank_re.match(line):
            continue

        # Check for end of block if we are inside one
        if l2 and multilines.get(line_idx) is None and is_end_of_block(line_indent, indents):
            l1.append(l2)
            l2 = []
            continue

        # Skip non-covered lines
        if not (line_idx in coverage):
            is_last_non_blank_line_covered = False
            continue

        # Start of new covered block
        if not l2:
            add_previous_line(l2, afile, line_idx)
            indents.append(line_indent)
            l2.append(line)
            is_last_non_blank_line_covered = True
            continue

        # Check for GAP -> last non blank line is not covered
        # For reason to use 'is_last_non_blank_line_covered' see 'test_two_empty_lines_after_gap'
        if not is_last_non_blank_line_covered:
            l2.append(GAP_MARK)

        # Check indentation
        if line_indent > indents[-1]:  # Line is from new block
            indents.append(line_indent)

        l2.append(line)

    if l2:
        l1.append(l2)

    return l1


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


def add_previous_line(l2, afile, i):
    i = i - 2
    if i < 0:
        return

    while blank_re.match(afile[i]):
        i -= 1
        if i < 0:
            return

    l2.append(afile[i])


class DoesntHaveException(Exception):
    pass


def get_real_subblock_length(subblock):
    subblock_length = len(subblock)
    if END_OF_FILE_MARK in subblock:
        return subblock_length - 1
    else:
        return subblock_length


def match_fingerprints(file_lines, fingerprints):
    def get_indent(line_idx):
        return get_indent_spaces_count(file_lines[line_idx])

    def gap_ends(line_idx):
        indent_before_gap = get_indent(line_idx - 1)
        while line_idx < file_lines_count and (get_indent(line_idx) > indent_before_gap):
            line_idx += 1
        return line_idx

    if len(file_lines) < get_real_subblock_length(fingerprints):
        raise DoesntHaveException()

    line_idx = 0
    first_line_indent = 0
    file_lines_count = len(file_lines)
    subblock_idx = 0

    while True:
        # Skip all gap lines or stop at the end of file
        if fingerprints[subblock_idx] == GAP_MARK:
            line_idx = gap_ends(line_idx)

        elif fingerprints[subblock_idx] == file_lines[line_idx]:  # Found block line
            if line_idx == 0:
                first_line_indent = get_indent(line_idx)
            line_idx += 1
        else:
            return match_fingerprints(file_lines[1:], fingerprints)

        subblock_idx += 1
        if subblock_idx == len(fingerprints):
            if (line_idx == file_lines_count or
                    # Check correct dedent - see 'test_new_line_after_indent' and
                    # 'test_new_line_after_gap' in 'test_process_code.py'
                    get_indent_spaces_count(file_lines[line_idx]) <= first_line_indent):

                return file_lines[line_idx:]
            else:
                return match_fingerprints(file_lines[1:], fingerprints)


def file_has_lines(file_fingerprints, required_fingerprints):
    non_empty_lines = []
    for e in file_fingerprints:
        if not blank_re.match(e):
            non_empty_lines.append(e)

    try:
        for rf in required_fingerprints:
            non_empty_lines = match_fingerprints(non_empty_lines, rf)
        return True
    except DoesntHaveException:
        return False
