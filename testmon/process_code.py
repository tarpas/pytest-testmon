import ast
import hashlib
import textwrap
import zlib
import os

import re
from coverage.python import get_python_source

END_OF_FILE_MARK = '=END OF FILE='

blank_re = re.compile(r"\s*(#|$)")
coding_re = re.compile(b'coding[=:]\s*([-\w.]+)')

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
    def __init__(self, source_code=None, filename='<unknown>', rootdir='', fingerprints=None):
        self.blocks = []
        self.counter = 0
        if fingerprints:
            self._fingerprints = fingerprints
        else:
            self._fingerprints = None
            if source_code is None:
                source_code, _ = read_file_with_checksum(os.path.join(rootdir, filename))
            else:
                source_code = textwrap.dedent(source_code)
            self.lines = source_code.splitlines()
            try:
                tree = ast.parse(source_code, filename)
                self.dump_and_block(tree, len(self.lines), name=filename)
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
        if self._fingerprints:
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


def human_coverage(analysis):
    result = set()

    source = analysis.file_reporter.source()
    statements = sorted(analysis.statements)
    missing = sorted(analysis.missing)

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
            continue
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


def block_list_list(afile, coverage):
    previous = 'N/A'
    nonempty = {}
    i = 0
    for (lineno, line) in enumerate(afile, start=1):
        if not blank_re.match(line):
            nonempty[lineno] = i
            i += 1

    l2 = []
    l1 = []
    for i in sorted(coverage):
        current_nonempty_line = nonempty[i]
        previous_non_empty_line = nonempty.get(previous, current_nonempty_line - 1)

        if not (previous_non_empty_line == current_nonempty_line - 1):
            add_non_executed_line_in_the_end(l2, afile, previous)
            l1.append(l2)
            l2 = []

        if not l2:
            add_non_executed_line_in_the_beginning(l2, afile, i - 2)

        l2.append(afile[i - 1])
        previous = i

    if l2:
        add_non_executed_line_in_the_end(l2, afile, previous)
        l1.append(l2)
    return l1


def add_non_executed_line_in_the_beginning(l2, afile, i):
    if i < 0:
        return

    while blank_re.match(afile[i]):
        i -= 1
        if i < 0:
            return

    l2.append(afile[i])


def add_non_executed_line_in_the_end(l2, afile, i):
    if i > len(afile) - 1:
        l2.append(END_OF_FILE_MARK)
        return

    while blank_re.match(afile[i]):
        i += 1
        if i > len(afile) - 1:
            l2.append(END_OF_FILE_MARK)
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


def the_rest_after(act_file_lines, subblock):

    if len(act_file_lines) < get_real_subblock_length(subblock):
        raise DoesntHaveException()

    i = 0

    for subblock_line in subblock:
        # This fix case when user add line at the end of file
        # TODO It create antoher false positives when non-executed line is added
        if subblock_line == END_OF_FILE_MARK and i >= len(act_file_lines):
            i += 1
            continue

        if subblock_line == act_file_lines[i]:
            i += 1

    if i == len(subblock):
        return act_file_lines[i-1:]
    else:
        return the_rest_after(act_file_lines[1:], subblock)


def file_has_lines(file_fingerprints, required_fingerprints):
    non_empty_lines = []
    for e in file_fingerprints:
        if not blank_re.match(e):
            non_empty_lines.append(e)

    try:
        for rf in required_fingerprints:
            non_empty_lines = the_rest_after(non_empty_lines, rf)
        return True
    except DoesntHaveException:
        return False
