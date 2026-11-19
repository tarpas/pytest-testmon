"""A testmon.net that fails must not fail the pytest run; see RemoteDB in testmon_core."""

import importlib.util
import socket
from xmlrpc.client import ProtocolError, ServerProxy

import pytest

from testmon import testmon_core
from testmon.db import DB
from testmon.testmon_core import get_data_file_path

pytest_plugins = ("pytester",)

RUNS = [pytest.param((), id="single")]
if importlib.util.find_spec("xdist"):
    RUNS.append(pytest.param(("-n", "2"), id="xdist"))


class FlakyRemote:
    """Stands in for the testmon.net proxy: a DB in another file, answering 502 to `failing`."""

    def __init__(self, datafile, failing, healthy_calls=0):
        self.database = DB(datafile)
        self.failing = failing
        self.healthy_calls = (
            healthy_calls  # each of `failing` works this many times first
        )

    def __getattr__(self, name):
        if name in self.failing:
            if self.healthy_calls <= 0:
                raise ProtocolError("testmon.net", 502, "Bad Gateway", {})
            self.healthy_calls -= 1
        return getattr(self.database, name)

    def close(self):
        self.database.close()


@pytest.fixture
def run(pytester, request):
    """run(*failing) -> RunResult of `pytest --testmon` against a remote failing those calls."""
    pytester.makepyfile(
        lib="def value():\n    return 1\n",
        test_lib="import lib\n\ndef test_lib():\n    assert lib.value()\n",
        test_other="def test_other():\n    pass\n",
    )

    def run_with(*failing, healthy_calls=0):
        class Plugin:
            @pytest.hookimpl(tryfirst=True)
            def pytest_configure(self, config):
                config.tmnet = FlakyRemote(
                    str(pytester.path / "remote.db"), failing, healthy_calls
                )

        return pytester.runpytest_inprocess(
            "--testmon", *request.param, plugins=[Plugin()]
        )

    return run_with


@pytest.mark.parametrize("run", RUNS, indirect=True)
def test_selection_from_remote(run, pytester):
    run().assert_outcomes(passed=2)
    pytester.makepyfile(lib="def value():\n    return 2\n")

    run().assert_outcomes(passed=1)

    assert not (pytester.path / get_data_file_path()).exists()


@pytest.mark.parametrize("run", RUNS, indirect=True)
@pytest.mark.parametrize(
    "call", ["fetch_unknown_files", "determine_tests", "all_test_executions"]
)
def test_failure_while_selecting_falls_back_to_local(run, call, pytester, caplog):
    run(call).assert_outcomes(passed=2)

    assert "falling back to .testmondata" in caplog.text
    assert (pytester.path / get_data_file_path()).exists()


@pytest.mark.parametrize("run", RUNS, indirect=True)
@pytest.mark.parametrize(
    "call", ["insert_test_file_fps", "delete_test_executions", "finish_execution"]
)
def test_failure_while_saving_does_not_stop_the_run(run, call, pytester, caplog):
    run(call).assert_outcomes(passed=2)

    assert "its results are not saved" in caplog.text
    assert not (pytester.path / get_data_file_path()).exists()


def test_silent_server_times_out(monkeypatch):
    monkeypatch.setattr(testmon_core, "REMOTE_TIMEOUT", 0.2)
    with socket.socket() as silent:  # accepts the connection, never answers
        silent.bind(("127.0.0.1", 0))
        silent.listen()
        url = f"http://127.0.0.1:{silent.getsockname()[1]}/"
        transport = testmon_core.timeout_transport(url, headers=[("x-api-key", "k")])
        proxy = ServerProxy(url, transport=transport)

        with pytest.raises(testmon_core.REMOTE_ERRORS), proxy:
            proxy.initiate_execution()

        connection, _ = silent.accept()
        with connection:
            assert b"x-api-key: k" in connection.recv(1000)


@pytest.mark.parametrize("run", RUNS, indirect=True)
def test_failure_after_selecting_does_not_hide_a_failing_test(run, pytester):
    pytester.makepyfile(test_failing="def test_failing():\n    assert False\n")
    run().assert_outcomes(passed=2, failed=1)

    # the selection reads all_test_executions once; every later read fails
    result = run("all_test_executions", healthy_calls=1)

    result.assert_outcomes(failed=1)
