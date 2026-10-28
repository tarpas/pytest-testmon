import importlib.util
from typing import Callable

import pytest

from testmon.collectors import COVERAGE_BACKEND, SYSMON, SYSMON_BACKEND
from testmon.testmon_core import TestmonData

# Every collection backend this interpreter can run; tests of the collector take all.
COLLECTOR_BACKENDS = [COVERAGE_BACKEND] + ([SYSMON_BACKEND] if SYSMON else [])


class GetTestmonDataPlugin:
    @pytest.hookimpl(tryfirst=True)
    def pytest_unconfigure(self, config):
        self.testmon_data: TestmonData = config.testmon_data


class LocalRemote:
    """A way to run a generated test project; see FLAVORS."""

    def __init__(
        self,
        testdir: "pytest.Testdir" = None,
        runpytest_inprocess: Callable = None,
        makepyfile: Callable = None,
        name: str = None,
        mkpydir: Callable = None,
        td: TestmonData = None,
        tmpdir=None,
    ):
        self.testdir = testdir
        self.runpytest_inprocess = runpytest_inprocess
        self.makepyfile = makepyfile
        self.name = name
        self.mkpydir = mkpydir
        self.td = td
        self.tmpdir = tmpdir


def runpytest_gen(lr, testdir, plugin_factories=(), extra_args=()):
    """An in-process pytest runner for `lr`: records the resulting TestmonData in `lr.td`."""

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
        lr.td = gtd.testmon_data
        return result

    return runpytest_inprocess


def make_flavor(testdir, name, plugin_factories=(), extra_args=()):
    lr = LocalRemote(
        testdir, None, testdir.makepyfile, name, testdir.mkpydir, None, testdir.tmpdir
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
