import pytest

pytest_plugins = ("pytester",)

pytest.importorskip("xdist")


@pytest.fixture
def testdir(pytester):
    pytester.makepyfile(
        dependency="""
            def value():
                return 1
        """,
        test_worker="""
            from dependency import value

            def test_worker_shares_the_controller_execution(request):
                assert value() == 1
                assert request.config.workerinput.get("testmon_exec_id") is not None
        """,
        test_unaffected="""
            def test_unaffected():
                pass
        """,
    )
    pytester.runpytest_inprocess("--testmon", "-n", "2").assert_outcomes(passed=2)
    return pytester


def test_selecting_workers_get_the_controller_execution(testdir):
    testdir.makepyfile(
        dependency="""
            def value():
                return 1 + 0
        """
    )
    result = testdir.runpytest_inprocess(
        "--testmon-nocollect", "--testmon-forceselect", "-n", "2"
    )
    result.assert_outcomes(passed=1)
