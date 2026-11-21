"""Per-test dependency collector built on coverage.py dynamic contexts.

Works on every supported Python. Runs coverage.py with the C tracer and one
dynamic context per test (cov.switch_context), then reads
CoverageData.contexts_by_lineno() every TEST_BATCH_SIZE tests.
"""

import os
import random
import sysconfig
import textwrap

try:
    from pytest_cov.plugin import CovPlugin
except ImportError:
    pass
import pytest
from coverage import Coverage, CoverageData
from coverage.exceptions import CoverageException

from testmon.testmon_core import (
    TEST_BATCH_SIZE,
    TestmonException,
    cached_relpath,
    home_file,
    should_include,
)


# coverage 7.10+ defaults to the sys.monitoring core on CPython 3.14+. That core
# doesn't support dynamic contexts: sys.monitoring disables a line event once the
# line has been recorded, so a line executed by several tests of one batch is
# attributed to the first test only and the other tests lose the dependency.
# testmon relies on contexts_by_lineno, so it needs the C tracer.
COVERAGE_CORE = "ctrace"


def force_context_capable_core(cov: Coverage):
    try:
        cov.set_option("run:core", COVERAGE_CORE)
    except CoverageException:
        # coverage < 7.10 has no core option and never defaults to sys.monitoring.
        pass


class CtraceCollector:
    coverage_stack: [Coverage] = []

    def __init__(
        self, rootdir, testmon_labels=None, cov_plugin=None
    ):  # TODO remove cov_plugin
        try:
            from testmon.testmon_core import (  # pylint: disable=import-outside-toplevel
                Testmon as UberTestmon,
            )

            CtraceCollector.coverage_stack: [Coverage] = UberTestmon.coverage_stack
        except ImportError:
            pass
        if testmon_labels is None:
            testmon_labels = {"singleprocess"}
        self.rootdir = rootdir
        self.testmon_labels = testmon_labels
        self.cov: Coverage = None
        self.sub_cov_file = None
        self.cov_plugin: CovPlugin = cov_plugin
        self._test_name = None
        self._next_test_name = None
        self.batched_test_names = set()
        self.check_stack = []
        self.is_started = False
        self._interrupted_at = None

    def start_cov(self):
        if not self.cov._started:
            CtraceCollector.coverage_stack.append(self.cov)
            self.cov.start()

    def stop_cov(self):
        if self.cov is None:
            return
        assert self.cov in CtraceCollector.coverage_stack
        if CtraceCollector.coverage_stack:
            while CtraceCollector.coverage_stack[-1] != self.cov:
                cov = CtraceCollector.coverage_stack.pop()
                cov.stop()
        if self.cov._started:
            self.cov.stop()
            CtraceCollector.coverage_stack.pop()
        if CtraceCollector.coverage_stack:
            CtraceCollector.coverage_stack[-1].start()

    def setup_coverage(self, subprocess=False):
        params = {
            "include": [os.path.join(self.rootdir, "*")],
            "omit": {
                os.path.join(value, "*")
                for key, value in sysconfig.get_paths().items()
                if key.endswith("lib")
            },
        }
        if self.cov_plugin and self.cov_plugin._started:
            cov = self.cov_plugin.cov_controller.cov
            CtraceCollector.coverage_stack.append(cov)
            if cov.config.source:
                params["include"] = list(
                    set(
                        [os.path.join(self.rootdir, "*")]
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
            # params["omit"] = cov.config.run_omit
            if cov.config.branch:
                raise TestmonException(
                    "testmon doesn't support simultaneous run with pytest-cov when "
                    "branch coverage is on. Please disable branch coverage."
                )
        if subprocess:
            self.setup_subprocess(params["include"])
        self.cov = Coverage(data_file=self.sub_cov_file, config_file=False, **params)
        self.cov._warn_no_data = False
        force_context_capable_core(self.cov)
        if CtraceCollector.coverage_stack:
            CtraceCollector.coverage_stack[-1].stop()

        self.start_cov()

    def start_testmon(self, test_name, next_test_name=None):
        self._next_test_name = next_test_name

        self.batched_test_names.add(test_name)
        if self.cov is None:
            self.setup_coverage()

        self.start_cov()
        self._test_name = test_name
        self.cov.switch_context(test_name)
        self.check_stack = CtraceCollector.coverage_stack.copy()

    def discard_current(self):
        self._interrupted_at = self._test_name

    def get_batch_coverage_data(self):
        if self.check_stack != CtraceCollector.coverage_stack:
            pytest.exit(
                (
                    "Exiting pytest!!!! This test corrupts Testmon.coverage_stack:"
                    f" {self._test_name} {self.check_stack},"
                    f" {CtraceCollector.coverage_stack}"
                ),
                returncode=3,
            )

        nodes_files_lines = {}

        if self.cov and (
            len(self.batched_test_names) >= TEST_BATCH_SIZE
            or self._next_test_name is None
            or self._interrupted_at
        ):
            self.cov.stop()
            nodes_files_lines, lines_data = self.get_nodes_files_lines(
                dont_include=self._interrupted_at
            )

            if (
                len(CtraceCollector.coverage_stack) > 1
                and CtraceCollector.coverage_stack[-1] == self.cov
            ):
                filtered_lines_data = {
                    file: data
                    for file, data in lines_data.items()
                    if should_include(CtraceCollector.coverage_stack[-2], file)
                }
                CtraceCollector.coverage_stack[-2].get_data().add_lines(
                    filtered_lines_data
                )

            self.cov.erase()
            self.cov.start()
            self.batched_test_names = set()
        return nodes_files_lines

    def get_nodes_files_lines(self, dont_include):
        cov_data: CoverageData = self.cov.get_data()
        files = cov_data.measured_files()
        nodes_files_lines = {}
        files_lines = {}
        for file in files:
            relfilename = cached_relpath(file, self.rootdir)

            contexts_by_lineno = cov_data.contexts_by_lineno(file)

            for lineno, contexts in contexts_by_lineno.items():
                for context in contexts:
                    nodes_files_lines.setdefault(context, {}).setdefault(
                        relfilename, set()
                    ).add(lineno)
                    files_lines.setdefault(file, set()).add(lineno)
        nodes_files_lines.pop(dont_include, None)
        self.batched_test_names.discard(dont_include)
        nodes_files_lines.pop("", None)
        for test_name in self.batched_test_names:
            if home_file(test_name) not in nodes_files_lines.setdefault(test_name, {}):
                nodes_files_lines[test_name].setdefault(home_file(test_name), {1})
        return nodes_files_lines, files_lines

    def close(self):
        if self.cov is None:
            return
        assert self.cov in CtraceCollector.coverage_stack
        if CtraceCollector.coverage_stack:
            while CtraceCollector.coverage_stack[-1] != self.cov:
                cov = CtraceCollector.coverage_stack.pop()
                cov.stop()
        if self.cov._started:
            self.cov.stop()
            CtraceCollector.coverage_stack.pop()
        if self.sub_cov_file:
            os.remove(self.sub_cov_file + "_rc")
            os.environ.pop("COVERAGE_CORE", None)
        os.environ.pop("COVERAGE_PROCESS_START", None)
        self.cov = None
        if CtraceCollector.coverage_stack:
            CtraceCollector.coverage_stack[-1].start()

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
