import pytest

pytest_plugins = "pytester"


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
            self.raw_nodeids = []

        @pytest.hookimpl(tryfirst=True, hookwrapper=True)
        def pytest_pycollect_makeitem(self, collector, name, obj):
            makeitem_result = yield
            items = makeitem_result.get_result() or []

            try:
                self.raw_nodeids.extend(
                    [item.nodeid for item in items if isinstance(item, pytest.Item)]
                )
            except TypeError:  # 'Class' object is not iterable
                pass

    plugin = Plugin()
    result = testdir.runpytest_inprocess("test_a.py::Test1::test_2", plugins=[plugin])
    assert plugin.raw_nodeids == [
        "test_a.py::Test1::test_1[1]",
        "test_a.py::Test1::test_1[2]",
        "test_a.py::Test1::test_2",
    ]
    result.assert_outcomes(1, 0, 0)
