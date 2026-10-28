"""Collection backends: which project code did each test execute?

Both backends produce the same thing, ``{test_name: {absolute_filename: {line, ...}}}``,
where every line falls inside the body of a function (or module) that the test entered.
``process_code.create_fingerprint`` maps those lines to method checksums, so the
database and the server never see a difference between the backends.

``SysmonBackend`` (CPython 3.12+) listens to ``sys.monitoring`` ``PY_START`` events with
its own tool id. The callback records one representative body line per entered code
object and returns ``DISABLE``, so it runs once per code object per test instead of once
per call; ``restart_events()`` at every test switch re-arms the events. Measured overhead
is within a few percent of untraced execution (see testmon-dev's
``docs/strategy/04-sys-monitoring-collector.md``).

``CoverageBackend`` drives coverage.py's C tracer with dynamic contexts. It is the only
option below 3.12 and for subprocess tracking, and it carries the ``coverage_stack``
protocol that lets a nested collector (dogfooding, pytest-cov) take over the single
``sys.settrace`` slot and hand its lines back.
"""

import os
import random
import sys
import sysconfig
import textwrap
from functools import lru_cache

from coverage import Coverage, CoverageData
from coverage.exceptions import CoverageException

SYSMON = getattr(sys, "monitoring", None)
SYSMON_BACKEND = "sysmon"
COVERAGE_BACKEND = "coverage"


def default_backend_name():
    forced = os.environ.get("TESTMON_COLLECTOR")
    if forced in (SYSMON_BACKEND, COVERAGE_BACKEND):
        return forced
    return SYSMON_BACKEND if SYSMON is not None else COVERAGE_BACKEND


def _omit_prefixes():
    """Library directories of the running interpreter: never project code, even when the
    virtualenv lives inside the project."""
    return tuple(
        os.path.join(value, "")
        for key, value in sysconfig.get_paths().items()
        if key.endswith("lib")
    )


# ---------------------------------------------------------------------- sys.monitoring


def body_line(code):
    """A line that lies inside the body of ``code``.

    ``co_firstlineno`` is the ``def`` (or first decorator) line, which is outside the
    block testmon builds for the body. The line table lists the body's lines; take the
    smallest one after the header. One-liners (``def f(): return 1``, lambdas) fall back
    to the header line, which for them is also the body line. Module code starts at line
    1 with a synthetic line 0 for ``RESUME``, so take the first real line.
    """
    first = code.co_firstlineno
    if code.co_name == "<module>":
        lines = [line for _, _, line in code.co_lines() if line]
        return min(lines) if lines else first
    best = None
    for _, _, line in code.co_lines():
        if line and line > first and (best is None or line < best):
            best = line
    return first if best is None else best


class _SysmonEngine:
    """The one ``sys.monitoring`` tool of this process, shared by all active backends.

    Nested collectors (a test that starts its own ``TestmonCollector``) just add
    themselves here; every active backend receives every event.
    """

    # 0 debugger, 1 coverage.py, 2 profiler, 5 optimizer: start with the unassigned ids
    # and only borrow a named one when it is free.
    TOOL_IDS = (3, 4, 2, 5, 1)

    def __init__(self):
        self.tool_id = None
        self.backends = []

    def add(self, backend):
        if backend in self.backends:
            return
        if not self.backends:
            self._acquire()
        self.backends.append(backend)
        SYSMON.restart_events()

    def remove(self, backend):
        if backend not in self.backends:
            return
        self.backends.remove(backend)
        if not self.backends:
            self._release()

    def _acquire(self):
        for tool_id in self.TOOL_IDS:
            if SYSMON.get_tool(tool_id) is None:
                SYSMON.use_tool_id(tool_id, "testmon")
                self.tool_id = tool_id
                break
        else:
            raise RuntimeError("testmon: all sys.monitoring tool ids are taken")
        SYSMON.register_callback(
            self.tool_id, SYSMON.events.PY_START, self._on_py_start
        )
        SYSMON.set_events(self.tool_id, SYSMON.events.PY_START)

    def _release(self):
        SYSMON.set_events(self.tool_id, 0)
        SYSMON.register_callback(self.tool_id, SYSMON.events.PY_START, None)
        SYSMON.free_tool_id(self.tool_id)
        self.tool_id = None

    def _on_py_start(self, code, _instruction_offset):
        for backend in self.backends:
            backend.record(code)
        # Fire again only after the next restart_events(), i.e. for the next test.
        return SYSMON.DISABLE


