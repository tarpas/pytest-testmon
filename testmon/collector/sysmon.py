"""Per-test dependency collector built directly on sys.monitoring (PEP 669).

Alternative to CtraceCollector for testmon on Python 3.12+: records, for each
test, the lines executed inside the project (stdlib and site-packages are
omitted) without going through coverage.
"""

import os
import sys
import sysconfig

from testmon.collector import NodesFilesLines
from testmon.testmon_core import TEST_BATCH_SIZE, home_file

if not hasattr(sys, "monitoring"):  # CPython < 3.12
    raise ImportError("sys.monitoring requires CPython 3.12+")

sysmon = sys.monitoring
EV = sysmon.events
DISABLE = sysmon.DISABLE

# https://peps.python.org/pep-0669/#tool-identifiers
# CPython suggests in PEP 669: 0 (debugger), 1 (coverage), 2 (profiler), 5 (optimizer).
# These are conventions, not enforced. We aren't a debugger, profiler or optimizer, and
# we avoid 1 so coverage keeps working, so we prefer 3 and 4.
_PREFERRED_TOOL_IDS = (3, 4, 5, 2)


def search_free_tool_id():
    """The first free tool id testmon may use, or None."""
    for tool_id in _PREFERRED_TOOL_IDS:
        if sysmon.get_tool(tool_id) is None:
            return tool_id
    return None


def _acquire_tool_id(name):
    tool_id = search_free_tool_id()
    if tool_id is None:
        raise RuntimeError("testmon: no free sys.monitoring tool id")
    sysmon.use_tool_id(tool_id, name)
    return tool_id


def _single_line(code):
    """The line of a code object whose instructions are all on one line
    (lambda x: x + 1, def f(x): return x), else None."""
    lines = {line for _, _, line in code.co_lines() if line is not None}
    return lines.pop() if len(lines) == 1 else None


def _dir_prefix(path):
    """Normalized "path/" for prefix tests: case and slashes don't matter on
    Windows (normcase), and "/root" doesn't match "/root2"."""
    return os.path.join(os.path.normcase(path), "")


