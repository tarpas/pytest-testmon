import os
from pathlib import Path

import pytest
from coverage import Coverage, CoverageData
from testmon.testmon_core import should_include
from inspect import currentframe, getframeinfo

pytest_plugins = ("pytester",)


def one():
    return getframeinfo(currentframe()).lineno


def two():
    a = 0
    return a + getframeinfo(currentframe()).lineno


class Plugin:
    def pytest_configure(self, config):
        cov_plugin = config.pluginmanager.get_plugin("_cov")
        self.cov_plugin = cov_plugin
        self.cov_started = bool(cov_plugin and cov_plugin._started)


class TestPytestCovAssumptions:
    def test_inactive(self, testdir):
        plugin = Plugin()
        testdir.runpytest_inprocess("", plugins=[plugin])
        assert plugin.cov_started is False

    @pytest.mark.filterwarnings("ignore:")
    @pytest.mark.skipif(
        "cov" not in os.environ.get("TOX_ENV_NAME", "cov"),
        reason="requires pytest-cov in TOX",
    )
    def test_active(self, testdir):
        plugin = Plugin()

        testdir.runpytest_inprocess("--cov=.", plugins=[plugin])
        assert plugin.cov_started is True

    def test_specify_include(self, testdir):
        testdir.makepyfile(
            lib="""
        Ahoj
        bka
        # #
        """
        )

        cov = Coverage(data_file=None, config_file=False, include=["."])
        cov._warn_no_data = False
        cov.start()
        cov.stop()

        assert set() == cov.get_data().measured_files()

    # specifying source=".",
    # searches for all python files in that directory and adds them
    # to measured_files(), cov.get_data() calls cov._post_save_work()
    # which searches all py files in the source dir
    def test_specify_source(self, testdir):
        testdir.makepyfile(lib="")

        cov = Coverage(data_file=None, config_file=False, source=["."])
        cov._warn_no_data = False
        cov.start()
        cov.stop()
        for mf in cov.get_data().measured_files():
            assert mf.endswith("lib.py")

    def test_specify_sub_source(self, testdir):
        tests_subdir_path = testdir.mkpydir("tests")
        testfile = tests_subdir_path / "lib.py"
        testfile.write_text("", encoding="utf-8")

        cov = Coverage(data_file=None, config_file=False, source=["."])
        cov._warn_no_data = False
        cov.start()
        cov.stop()
        assert any(
            [
                mf.endswith(os.path.normpath("tests/lib.py"))
                for mf in cov.get_data().measured_files()
            ]
        )


"""Coverage.start(), stop(), get_data() have high or sometimes prohibitive computational cost. The cost is not inherent
in the operations so they might be fixed (one way of proceding is to use internal methods or submit PR to coverage). 
The other way, which is already avialable is to use contexts, gather them in bulk and then do batch processing for many
(hundreds) tests at once. Batch processing and batch writing is probably also the most effective way of creating
and writing the testmon data."""


class TestCovAssumptions:
    @pytest.fixture
    def uber_cov_plugin(self, request):
        return request.config.pluginmanager.get_plugin("_cov")

    def test_2_coverages1(self, testdir):
        cov1 = Coverage(data_file=None)
        cov1._warn_no_data = False
        cov1.start()
        cov2 = Coverage(data_file=None)
        cov2._warn_no_data = False
        cov1.stop()
        cov2.start()
        cov2.switch_context("1")
        line1 = one()
        cov2.switch_context("2")
        line2 = two()
        cov2.stop()
        data2: CoverageData = cov2.get_data()
        data2.set_query_contexts(["1", "2"])

        for filename in data2.measured_files():
            aggregate_lines = sorted(data2.lines(filename))
        assert aggregate_lines == [line1, line2 - 1, line2]
        cov2.erase()
        data1: CoverageData = cov1.get_data()
        data1.add_lines({filename: aggregate_lines})
        cov1.start()
        cov1.stop()
        assert sorted(data1.lines(filename)) == aggregate_lines

    def test_2_stops_allowed(self, testdir):
        cov1 = Coverage(data_file=None)
        cov1._warn_no_data = False
        cov1.start()
        cov1.stop()
        cov1.stop()

    def test_get_filter_method(self):
        cov = Coverage()
        cov.start()
        cov.stop()
        assert cov._should_trace

    def test_should_include_omit(self, testdir):
        source = Path(testdir.mkdir("source"))
        cov = Coverage(source=[str(source)], omit=[str(source / "omit" / "*")])
        cov.start()
        cov.stop()

        assert not should_include(cov, Path(str(testdir)) / "a.py")

        assert not should_include(cov, source / "omit" / "c.py")

        assert should_include(cov, source)

    def test_should_include_source(self, testdir):
        include = Path(testdir.mkdir("include"))
        cov = Coverage(
            include=[str(include / "*")],
        )
        cov.start()
        cov.stop()

        assert not should_include(cov, str(testdir))

        assert not should_include(cov, Path(str(testdir)) / "a.py")

        assert should_include(cov, include / "c.py")
