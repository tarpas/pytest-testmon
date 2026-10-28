import pytest

pytest_plugins = "pytester"


class GetConfigPlugin:
    def pytest_configure(self, config):
        self.ignore_dependencies = config.getini("testmon_ignore_dependencies")


def assert_one_two(td):
    get_config_plugin = GetConfigPlugin()
    td.runpytest_inprocess("-v", plugins=[get_config_plugin])
    assert get_config_plugin.ignore_dependencies == ["one", "two"]


def test_ignore_setup(testdir):
    testdir.makefile(
        ".cfg",
        setup="""
                    [tool:pytest]
                    testmon_ignore_dependencies=one two
                    """,
    )
    assert_one_two(testdir)


def test_ignore_tox(testdir):
    testdir.makefile(
        ".ini",
        tox="""
                    [pytest]
                    testmon_ignore_dependencies=one two
                    """,
    )

    assert_one_two(testdir)


@pytest.mark.skipif(pytest.__version__ < "6.0", reason="requires pytest >= 6.0")
def test_ignore_toml(testdir):
    testdir.makefile(
        ".toml",
        pyproject="""
                    [tool.pytest.ini_options]
                    testmon_ignore_dependencies="one two"
                    """,
    )

    assert_one_two(testdir)


def test_get_all_collected_items(testdir):
    testdir.makepyfile(__init__="")

    testdir.makepyfile(
        test_a="""
        import pytest
        class Test1():
            @pytest.mark.parametrize('a', [1, 2])
            def test_1(self, a):
                pass
            def test_2(self):
                pass
    """
    )

    class Plugin:
        def __init__(self):
            self.raw_test_names = []

        @pytest.hookimpl(tryfirst=True, hookwrapper=True)
        def pytest_pycollect_makeitem(self, collector, name, obj):
            makeitem_result = yield
            items = makeitem_result.get_result() or []

            try:
                self.raw_test_names.extend(
                    [item.nodeid for item in items if isinstance(item, pytest.Item)]
                )
            except TypeError:  # 'Class' object is not iterable
                pass

    plugin = Plugin()
    result = testdir.runpytest_inprocess("test_a.py::Test1::test_2", plugins=[plugin])
    assert plugin.raw_test_names == [
        "test_a.py::Test1::test_1[1]",
        "test_a.py::Test1::test_1[2]",
        "test_a.py::Test1::test_2",
    ]
    result.assert_outcomes(1, 0, 0)