_ENGINE = _SysmonEngine() if SYSMON is not None else None


class SysmonBackend:
    name = SYSMON_BACKEND

    def __init__(self, rootdir):
        self.include = os.path.join(os.path.abspath(rootdir), "")
        self.omit = _omit_prefixes()
        self._code_info = {}  # id(code) -> (filename, body line) or None if excluded
        self._keep = []  # keeps code objects alive so ids stay unique
        self._data = {}  # test_name -> {filename: {line, ...}}
        self._current = {}  # bucket for events before the first switch()
        self.started = False

    # -- lifecycle

    def start(self):
        if not self.started:
            self.started = True
            _ENGINE.add(self)

    def switch(self, test_name):
        self._current = self._data.setdefault(test_name, {})
        SYSMON.restart_events()

    def take(self):
        data, self._data = self._data, {}
        self._current = {}
        return data

    def stop(self):
        if self.started:
            self.started = False
            _ENGINE.remove(self)

    close = stop

    def snapshot(self):
        return tuple(id(backend) for backend in _ENGINE.backends)

    def is_consistent(self, snapshot):
        return self.snapshot() == snapshot

    # -- event handling (hot path)

    def record(self, code):
        info = self._code_info.get(id(code), False)
        if info is False:
            info = self._classify(code)
        if info is not None:
            self._current.setdefault(info[0], set()).add(info[1])

    def _classify(self, code):
        filename = code.co_filename
        info = None
        if filename and filename[0] != "<" and code.co_name != "__annotate__":
            if not os.path.isabs(filename):
                filename = os.path.abspath(filename)
            if filename.startswith(self.include) and not filename.startswith(self.omit):
                info = (filename, body_line(code))
        self._code_info[id(code)] = info
        self._keep.append(code)
        return info


# ---------------------------------------------------------------------- coverage.py


# coverage 7.10+ defaults to the sys.monitoring core on CPython 3.14+. That core
# doesn't support dynamic contexts: sys.monitoring disables a line event once the
# line has been recorded, so a line executed by several tests of one batch is
# attributed to the first test only and the other tests lose the dependency.
# This backend relies on contexts_by_lineno, so it needs the C tracer.
COVERAGE_CORE = "ctrace"


def force_context_capable_core(cov: Coverage):
    try:
        cov.set_option("run:core", COVERAGE_CORE)
    except CoverageException:
        # coverage < 7.10 has no core option and never defaults to sys.monitoring.
        pass


@lru_cache(maxsize=1000)
def should_include(cov, filename):
    return cov._should_trace(str(filename), None).trace


