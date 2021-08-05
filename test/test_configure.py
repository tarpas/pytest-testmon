import pytest
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
        }

    def test_easy(self, options):
        options["testmon"] = True
        assert configure._header_collect_select(options) == (
            "testmon: ",
            True,
            True,
        )

    def test_empty(self, options):
        options["testmon"] = None
        assert configure._header_collect_select(options) == (None, False, False)

    def test_dogfooding(self, options):
        options["testmon"] = True
        assert configure._header_collect_select(
            options, dogfooding=True, debugger=True
        ) == ("testmon: ", True, True)

    def test_noselect(self, options):
        options["testmon_noselect"] = True
        assert configure._header_collect_select(options) == (
            "testmon: selection deactivated, ",
            True,
            False,
        )

    def test_noselect_trace(self, options):
        options["testmon_noselect"] = True
        assert configure._header_collect_select(options, debugger=True) == (
            "testmon: collection automatically deactivated because it's not compatible with debugger, selection deactivated, ",
            False,
            False,
        )

    def test_nocollect_minus_k(self, options):
        options["keyword"] = "test1"
        options["testmon_nocollect"] = True
        assert configure._header_collect_select(options) == (
            "testmon: collection deactivated, selection automatically deactivated because -k was used, ",
            False,
            False,
        )

    def test_nocollect_coverage(self, options):
        options["testmon"] = True
        assert configure._header_collect_select(options, coverage=True) == (
            "testmon: collection automatically deactivated because it's not compatible with coverage.py, ",
            False,
            True,
        )
