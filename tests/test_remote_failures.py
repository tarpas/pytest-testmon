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


@pytest.fixture(params=RUNS)
def tmnet_run(pytester, request):
    """tmnet_run(*args, failing=()) -> RunResult of `pytest *args` against a remote failing those calls."""
    pytester.makepyfile(
        lib="def value():\n    return 1\n",
        test_lib="import lib\n\ndef test_lib():\n    assert lib.value()\n",
        test_other="def test_other():\n    pass\n",
    )

    def run_with(*args, failing=()):
        class Plugin:
            @pytest.hookimpl(tryfirst=True)
            def pytest_configure(self, config):
                config.tmnet = FlakyRemote(str(pytester.path / "remote.db"), failing)

        return pytester.runpytest_inprocess(*args, *request.param, plugins=[Plugin()])

    return run_with


def test_mirror_keeps_the_local_database_accurate(tmnet_run, pytester):
    tmnet_run("--testmon", "--tmnet-mirror").assert_outcomes(passed=2)
    pytester.makepyfile(lib="def value():\n    return 2\n")
    tmnet_run("--testmon", "--tmnet-mirror").assert_outcomes(passed=1)

    # the local database alone selects what changed since: only test_lib depends on lib
    pytester.makepyfile(lib="def value():\n    return 3\n")
    pytester.runpytest_inprocess("--testmon").assert_outcomes(passed=1)


LIBS = {"lib_a": "def a():\n    return 1\n", "lib_b": "def b():\n    return 1\n"}
TWO_TESTS = (
    "import lib_a, lib_b\n\n"
    "def test_a():\n    assert lib_a.a()\n\n"
    "def test_b():\n    assert lib_b.b()\n"
)


def test_mirror_started_by_a_run_that_selects_part_of_a_file(tmnet_run, pytester):
    pytester.makepyfile(test_both=TWO_TESTS, **LIBS)
    tmnet_run("--testmon").assert_outcomes(passed=4)
    pytester.makepyfile(lib_a="def a():\n    return 2\n")
    tmnet_run("--testmon", "--tmnet-mirror").assert_outcomes(passed=1)

    # testmon.net is down. The mirror has a result of test_a only: everything else runs,
    # test_b too, although its file looks unchanged to the mirror
    pytester.makepyfile(lib_b="def b():\n    return 2\n")
    tmnet_run(
        "--testmon", "--tmnet-mirror", failing=("initiate_execution",)
    ).assert_outcomes(passed=3)


def test_mirror_that_missed_the_run_which_added_a_test(tmnet_run, pytester):
    pytester.makepyfile(test_both=TWO_TESTS, **LIBS)
    tmnet_run("--testmon", "--tmnet-mirror").assert_outcomes(passed=4)
    pytester.makepyfile(
        lib_c="def c():\n    return 1\n",
        test_both=TWO_TESTS.replace("lib_b\n", "lib_b, lib_c\n")
        + "\ndef test_c():\n    assert lib_c.c()\n",
    )
    tmnet_run("--testmon").assert_outcomes(passed=3)  # not mirrored
    # the next two runs bring the mirror's test_a and test_b up to date, not test_c
    pytester.makepyfile(lib_a="def a():\n    return 2\n")
    tmnet_run("--testmon", "--tmnet-mirror").assert_outcomes(passed=1)
    pytester.makepyfile(lib_b="def b():\n    return 2\n")
    tmnet_run("--testmon", "--tmnet-mirror").assert_outcomes(passed=1)

    pytester.makepyfile(lib_c="def c():\n    return 2\n")
    tmnet_run(
        "--testmon", "--tmnet-mirror", failing=("initiate_execution",)
    ).assert_outcomes(passed=1)


def test_no_local_database_without_the_mirror_option(tmnet_run, pytester):
    tmnet_run("--testmon").assert_outcomes(passed=2)

    assert not (pytester.path / get_data_file_path()).exists()


def test_mirror_keeps_recording_when_testmon_net_fails_while_saving(
    tmnet_run, pytester
):
    tmnet_run(
        "--testmon", "--tmnet-mirror", failing=("insert_test_file_fps",)
    ).assert_outcomes(passed=2)

    pytester.makepyfile(lib="def value():\n    return 2\n")
    pytester.runpytest_inprocess("--testmon").assert_outcomes(passed=1)


def test_a_mirror_that_cannot_be_opened_fails_like_a_local_run(tmnet_run, pytester):
    (pytester.path / get_data_file_path()).mkdir()
    local = pytester.runpytest_inprocess("--testmon")

    assert tmnet_run("--testmon", "--tmnet-mirror").ret == local.ret != 0


def test_failure_while_selecting_with_a_mirror_falls_back_to_one_local_database(
    tmnet_run, pytester, caplog
):
    tmnet_run(
        "--testmon", "--tmnet-mirror", failing=("determine_tests",)
    ).assert_outcomes(passed=2)

    assert "falling back to .testmondata" in caplog.text
    pytester.makepyfile(lib="def value():\n    return 2\n")
    pytester.runpytest_inprocess("--testmon").assert_outcomes(passed=1)
