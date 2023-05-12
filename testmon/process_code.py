import ast
import textwrap
import zlib
from functools import lru_cache
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional, Union
from array import array
from subprocess import run, CalledProcessError

from coverage.phystokens import source_encoding

CHECKUMS_ARRAY_TYPE = "i"


def to_signed(unsigned33):
    unsigned33 = unsigned33 & 0xFFFFFFFF
    return (unsigned33 ^ 0x80000000) - 0x80000000


def debug_encode_lines(lines):
    return lines


def debug_code_to_blob(checksums):
    return ";\n".join(checksums)


def debug_blob_to_code(blob):
    return blob.split(";\n")


def methods_to_checksums(blocks):
    checksums = []
    for block in blocks:
        checksums.append(to_signed(zlib.crc32(block.encode("UTF-8"))))

    return checksums


def checksums_to_blob(checksums):
    blob = array(CHECKUMS_ARRAY_TYPE, checksums)
    data = blob.tobytes()
    return sqlite3.Binary(data)


def blob_to_checksums(blob):
    arr = array(CHECKUMS_ARRAY_TYPE)
    arr.frombytes(blob)
    return arr.tolist()


GAP_MARKS = {i: f"{i}GAP" for i in range(-1, 64)}
INVERTED_GAP_MARKS_CHECKSUMS = {
    methods_to_checksums([f"{i}GAP"])[0]: i for i in range(-1, 64)
}


class Block:
    def __init__(self, start, end, code=0, name=""):
        self.start = start
        self.end = end
        self.name = name
        self.code = code

    @property
    def checksum(self):
        return self.code

    def __repr__(self):
        return f"{self.start}-{self.end} h: {self.checksum}, n:{self.name}, repr:{self.code}"

    def __eq__(self, other):
        return (self.start, self.end, self.checksum, self.name) == (
            other.start,
            other.end,
            other.checksum,
            other.name,
        )

    def __ne__(self, other):
        return not self.__eq__(other)


@lru_cache(300)
def bytes_to_string_and_fsha(byte_stream):
    byte_stream = byte_stream.replace(b"\f", b" ")
    byte_stream = byte_stream.replace(b"\r\n", b"\n")
    byte_string = byte_stream.decode(source_encoding(byte_stream), "replace")
    git_header = b"blob %u\0" % len(byte_string)
    hsh = hashlib.sha1()
    hsh.update(git_header)
    hsh.update(byte_stream)
    if byte_string and byte_string[-1] != "\n":
        byte_string += "\n"
    return byte_string, hsh.hexdigest()


def _next_lineno(nodes, i, end):
    try:
        return nodes[i + 1].lineno - 1
    except IndexError:
        return end
    except AttributeError:
        return None


class Module:
    def __init__(
        self,
        source_code=None,
        mtime=None,
        ext="py",
        fs_fsha=None,
        filename=None,
        rootdir=None,
    ):
        self.filename = filename
        self.rootdir = rootdir
        self._blocks = None
        self.counter = 0
        self.mtime = mtime
        self._source_code = (
            None if source_code is None else textwrap.dedent(source_code)
        )
        self.fs_fsha = (
            fs_fsha or bytes_to_string_and_fsha(bytes(source_code, "utf-8"))[1]
        )
        self.ext = ext

    def dump_and_block(self, node, end, name="unknown", into_block=False):
        if isinstance(node, ast.AST):
            class_name = node.__class__.__name__
            fields = []
            for field_name, field_value in ast.iter_fields(node):
                transform_into_block = (
                    class_name in ("AsyncFunctionDef", "FunctionDef", "Module")
                ) and field_name == "body"
                fields.append(
                    (
                        field_name,
                        self.dump_and_block(
                            field_value,
                            end,
                            name=getattr(node, "name", "unknown"),
                            into_block=transform_into_block,
                        ),
                    )
                )
            return f"{class_name}({', '.join((field_value for field_name, field_value in fields))})"
        if isinstance(node, list):
            representations = []
            for i, item in enumerate(node):
                representations.append(
                    self.dump_and_block(item, _next_lineno(node, i, end))
                )
            if into_block and node:
                self._blocks.append(
                    Block(
                        node[0].lineno,
                        end,
                        code=str(self.counter) + ":" + ", ".join(representations),
                        name=name,
                    )
                )
                self.counter += 1
                return "transformed_into_block"
            return ", ".join(representations)
        return repr(node)

    @property
    def checksums(self):
        return methods_to_checksums([block.checksum for block in self.blocks])

    @property
    def blocks(self):
        if self._blocks is None:
            self._blocks = []
            lines = self.source_code.splitlines()
            if self.ext == "py":
                try:
                    tree = ast.parse(self.source_code, filename="<unknown>")
                    self.dump_and_block(tree, len(lines), name="<module>")
                except SyntaxError:
                    pass
            else:
                self._blocks = [Block(1, len(lines), self.source_code)]
        return self._blocks

    @property
    def source_code(self):
        if self._source_code is None:
            self._source_code = read_source_sha(Path(self.rootdir) / self.filename)[0]
        return self._source_code

    @property
    def method_checksums(self):
        return methods_to_checksums([block.checksum for block in self.blocks])


def read_source_sha(filename):
    # source_bytes: Optional[bytes]

    try:
        with open(filename, "rb") as file:
            source_bytes = file.read()
    except FileNotFoundError:
        return None, None

    source, fsha = bytes_to_string_and_fsha(source_bytes)
    return source, fsha


def noncached_get_files_shas(directory):
    all_shas = {}
    try:
        result = run(
            ["git", "ls-files", "--stage", "-m", directory],
            capture_output=True,
            universal_newlines=True,
            check=True,
        )
    except (FileNotFoundError, CalledProcessError):
        return all_shas

    modified_files = set()
    for line in result.stdout.splitlines():
        _, hsh, filename_with_junk = line.split(" ", 2)
        _, filename = filename_with_junk.split("\t", 1)
        if filename in all_shas:
            modified_files.add(filename)
        else:
            all_shas[filename] = hsh
    for modified_file in modified_files:
        del all_shas[modified_file]
    return all_shas


@lru_cache()
def get_files_shas(directory):
    return noncached_get_files_shas(directory)


def get_source_sha(directory, filename):
    try:
        sha = get_files_shas(directory)[filename]
        return (None, sha)
    except KeyError:
        pass
    return read_source_sha(Path(directory) / filename)


def match_fingerprint_source(source_code, fingerprint, ext="py"):
    module = Module(source_code=source_code, ext=ext)
    return match_fingerprint(module, fingerprint)


def match_fingerprint(module, fingerprint):
    if set(fingerprint) - set(module.checksums):
        return False
    return True


def create_fingerprint_source(source_code, lines, ext="py"):
    module = Module(source_code=source_code, ext=ext)
    return create_fingerprint(module, lines)


def create_fingerprint(module, covered_lines):
    blocks = module.blocks
    method_reprs = []
    line_index = 0
    sorted_lines = sorted(covered_lines)

    for current_block in sorted(blocks, key=lambda x: x.start):
        try:
            while sorted_lines[line_index] < current_block.start:
                line_index += 1
            if sorted_lines[line_index] <= current_block.end:
                method_reprs.append(current_block.code)
        except IndexError:
            break

    return methods_to_checksums(method_reprs)
