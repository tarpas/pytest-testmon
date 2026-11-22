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


def methods_to_checksums(blocks) -> [int]:
    checksums = []
    for block in blocks:
        checksums.append(to_signed(zlib.crc32(block.encode("UTF-8"))))

    return checksums


def checksums_to_blob(checksums: [int]) -> sqlite3.Binary:
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
        # assert start <= end
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
def bytes_to_string_and_fsha(byte_stream: bytes) -> Union[str, bytes]:
    # The fsha must equal git's blob sha of the CRLF-normalized bytes, so that it
    # matches the index entry returned by get_files_shas() and no read is needed
    # for files git reports as unmodified. The header length is the byte length,
    # and hashing happens before the \f replacement (git does not touch \f).
    byte_stream = byte_stream.replace(b"\r\n", b"\n")
    hsh = hashlib.sha1()
    hsh.update(b"blob %u\0" % len(byte_stream))
    hsh.update(byte_stream)
    # Replace \f because of http://bugs.python.org/issue19035
    byte_stream = byte_stream.replace(b"\f", b" ")
    byte_string = byte_stream.decode(source_encoding(byte_stream), "replace")
    if byte_string and byte_string[-1] != "\n":
        byte_string += "\n"
    return byte_string, hsh.hexdigest()


_BLOCK_CLASSES = frozenset(("AsyncFunctionDef", "FunctionDef", "Module"))


class Module:
    def __init__(  # pylint: disable=too-many-arguments
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
        self._checksums = None
        self._sorted_blocks = None
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
        """Frame of this method is taken from ast.dump
        Objective is to return a representation of python source code where
        all of the bodies of functions are replaced with 'transformed_into_block'
        string. The rest of the syntax tree is represented in the same way as
        in ast.dump(tree, annotate_fields=False). Of course the bodies of functions
        are not completely thrown away, they are transformed into Block() objects
        and appended to self.blocks. More can be probably understood from
        (at the time rather messy) test_process_code.py examples.
        """

        if isinstance(node, ast.AST):
            class_name = type(node).__name__
            blocky = class_name in _BLOCK_CLASSES
            node_name = getattr(node, "name", "unknown")
            fields = []
            for field_name in node._fields:
                try:
                    field_value = getattr(node, field_name)
                except AttributeError:  # what ast.iter_fields skips
                    continue
                fields.append(
                    self.dump_and_block(
                        field_value,
                        end,
                        name=node_name,
                        into_block=blocky and field_name == "body",
                    )
                )
            return f"{class_name}({', '.join(fields)})"
        if isinstance(node, list):
            representations = []
            last = len(node) - 1
            for i, item in enumerate(node):
                if i < last:
                    next_lineno = getattr(node[i + 1], "lineno", None)
                    item_end = None if next_lineno is None else next_lineno - 1
                else:
                    item_end = end
                representations.append(self.dump_and_block(item, item_end))
            if into_block and node:
                # Use last child's end_lineno only if end is not available (None)
                if end is None:
                    last_child = node[-1]
                    block_end = getattr(last_child, "end_lineno", None)
                else:
                    block_end = end
                self._blocks.append(
                    Block(
                        node[0].lineno,
                        block_end,
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
        if self._checksums is None:
            self._checksums = methods_to_checksums(
                [block.checksum for block in self.blocks]
            )
        return self._checksums

    @property
    def sorted_blocks(self):
        """[(start, end, checksum)] of the blocks, by start line."""
        if self._sorted_blocks is None:
            self._sorted_blocks = sorted(
                (
                    (block.start, block.end, checksum)
                    for block, checksum in zip(self.blocks, self.checksums)
                ),
                key=lambda block: block[0],
            )
        return self._sorted_blocks

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
                    # We can continue without blocks because no tests depending on this file will ever get executed,
                    # so no node depending on this checksum and mtime will ever be written to db.
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
        return self.checksums


def read_source_sha(filename: str):
    source_bytes: Optional[bytes]

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
        # Run inside `directory` so the printed paths are relative to it (they
        # are the keys testmon looks up); a pathspec argument would print paths
        # relative to the current working directory instead.
        result = run(
            ["git", "ls-files", "--stage", "-m"],
            cwd=directory or None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except (FileNotFoundError, NotADirectoryError, CalledProcessError):
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


def get_source_sha(directory: "str", filename: "str"):
    try:
        sha = get_files_shas(directory)[filename]
        return (None, sha)
    except KeyError:
        pass
    return read_source_sha(Path(directory) / filename)


def match_fingerprint_source(source_code, fingerprint, ext="py"):
    module = Module(source_code=source_code, ext=ext)
    return match_fingerprint(module, fingerprint)


def match_fingerprint(module: Module, fingerprint):
    if set(fingerprint) - set(module.checksums):
        return False
    return True


def create_fingerprint_source(source_code, lines, ext="py"):
    module = Module(source_code=source_code, ext=ext)
    return create_fingerprint(module, lines)


def create_fingerprint(module, covered_lines) -> [int]:
    fingerprint = []
    line_index = 0
    sorted_lines = sorted(covered_lines)

    for start, end, checksum in module.sorted_blocks:
        try:
            while sorted_lines[line_index] < start:
                line_index += 1
            if sorted_lines[line_index] <= end:
                fingerprint.append(checksum)
        except IndexError:
            break

    return fingerprint
