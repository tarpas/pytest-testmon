import importlib.util
from typing import Callable

import pytest

from testmon.testmon_core import TestmonData

# The plain state of the plugin's TestmonData at the end of a run; see GetTestmonDataPlugin.
SNAPSHOT_ATTRIBUTES = (
    "rootdir",
    "environment",
    "exec_id",
    "system_packages_change",
    "files_of_interest",
    "all_files",
    "unstable_test_names",
    "unstable_files",
    "stable_test_names",
    "stable_files",
    "failing_tests",
)


class GetTestmonDataPlugin:
    """Snapshots the plugin's TestmonData before the plugin closes its storage.

    The plugin closes its connection in pytest_unconfigure (TestmonData.close_connection), so
    the live object is useless afterwards; `LocalRemote.td` rebuilds one from this snapshot on
    a fresh connection.
    """

    snapshot: dict = None

    @pytest.hookimpl(tryfirst=True)
    def pytest_unconfigure(self, config):
        testmon_data: TestmonData = getattr(config, "testmon_data", None)
        if testmon_data is not None:  # the run used testmon
            self.snapshot = {
                name: getattr(testmon_data, name) for name in SNAPSHOT_ATTRIBUTES
            }


class LocalRemote:
    """A way to run a generated test project; see FLAVORS.

    `td` is a TestmonData with the state of the last run, open on its own connection to the
    run's storage (`open_db` makes the connection for flavours that don't use .testmondata).
    It is opened on first access and closed by the next run or `close()`.
    """

    def __init__(
        self,
        testdir: "pytest.Testdir" = None,
        runpytest_inprocess: Callable = None,
        makepyfile: Callable = None,
        name: str = None,
        mkpydir: Callable = None,
        tmpdir=None,
        open_db: Callable = None,
    ):
        self.testdir = testdir
        self.runpytest_inprocess = runpytest_inprocess
        self.makepyfile = makepyfile
        self.name = name
        self.mkpydir = mkpydir
        self.tmpdir = tmpdir
        self.open_db = open_db
        self.snapshot: dict = None
        self._td: TestmonData = None

    @property
    def td(self) -> TestmonData:
        if self._td is None:
            assert self.snapshot, "no testmon run yet"
            database = self.open_db() if self.open_db else None
            self._td = TestmonData(self.snapshot["rootdir"], database=database)
            self._td.__dict__.update(self.snapshot)
        return self._td

    def record_run(self, snapshot: dict):
        self.close()
        self.snapshot = snapshot

    def close(self):
        if self._td is not None:
            self._td.close_connection()
            self._td = None


def runpytest_gen(lr, testdir, plugin_factories=(), extra_args=()):
    """An in-process pytest runner for `lr`: records the resulting TestmonData state in `lr`."""

    def runpytest_inprocess(*args, **kwargs):
        if kwargs:
            raise NotImplementedError()
        gtd = GetTestmonDataPlugin()
        plugins = [factory() for factory in plugin_factories] + [gtd]
        # runpytest_inprocess finds/imports "tests" module, which triggers AssertRewriteWarning. Suppress it.
        args = (
            args
            + ("-W", "ignore::pytest.PytestAssertRewriteWarning")
            + tuple(extra_args)
        )
        result = testdir.runpytest_inprocess(*args, plugins=plugins)
        lr.record_run(gtd.snapshot)
        return result

    return runpytest_inprocess


def make_flavor(testdir, name, plugin_factories=(), extra_args=(), open_db=None):
    lr = LocalRemote(
        testdir,
        None,
        testdir.makepyfile,
        name,
        testdir.mkpydir,
        testdir.tmpdir,
        open_db,
    )
    lr.runpytest_inprocess = runpytest_gen(lr, testdir, plugin_factories, extra_args)
    # the plain local run, for tests that need to compare with it
    lr.runpytest_local_inprocess = runpytest_gen(lr, testdir)
    return lr


# Ways to run the tests that use the `local_remote` fixture: name -> factory(testdir) -> LocalRemote.
# "local" always, "xdist" (the same under `-n 2`) when pytest-xdist is installed. Plugins can add
# more through the `pytest_testmon_flavors` hook declared in tests/conftest.py.
FLAVORS = {"local": lambda testdir: make_flavor(testdir, "local")}
if importlib.util.find_spec("xdist"):
    FLAVORS["xdist"] = lambda testdir: make_flavor(
        testdir, "xdist", extra_args=("-n", "2")
    )