class CoverageBackend:
    name = COVERAGE_BACKEND

    # Every Coverage object that has been started in this process, innermost last.
    # Only one sys.settrace tracer can run, so a nested collector stops the outer one,
    # collects, hands the outer one the lines it is interested in, and restarts it.
    coverage_stack: [Coverage] = []

    def __init__(self, rootdir, cov_plugin=None, subprocess=False):
        self.rootdir = rootdir
        self.cov_plugin = cov_plugin
        self.sub_cov_file = None
        params = {
            "include": [os.path.join(rootdir, "*")],
            "omit": {prefix + "*" for prefix in _omit_prefixes()},
        }
        if cov_plugin and cov_plugin._started:
            cov = cov_plugin.cov_controller.cov
            self.coverage_stack.append(cov)
            if cov.config.source:
                params["include"] = list(
                    set(
                        [os.path.join(rootdir, "*")]
                        + [
                            os.path.join(os.path.abspath(source), "*")
                            for source in cov.config.source
                        ]
                    )
                )
            elif cov.config.run_include:
                params["include"] = list(
                    set(cov.config.run_include + params["include"])
                )
            if cov.config.branch:
                from testmon.testmon_core import (  # pylint: disable=import-outside-toplevel,cyclic-import
                    TestmonException,
                )

                raise TestmonException(
                    "testmon doesn't support simultaneous run with pytest-cov when "
                    "branch coverage is on. Please disable branch coverage."
                )
        if subprocess:
            self.setup_subprocess(params["include"])
        self.cov = Coverage(data_file=self.sub_cov_file, config_file=False, **params)
        self.cov._warn_no_data = False
        force_context_capable_core(self.cov)

    # -- lifecycle

    def start(self):
        if self.coverage_stack and self.coverage_stack[-1] is not self.cov:
            self.coverage_stack[-1].stop()
        if not self.cov._started:
            self.coverage_stack.append(self.cov)
            self.cov.start()

    def switch(self, test_name):
        self.cov.switch_context(test_name)

    def take(self):
        self.cov.stop()
        cov_data: CoverageData = self.cov.get_data()
        data = {}
        files_lines = {}
        for file in cov_data.measured_files():
            for lineno, contexts in cov_data.contexts_by_lineno(file).items():
                for context in contexts:
                    data.setdefault(context, {}).setdefault(file, set()).add(lineno)
                files_lines.setdefault(file, set()).add(lineno)

        if len(self.coverage_stack) > 1 and self.coverage_stack[-1] == self.cov:
            parent = self.coverage_stack[-2]
            parent.get_data().add_lines(
                {
                    file: lines
                    for file, lines in files_lines.items()
                    if should_include(parent, file)
                }
            )

        self.cov.erase()
        self.cov.start()
        return data

    def stop(self):
        assert self.cov in self.coverage_stack
        while self.coverage_stack[-1] != self.cov:
            self.coverage_stack.pop().stop()
        if self.cov._started:
            self.cov.stop()
            self.coverage_stack.pop()
        if self.coverage_stack:
            self.coverage_stack[-1].start()

    def close(self):
        if self.cov in self.coverage_stack:
            self.stop()
        if self.sub_cov_file:
            os.remove(self.sub_cov_file + "_rc")
            os.environ.pop("COVERAGE_CORE", None)
        os.environ.pop("COVERAGE_PROCESS_START", None)

    def snapshot(self):
        return self.coverage_stack.copy()

    def is_consistent(self, snapshot):
        return self.coverage_stack == snapshot

    # -- subprocesses

    def setup_subprocess(self, includes):
        # This can be redone to use functionality from pytest-cov
        if not os.path.exists(".tmontmp"):
            os.makedirs(".tmontmp")
        self.sub_cov_file = os.path.abspath(
            ".tmontmp/.testmoncoverage" + str(random.randint(0, 1000000))
        )
        with open(self.sub_cov_file + "_rc", "w", encoding="utf-8") as subprocess_rc:
            rc_content = textwrap.dedent(
                """\
                    [run]
                    data_file = {}
                    include = {}
                    parallel=True
                    """
            ).format(
                self.sub_cov_file,
                "\n ".join(includes),
            )
            subprocess_rc.write(rc_content)
        os.environ["COVERAGE_PROCESS_START"] = self.sub_cov_file + "_rc"
        os.environ["COVERAGE_CORE"] = COVERAGE_CORE


def make_backend(name, rootdir, cov_plugin=None, subprocess=False):
    if name == SYSMON_BACKEND and not subprocess:
        if SYSMON is None:
            raise RuntimeError("the sysmon collector needs CPython 3.12 or newer")
        return SysmonBackend(rootdir)
    return CoverageBackend(rootdir, cov_plugin=cov_plugin, subprocess=subprocess)
