"""The interface testmon's pytest plugin uses to record per-test dependencies.

Two implementations:
  * SysmonCollector (sysmon.py): sys.monitoring (PEP 669). Default on
    CPython 3.12+, much cheaper per test.
  * CtraceCollector (ctrace.py): coverage.py, C tracer, one dynamic
    context per test. Used on 3.11, or with TESTMON_CORE=ctrace.

Both measure the pytest process only; under pytest-xdist every worker runs
its own collector.
"""

import os
from typing import Protocol

from testmon.common import get_logger

# {test name: {file path relative to rootdir: {line numbers}}}
NodesFilesLines = dict[str, dict[str, set[int]]]

logger = get_logger(__name__)


class Collector(Protocol):
    rootdir: str
    testmon_labels: set[str]
    batched_test_names: set[str]

    def start_testmon(self, test_name: str, next_test_name: str | None = None) -> None:
        """A test starts: lines run from now on belong to test_name."""

    def discard_current(self) -> None:
        """The current test was interrupted: leave it out of the batch."""

    def get_batch_coverage_data(self) -> NodesFilesLines:
        """Every TEST_BATCH_SIZE tests and after the last one: the batch's
        dependencies. Otherwise an empty dict."""

    def close(self) -> None:
        """Stop measuring and release everything."""


CORES = ("sysmon", "ctrace")


def make_collector(rootdir, testmon_labels=None, cov_plugin=None) -> Collector:
    """SysmonCollector on CPython 3.12+, CtraceCollector otherwise.

    TESTMON_CORE=ctrace forces the coverage.py collector."""
    # pylint: disable=import-outside-toplevel
    core = os.environ.get("TESTMON_CORE", "")
    if core and core not in CORES:
        logger.warning(
            "TESTMON_CORE=%s is unknown (expected one of %s), using the default",
            core,
            ", ".join(CORES),
        )
        core = ""
    if core != "ctrace":
        try:
            from testmon.collector.sysmon import SysmonCollector, search_free_tool_id
        except ImportError:
            if core == "sysmon":
                logger.warning("TESTMON_CORE=sysmon needs CPython 3.12+, using ctrace")
        else:
            if search_free_tool_id() is not None:
                return SysmonCollector(rootdir, testmon_labels, cov_plugin)
            logger.warning("no free sys.monitoring tool id, using ctrace")
    from testmon.collector.ctrace import CtraceCollector

    return CtraceCollector(rootdir, testmon_labels, cov_plugin)