class SysmonCollector:
    def __init__(self, rootdir, testmon_labels=None, cov_plugin=None):
        self.rootdir = rootdir
        self.testmon_labels = testmon_labels or {"singleprocess"}
        self.cov_plugin = cov_plugin  # pytest-cov keeps running on its own
        self._real_root = os.path.realpath(rootdir)
        self._root_prefix = _dir_prefix(self._real_root)

        self._omit_prefixes = tuple(
            _dir_prefix(os.path.realpath(path))
            for key, path in sysconfig.get_paths().items()
            if key.endswith("lib")
        )

        self._tool_id = None
        # Code objects armed with local events (see _arm), keyed by id(): code
        # objects compare *equal* when only co_filename differs (e.g. the same
        # test function in two modules), so a set() would silently skip one.
        # Values keep them alive, so ids are never reused.
        self._armed = {}
        # {id(code): line} for the armed single-line codes (see _arm)
        self._one_line = {}
        # {id(code): set(lineno)} of the current test; the codes are in _armed
        self._current_lines = {}
        self._test_name = None
        self._next_test_name = None
        self._batch = {}  # {test name: {abs filename: set(lineno)}}
        self.batched_test_names = set()
        self._interrupted_at = None

        self._in_scope_cache = {}
        self._relpath_cache = {}

    def _in_scope(self, filename):
        if filename not in self._in_scope_cache:
            if not filename or filename[0] == "<":  # <string>, <frozen ...>
                in_scope = False
            else:
                path = os.path.normcase(os.path.realpath(filename))
                in_scope = path.startswith(self._root_prefix) and not path.startswith(
                    self._omit_prefixes
                )
            self._in_scope_cache[filename] = in_scope
        return self._in_scope_cache[filename]

    def _relpath(self, filename):
        # What coverage reports for CtraceCollector: the file's realpath
        # relative to rootdir's. co_filename itself may go through a symlink
        # (macOS /var -> /private/var, a symlinked sys.path entry). On Windows
        # relpath compares case-insensitively and realpath restores the on-disk
        # case, as coverage does.
        if filename not in self._relpath_cache:
            self._relpath_cache[filename] = os.path.relpath(
                os.path.realpath(filename), self._real_root
            ).replace(os.sep, "/")
        return self._relpath_cache[filename]

    def _on_py_start(self, code, _offset):
        if id(code) not in self._armed and self._in_scope(code.co_filename):
            self._armed[id(code)] = code
            line = _single_line(code)
            if line is not None:
                self._one_line[id(code)] = line
            self._arm(code)
        return DISABLE

    def _arm(self, code):
        # Resetting to 0 first is what clears the locations that returned
        # DISABLE. Single-line codes (lambda x: x + 1) get INSTRUCTION: on
        # 3.14+ they report no LINE once re-armed.
        sysmon.set_local_events(self._tool_id, code, 0)
        events = EV.INSTRUCTION if id(code) in self._one_line else EV.LINE
        sysmon.set_local_events(self._tool_id, code, events)

    def _on_line(self, code, line_number):
        self._current_lines.setdefault(id(code), set()).add(line_number)
        return DISABLE

    def _on_instruction(self, code, _offset):
        self._current_lines.setdefault(id(code), set()).add(self._one_line[id(code)])
        return DISABLE

    def _start_monitoring(self):
        self._tool_id = _acquire_tool_id("testmon")
        sysmon.register_callback(self._tool_id, EV.PY_START, self._on_py_start)
        sysmon.register_callback(self._tool_id, EV.LINE, self._on_line)
        sysmon.register_callback(self._tool_id, EV.INSTRUCTION, self._on_instruction)
        sysmon.restart_events()
        sysmon.set_events(self._tool_id, EV.PY_START)

    def _flush_current(self):
        """Move the current test's lines to the batch and re-arm only the code
        that ran: restart_events() would re-enable PY_START for every function
        seen so far, pytest's own included, at a callback each per test."""
        current, self._current_lines = self._current_lines, {}
        # An empty entry would erase the lines of a test that closed a batch.
        per_test = (
            self._batch.setdefault(self._test_name, {})
            if self._test_name is not None and current
            else None
        )
        # list(): a callback in another thread may still add to current
        for code_id, lines in list(current.items()):
            code = self._armed[code_id]
            if per_test is not None:
                per_test.setdefault(code.co_filename, set()).update(lines)
            self._arm(code)

    def start_testmon(self, test_name, next_test_name=None):
        if self._tool_id is None:
            self._start_monitoring()
        self._flush_current()
        self._test_name = test_name
        self._next_test_name = next_test_name
        self.batched_test_names.add(test_name)

    def discard_current(self):
        self._interrupted_at = self._test_name

    def get_batch_coverage_data(self) -> NodesFilesLines:
        if self._tool_id is None or not (
            len(self.batched_test_names) >= TEST_BATCH_SIZE
            or self._next_test_name is None
            or self._interrupted_at
        ):
            return {}
        # Lines executed after this point (until the next switch) stay with the
        # current test and are reported in the next batch, like with contexts.
        self._flush_current()

        nodes_files_lines = {}
        for test_name, files in self._batch.items():
            if test_name == self._interrupted_at:
                continue
            per_test = nodes_files_lines[test_name] = {}
            for filename, lines in files.items():
                per_test.setdefault(self._relpath(filename), set()).update(lines)
        self.batched_test_names.discard(self._interrupted_at)
        for test_name in self.batched_test_names:
            per_test = nodes_files_lines.setdefault(test_name, {})
            per_test.setdefault(home_file(test_name), {1})

        self._batch = {}
        self.batched_test_names = set()
        self._interrupted_at = None
        return nodes_files_lines

    def close(self):
        if self._tool_id is None:
            return
        tool_id, self._tool_id = self._tool_id, None
        sysmon.set_events(tool_id, 0)
        for code in self._armed.values():
            sysmon.set_local_events(tool_id, code, 0)
        self._armed.clear()
        self._one_line.clear()
        sysmon.register_callback(tool_id, EV.PY_START, None)
        sysmon.register_callback(tool_id, EV.LINE, None)
        sysmon.register_callback(tool_id, EV.INSTRUCTION, None)
        if hasattr(sysmon, "clear_tool_id"):
            sysmon.clear_tool_id(tool_id)
        sysmon.free_tool_id(tool_id)
