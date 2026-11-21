"""Per-test dependency collector built directly on sys.monitoring (PEP 669).

Alternative to CtraceCollector for testmon on Python 3.12+: records, for each
test, the lines executed inside the project (stdlib and site-packages are
omitted) without going through coverage.
"""

import os
import sys
import sysconfig
from functools import lru_cache

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
        # Code objects with local LINE events enabled, keyed by id(): code
        # objects compare *equal* when only co_filename differs (e.g. the same
        # test function in two modules), so a set() would silently skip one.
        # Values keep them alive, so ids are never reused.
        self._armed = {}
        self._current_lines = {}  # {abs filename: set(lineno)} of current test
        self._test_name = None
        self._next_test_name = None
        self._batch = {}  # {test name: {abs filename: set(lineno)}}
        self.batched_test_names = set()
        self._interrupted_at = None

    @lru_cache(maxsize=None)  # noqa: B019 (one collector per session)
    def _in_scope(self, filename):
        if not filename or filename[0] == "<":  # <string>, <frozen ...>
            return False
        path = os.path.normcase(os.path.realpath(filename))
        return path.startswith(self._root_prefix) and not path.startswith(
            self._omit_prefixes
        )

    @lru_cache(maxsize=None)  # noqa: B019 (one collector per session)
    def _relpath(self, filename):
        # What coverage reports for CtraceCollector: the file's realpath
        # relative to rootdir's. co_filename itself may go through a symlink
        # (macOS /var -> /private/var, a symlinked sys.path entry). On Windows
        # relpath compares case-insensitively and realpath restores the on-disk
        # case, as coverage does.
        return os.path.relpath(os.path.realpath(filename), self._real_root).replace(
            os.sep, "/"
        )

    def _on_py_start(self, code, instruction_offset):  # pylint: disable=unused-argument
        if id(code) not in self._armed and self._in_scope(code.co_filename):
            sysmon.set_local_events(self._tool_id, code, EV.LINE)
            self._armed[id(code)] = code
        return DISABLE

    def _on_line(self, code, line_number):
        lines = self._current_lines.get(code.co_filename)
        if lines is None:
            lines = self._current_lines.setdefault(code.co_filename, set())
        lines.add(line_number)
        return DISABLE

    def _start_monitoring(self):
        self._tool_id = _acquire_tool_id("testmon")
        sysmon.register_callback(self._tool_id, EV.PY_START, self._on_py_start)
        sysmon.register_callback(self._tool_id, EV.LINE, self._on_line)
        sysmon.restart_events()
        sysmon.set_events(self._tool_id, EV.PY_START)

    def _flush_current(self):
        current, self._current_lines = self._current_lines, {}
        if self._test_name is not None and current:
            per_test = self._batch.setdefault(self._test_name, {})
            for filename, lines in list(current.items()):
                per_test.setdefault(filename, set()).update(lines)

    def start_testmon(self, test_name, next_test_name=None):
        if self._tool_id is None:
            self._start_monitoring()
        self._flush_current()
        sysmon.restart_events()
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
        self._flush_current()
        # Lines executed after this point (until the next switch) stay with the
        # current test and are reported in the next batch, like with contexts.
        sysmon.restart_events()

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
        sysmon.register_callback(tool_id, EV.PY_START, None)
        sysmon.register_callback(tool_id, EV.LINE, None)
        if hasattr(sysmon, "clear_tool_id"):
            sysmon.clear_tool_id(tool_id)
        sysmon.free_tool_id(tool_id)
