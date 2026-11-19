import socket

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


def test_workers_follow_the_controller_to_local_storage(pytester, monkeypatch):
    """testmon.net unreachable: the controller falls back to .testmondata and so do the workers."""
    with socket.socket() as free:  # a port nobody listens on
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    pytester.makeini(f"[pytest]\ntmnet_url = http://127.0.0.1:{port}/\n")
    monkeypatch.setenv("TMNET_API_KEY", "irrelevant")
    pytester.makepyfile(test_a="def test_a():\n    pass\n")

    result = pytester.runpytest_inprocess("--tmnet", "-n", "2")

    result.assert_outcomes(passed=1)
    assert (pytester.path / ".testmondata").exists()
