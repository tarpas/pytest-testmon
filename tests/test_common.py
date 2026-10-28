# pylint: disable=unused-argument
from testmon.common import get_system_packages

pytest_plugins = ("pytester",)


class TestMisc:
    def test_get_system_packages(self, monkeypatch):
        monkeypatch.setattr(
            "testmon.common.get_system_packages_raw", lambda: [("a", "1.2.3")]
        )
        assert get_system_packages() == "a 1.2.3"

    def test_get_system_packages_ignore(self):
        assert "pytest " not in get_system_packages(ignore={"pytest"})
