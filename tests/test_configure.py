from types import SimpleNamespace

import pytest
from coverage import Coverage

from testmon.configure import TmConf
from testmon import configure


class TestConfigure:
    @pytest.fixture()
    def options(self):
        return {
            "testmon": False,
            "testmon_noselect": False,
            "testmon_nocollect": False,
            "testmon_forceselect": False,
            "no-testmon": False,
            "keyword": "",
            "markexpr": "",
            "lf": False,
            "file_or_dir": [],
        }

    def test_noselect_reasons_without_lf_option(self, options):
        # `lf` is deliberately missing: `-p no:cacheprovider` does not register `--lf`
        del options["lf"]
        assert configure._get_noselect_reasons(options) == []

    def test_noselect_reasons_with_lf(self, options):
        options["lf"] = True
        assert configure._get_noselect_reasons(options) == ["--lf was used"]

    def test_noselect_reasons_with_lf_disabled(self, options):
        options["lf"] = False
        assert configure._get_noselect_reasons(options) == []

    def test_easy(self, options):
        options["testmon"] = True
        assert configure._header_collect_select(options) == TmConf(
            "testmon: ",
            True,
            True,
        )

    def test_empty(self, options):
        options["testmon"] = None
        assert configure._header_collect_select(options) == TmConf(None, False, False)

    def test_dogfooding(self, options):
        options["testmon"] = True
        assert configure._header_collect_select(
            options, dogfooding=True, debugger=True
        ) == TmConf("testmon: ", True, True)

    def test_noselect(self, options):
        options["testmon_noselect"] = True
        assert configure._header_collect_select(options) == TmConf(
            "testmon: selection deactivated, ",
            True,
            False,
        )

    def test_noselect_trace(self, options):
        options["testmon_noselect"] = True
        assert configure._header_collect_select(options, debugger=True) == TmConf(
            (
                "testmon: collection automatically deactivated because "
                "it's not compatible with debugger, selection deactivated, "
            ),
            False,
            False,
        )

    def test_nocollect_minus_k(self, options):
        options["keyword"] = "test1"
        options["testmon_nocollect"] = True
        assert configure._header_collect_select(options) == TmConf(
            (
                "testmon: collection deactivated, "
                "selection automatically deactivated because -k was used, "
            ),
            False,
            False,
        )

    def test_nocollect_coverage_without_cov_plugin(self, options):
        options["testmon"] = True
        assert configure._header_collect_select(options, coverage=True) == TmConf(
            "testmon: collection automatically deactivated "
            "because coverage.py was detected and simultaneous collection is not supported, ",
            False,
            True,
        )

    def test_nocollect_coverage_with_cov_plugin(self, options):
        options["testmon"] = True
        assert configure._header_collect_select(
            options, coverage=True, cov_plugin=True
        ) == TmConf("testmon: ", True, True)

    def test_is_coverage_detects_outer_measurement(self, monkeypatch):
        monkeypatch.setattr(Coverage, "current", classmethod(lambda cls: None))
        assert not configure._is_coverage()
        monkeypatch.setattr(Coverage, "current", classmethod(lambda cls: object()))
        assert configure._is_coverage()

    @pytest.mark.parametrize("started, collect", [(False, False), (True, True)])
    def test_cov_plugin_counts_only_when_started(
        self, options, monkeypatch, started, collect
    ):
        options["testmon"] = True
        monkeypatch.setattr(configure, "_is_coverage", lambda: True)
        monkeypatch.setattr(configure, "_is_debugger", lambda: False)
        config = SimpleNamespace(option=SimpleNamespace(**options))
        cov_plugin = SimpleNamespace(_started=started)

        tm_conf = configure.header_collect_select(config, None, cov_plugin=cov_plugin)

        assert tm_conf.collect is collect
