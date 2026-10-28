"""The collection backends in testmon.collectors, mostly the sys.monitoring one."""

import os
import sys
import textwrap
import threading

import pytest
from coverage import Coverage

from testmon import collectors
from testmon.collectors import (
    COVERAGE_BACKEND,
    SYSMON_BACKEND,
    CoverageBackend,
    SysmonBackend,
    body_line,
    default_backend_name,
    make_backend,
)
from testmon.testmon_core import TestmonCollector

pytest_plugins = ("pytester",)

needs_sysmon = pytest.mark.skipif(
    collectors.SYSMON is None, reason="sys.monitoring needs CPython 3.12+"
)


class TestDefaultBackend:
    def test_follows_interpreter(self, monkeypatch):
        monkeypatch.delenv("TESTMON_COLLECTOR", raising=False)
        expected = SYSMON_BACKEND if collectors.SYSMON else COVERAGE_BACKEND
        assert default_backend_name() == expected

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("TESTMON_COLLECTOR", COVERAGE_BACKEND)
        assert default_backend_name() == COVERAGE_BACKEND
        monkeypatch.setenv("TESTMON_COLLECTOR", "nonsense")
        assert default_backend_name() == (
            SYSMON_BACKEND if collectors.SYSMON else COVERAGE_BACKEND
        )

    @needs_sysmon
    def test_subprocess_tracking_forces_coverage(self, testdir, monkeypatch):
        monkeypatch.chdir(testdir.tmpdir)
        backend = make_backend(SYSMON_BACKEND, str(testdir.tmpdir), subprocess=True)
        try:
            assert isinstance(backend, CoverageBackend)
        finally:
            backend.close()
        assert isinstance(make_backend(SYSMON_BACKEND, "."), SysmonBackend)


SAMPLE = textwrap.dedent(
    '''\
    # a comment before the first statement

    import functools
    @functools.lru_cache
    def decorated(x):
        return x
    def oneliner(): return 1
    def docstring_only():
        """only a docstring"""
    class K:
        attr = 1
        def method(self):
            def inner():
                return 1
            return inner()
    lam = lambda: 1
    def gen():
        yield 1
    '''
)


def _code_objects(code):
    yield code
    for const in code.co_consts:
        if hasattr(const, "co_code"):
            yield from _code_objects(const)


@needs_sysmon
class TestBodyLine:
    """body_line must return a line inside the block process_code builds for the code
    object, i.e. between the first and last statement of its body (one-liners and
    lambdas: the header line is the body line). Decorated functions start at the
    decorator, modules at line 1 with a synthetic line 0: neither is the body."""

    @pytest.fixture(scope="class")
    def lines(self):
        code = compile(SAMPLE, "<sample>", "exec")
        return {c.co_qualname: body_line(c) for c in _code_objects(code)}

    def test_module_first_statement(self, lines):
        assert lines["<module>"] == 3

    def test_decorated_skips_decorator_and_def(self, lines):
        assert lines["decorated"] == 6

    def test_oneliner_is_its_own_line(self, lines):
        assert lines["oneliner"] == 7

    def test_docstring_only_falls_back_to_def(self, lines):
        # the docstring is folded into the code object; the def line maps to the
        # enclosing block, which is where a no-op function belongs anyway
        assert lines["docstring_only"] == 8

    def test_class_body_and_methods(self, lines):
        assert lines["K"] == 11
        assert lines["K.method"] == 13
        assert lines["K.method.<locals>.inner"] == 14

    def test_lambda_and_generator(self, lines):
        assert lines["<lambda>"] == 16
        assert lines["gen"] == 18


@needs_sysmon
class TestSysmonBackend:
    @pytest.fixture
    def project(self, testdir):
        testdir.makepyfile(
            proj_dep=textwrap.dedent(
                """\
                import functools

                @functools.lru_cache
                def cached(x):
                    return x + 1

                def plain():
                    return 2

                class K:
                    def method(self):
                        return 3

                def gen():
                    yield 4
                """
            )
        )
        testdir.syspathinsert()
        import proj_dep  # pylint: disable=import-error,import-outside-toplevel

        yield proj_dep
        del sys.modules["proj_dep"]

    @pytest.fixture
    def backend(self, testdir):
        backend = SysmonBackend(str(testdir.tmpdir))
        backend.start()
        yield backend
        backend.stop()

    def test_records_one_body_line_per_entered_function(self, project, backend):
        backend.switch("t")
        project.cached(1)
        project.plain()
        project.K().method()
        next(project.gen())
        data = backend.take()
        assert data["t"][project.__file__] == {5, 8, 12, 15}

    def test_every_test_sees_the_shared_function(self, project, backend):
        for name in ("t1", "t2", "t3"):
            backend.switch(name)
            project.plain()
        data = backend.take()
        assert {name: lines[project.__file__] for name, lines in data.items()} == {
            "t1": {8},
            "t2": {8},
            "t3": {8},
        }

    def test_untouched_function_is_not_recorded(self, project, backend):
        backend.switch("t")
        project.plain()
        assert backend.take()["t"][project.__file__] == {8}

    def test_events_before_first_switch_are_dropped(self, project, backend):
        project.plain()
        backend.switch("t")
        project.cached(2)
        assert backend.take() == {"t": {project.__file__: {5}}}

    def test_take_clears(self, project, backend):
        backend.switch("t")
        project.plain()
        backend.take()
        backend.switch("t2")
        assert backend.take() == {"t2": {}}

    def test_filters_stdlib_and_synthetic_code(self, project, backend, testdir):
        backend.switch("t")
        import json  # pylint: disable=import-outside-toplevel

        json.dumps({"a": [1]}, indent=1)  # pure-python encoder, in the stdlib
        exec(compile("def f():\n    return 1\nf()", "<string>", "exec"), {})
        project.plain()
        data = backend.take()
        assert list(data["t"]) == [project.__file__]

    def test_relative_filenames_resolve_against_cwd(self, backend, testdir):
        testdir.makepyfile(relative="def h():\n    return 1\nh()\n")
        backend.switch("t")
        with open("relative.py", encoding="utf-8") as source:
            exec(compile(source.read(), "relative.py", "exec"), {})
        assert backend.take()["t"] == {
            os.path.join(str(testdir.tmpdir), "relative.py"): {1, 2}
        }

    def test_worker_threads_are_recorded(self, project, backend):
        backend.switch("t")
        thread = threading.Thread(target=project.plain)
        thread.start()
        thread.join()
        assert backend.take()["t"][project.__file__] == {8}

    def test_nested_backends_both_record_and_free_the_tool(self, project, testdir):
        outer = SysmonBackend(str(testdir.tmpdir))
        inner = SysmonBackend(str(testdir.tmpdir))
        outer.start()
        outer.switch("outer")
        project.plain()
        inner.start()
        inner.switch("inner")
        project.plain()  # already DISABLEd for outer; inner's start re-armed it
        project.cached(3)
        inner.stop()
        project.K().method()
        outer.stop()
        assert inner.take()["inner"][project.__file__] == {5, 8}
        assert outer.take()["outer"][project.__file__] == {5, 8, 12}
        assert outer not in collectors._ENGINE.backends
        assert inner not in collectors._ENGINE.backends
        tool_ids = [i for i in range(6) if sys.monitoring.get_tool(i) == "testmon"]
        # the tool stays in use when this suite itself runs under --testmon
        assert len(tool_ids) == (1 if collectors._ENGINE.backends else 0)

    @pytest.mark.parametrize("core", ["ctrace", "sysmon"])
    def test_coexists_with_a_running_coverage(self, project, backend, core):
        cov = Coverage(data_file=None, config_file=False, include=[project.__file__])
        cov._warn_no_data = False
        try:
            cov.set_option("run:core", core)
        except Exception:  # pylint: disable=broad-except
            pytest.skip(f"coverage {Coverage.__module__} has no core option")
        cov.start()
        backend.switch("t")
        project.plain()
        backend.switch("t2")
        project.cached(4)
        cov.stop()
        data = backend.take()
        assert data["t"][project.__file__] == {8}
        assert data["t2"][project.__file__] == {5}
        assert {5, 8} <= set(cov.get_data().lines(project.__file__))


class TestCollectorWithBackend:
    """TestmonCollector behaves the same whichever backend it drives."""

    def test_start_stop_many(self, collector_backend):
        first = TestmonCollector("", backend=collector_backend)
        first.start_testmon("1")
        second = TestmonCollector("", backend=collector_backend)
        second.start_testmon("2")
        third = TestmonCollector("", backend=collector_backend)
        third.close()
        second.start_testmon("4")
        second.close()
        first.close()
        assert first.backend is None and first.cov is None

    def test_plugin_run_stores_fingerprints(
        self, testdir, collector_backend, monkeypatch
    ):
        monkeypatch.setenv("TESTMON_COLLECTOR", collector_backend)
        testdir.makepyfile(
            dep="def used():\n    return 1\n\ndef unused():\n    return 2\n",
            test_a="from dep import used\n\ndef test_1():\n    assert used() == 1\n",
        )
        result = testdir.runpytest_inprocess("--testmon", "-p", "no:cacheprovider")
        result.assert_outcomes(passed=1)
        testdir.makepyfile(
            dep="def used():\n    return 1\n\ndef unused():\n    return 3\n"
        )
        result = testdir.runpytest_inprocess("--testmon", "-p", "no:cacheprovider")
        result.assert_outcomes(passed=0)  # unused() changed: test_1 stays deselected
        testdir.makepyfile(
            dep="def used():\n    return 11\n\ndef unused():\n    return 3\n"
        )
        result = testdir.runpytest_inprocess("--testmon", "-p", "no:cacheprovider")
        result.assert_outcomes(failed=1)  # used() changed: test_1 runs again
