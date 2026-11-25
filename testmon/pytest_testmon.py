# -*- coding: utf-8 -*-
"""
Main module of testmon pytest plugin.
"""

import time
import xmlrpc.client
import os

from collections import defaultdict
from datetime import date, timedelta

from pathlib import Path
import pytest

from _pytest.config import ExitCode, Config
from _pytest.terminal import TerminalReporter

from testmon.configure import TmConf

from testmon.testmon_core import (
    TestmonCollector,
    eval_environment,
    TestmonData,
    home_file,
    TestmonException,
    get_test_execution_class_name,
    get_test_execution_module_name,
    cached_relpath,
    timeout_transport,
)
from testmon import configure
from testmon.common import get_logger, get_system_packages

SURVEY_NOTIFICATION_INTERVAL = timedelta(days=28)

logger = get_logger(__name__)


def pytest_addoption(parser):
    group = parser.getgroup(
        "automatically select tests affected by changes (pytest-testmon)"
    )

    group.addoption(
        "--testmon",
        action="store_true",
        dest="testmon",
        help=(
            "Select tests affected by changes (based on previously collected data) "
            "and collect + write new data (.testmondata file). "
            "Either collection or selection might be deactivated "
            "(sometimes automatically). See below."
        ),
    )

    group.addoption(
        "--testmon-noselect",
        action="store_true",
        dest="testmon_noselect",
        help=(
            "Reorder and prioritize the tests most likely to fail first, but don't deselect anything. "
            "Forced if you use -m, -k, -l, -lf, test_file.py::test_name"
        ),
    )

    group.addoption(
        "--testmon-nocollect",
        action="store_true",
        dest="testmon_nocollect",
        help=(
            "Run testmon but deactivate the collection and writing of testmon data. "
            "Forced if you run under debugger or coverage."
        ),
    )

    group.addoption(
        "--testmon-forceselect",
        action="store_true",
        dest="testmon_forceselect",
        help=(
            "Run testmon and select only tests affected by changes "
            "and satisfying pytest selectors at the same time."
        ),
    )

    group.addoption(
        "--no-testmon",
        action="store_true",
        dest="no-testmon",
        help=(
            "Turn off (even if activated from config by default).\n"
            "Forced if neither read nor write is possible "
            "(debugger plus test selector)."
        ),
    )

    group.addoption(
        "--testmon-env",
        action="store",
        type=str,
        dest="environment_expression",
        default="",
        help=(
            "This allows you to have separate coverage data within one"
            " .testmondata file, e.g. when using the same source"
            " code serving different endpoints or Django settings."
        ),
    )
    group.addoption(
        "--testmon-singleprocess",
        action="store_false",
        dest="testmon_singleprocess",
        help="Don't track subprocesses",
    )
    group.addoption(
        "--tmnet",
        action="store_true",
        dest="tmnet",
        help=(
            "Use tmnet cloud for storage instead of .testmondata file used by --testmon (see https://www.testmon.net)."
        ),
    )

    group.addoption(
        "--tmnet-mirror",
        action="store_true",
        dest="tmnet_mirror",
        help=(
            "With --tmnet, also record every result in the local .testmondata. "
            "Deprecated, to be removed in pytest-testmon 3.1."
        ),
    )

    parser.addini("environment_expression", "environment expression", default="")
    parser.addini(
        "testmon_ignore_dependencies",
        "ignore dependencies",
        type="args",
        default=[],
    )
    parser.addini("tmnet_url", "URL of the testmon.net api server.")
    parser.addini("tmnet_api_key", "testmon api key")


def testmon_options(config):
    result = []
    for label in [
        "testmon",
        "no-testmon",
        "environment_expression",
        "testmon_singleprocess",
    ]:
        if config.getoption(label):
            result.append(label.replace("testmon_", ""))
    return result


def init_testmon_data(config: Config):
    if get_running_as(config) == "worker":
        # The controller decides what to run and saves the results (TestmonXdistSync);
        # a worker has no storage, so all workers collect the same tests.
        config.testmon_data = None
        return

    environment = config.getoption("environment_expression") or eval_environment(
        config.getini("environment_expression")
    )
    ignore_dependencies = config.getini("testmon_ignore_dependencies")

    system_packages = get_system_packages(ignore=ignore_dependencies)

    url = config.getini("tmnet_url")
    rpc_proxy = None

    if config.testmon_config.tmnet or getattr(config, "tmnet", None):
        rpc_proxy = getattr(config, "tmnet", None)

        if not url:
            url = "https://api1.testmon.net/"
        if not rpc_proxy:
            tmnet_api_key = config.getini("tmnet_api_key")
            if "TMNET_API_KEY" in os.environ:
                if tmnet_api_key:
                    logger.warning(
                        "Duplicate TMNET_API_KEY (environment and ini file). \
                         Using TMNET_API_KEY from %s",
                        config.inipath,
                    )
                else:
                    tmnet_api_key = os.getenv("TMNET_API_KEY")

            if not tmnet_api_key.strip():
                raise ValueError(
                    "TMNET_API_KEY is required when using --tmnet. "
                    "Please set it in pytest.ini, pyproject.toml, or as an environment variable. "
                )

            rpc_proxy = xmlrpc.client.ServerProxy(
                url,
                allow_none=True,
                transport=timeout_transport(
                    url, headers=[("x-api-key", tmnet_api_key.strip())]
                ),
            )

    testmon_data: TestmonData = TestmonData.for_local_run(
        rootdir=str(config.rootpath),
        database=rpc_proxy,
        environment=environment,
        system_packages=system_packages,
        mirror=config.getoption("tmnet_mirror"),
    )
    testmon_data.determine_stable()
    config.testmon_data = testmon_data


def get_running_as(config):
    if hasattr(config, "workerinput"):
        return "worker"

    if getattr(config.option, "dist", "no") == "no":
        return "single"

    return "controller"


def register_plugins(config, should_select, should_collect, cov_plugin):
    if should_select or should_collect:
        config.pluginmanager.register(
            TestmonSelect(
                config,
                config.testmon_data,
                selection=getattr(config, "workerinput", {}).get("testmon_selection"),
            ),
            "TestmonSelect",
        )

    if should_collect:
        config.pluginmanager.register(
            TestmonCollect(
                TestmonCollector(
                    str(config.rootpath),
                    testmon_labels=testmon_options(config),
                    cov_plugin=cov_plugin,
                ),
                config.testmon_data,
                running_as=get_running_as(config),
            ),
            "TestmonCollect",
        )
    if (should_select or should_collect) and config.pluginmanager.hasplugin("xdist"):
        config.pluginmanager.register(TestmonXdistSync(sync=should_collect))


def pytest_configure(config):
    coverage_stack = None
    try:
        from tmnet.testmon_core import (  # pylint: disable=import-outside-toplevel
            Testmon as UberTestmon,
        )

        coverage_stack = UberTestmon.coverage_stack
    except ImportError:
        pass

    cov_plugin = None
    cov_plugin = config.pluginmanager.get_plugin("_cov")

    tm_conf = configure.header_collect_select(
        config, coverage_stack, cov_plugin=cov_plugin
    )
    config.testmon_config: TmConf = tm_conf
    if tm_conf.select or tm_conf.collect:
        if config.pluginmanager.has_plugin(
            "TestmonSelect"
        ) or config.pluginmanager.has_plugin("TestmonCollect"):
            pytest.exit("You cannot use two instances of testmon plugin.")
        try:
            init_testmon_data(config)
            register_plugins(config, tm_conf.select, tm_conf.collect, cov_plugin)
        except TestmonException as error:
            pytest.exit(str(error))


def pytest_report_header(config):
    tm_conf = config.testmon_config

    if (
        getattr(config, "testmon_data", None) is None
    ):  # an xdist worker: nobody reads it
        return tm_conf.message

    if tm_conf.collect or tm_conf.select:
        unstable_files = getattr(config.testmon_data, "unstable_files", set())
        stable_files = getattr(config.testmon_data, "stable_files", set())
        environment = config.testmon_data.environment

        tm_conf.message += changed_message(
            config,
            environment,
            config.testmon_data.system_packages_change,
            tm_conf.select,
            stable_files,
            unstable_files,
        )

        show_survey_notification = True
        last_notification_date = config.testmon_data.db.fetch_attribute(
            "last_survey_notification_date"
        )
        if last_notification_date:
            last_notification_date = date.fromisoformat(last_notification_date)
            if date.today() - last_notification_date < SURVEY_NOTIFICATION_INTERVAL:
                show_survey_notification = False
            else:
                config.testmon_data.db.write_attribute(
                    "last_survey_notification_date", date.today().isoformat()
                )
        else:
            config.testmon_data.db.write_attribute(
                "last_survey_notification_date", date.today().isoformat()
            )

        if show_survey_notification:
            tm_conf.message += (
                "\nHelp shape testmon! Tell us what saves you time "
                "and what we can improve: https://testmon.org/survey"
            )
    return tm_conf.message


def changed_message(
    config,
    environment,
    packages_change,
    should_select,
    stable_files,
    unstable_files,
):
    message = ""
    if should_select:
        changed_files_msg = ", ".join(unstable_files)
        if changed_files_msg == "" or len(changed_files_msg) > 100:
            changed_files_msg = str(len(config.testmon_data.unstable_files))

        if config.testmon_data.new_db:
            message += "new DB, "
        else:
            message += (
                "The packages installed in your Python environment have been changed. "
                "All tests have to be re-executed. "
                if packages_change
                else f"changed files: {changed_files_msg}, unchanged files: {len(stable_files)}, "
            )
    if config.testmon_data.environment:
        message += f"environment: {environment}"
    return message


def pytest_unconfigure(config):
    if getattr(config, "testmon_data", None):
        config.testmon_data.close_connection()


class TestmonCollect:
    def __init__(
        self, testmon, testmon_data: TestmonData, running_as="single", cov_plugin=None
    ):
        self.testmon_data: TestmonData = testmon_data
        self.testmon: TestmonCollector = testmon
        self._running_as = running_as

        self.reports = defaultdict(lambda: {})
        self.raw_test_names = []
        self.cov_plugin = cov_plugin
        self._sessionstarttime = time.time()

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_pycollect_makeitem(self, collector, name, obj):  # pylint: disable=unused-argument
        makeitem_result = yield
        items = makeitem_result.get_result() or []
        try:
            self.raw_test_names.extend(
                [item.nodeid for item in items if isinstance(item, pytest.Item)]
            )
        except TypeError:  # 'Class' object is not iterable
            pass

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, session, config, items):  # pylint: disable=unused-argument
        should_sync = not session.testsfailed and self._running_as in (
            "single",
            "controller",
        )
        if should_sync:
            config.testmon_data.sync_db_fs_tests(retain=set(self.raw_test_names))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):  # pylint: disable=unused-argument
        self.testmon.start_testmon(item.nodeid, nextitem.nodeid if nextitem else None)
        result = yield
        if result.excinfo and issubclass(result.excinfo[0], BaseException):
            self.testmon.discard_current()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):  # pylint: disable=unused-argument
        result = yield

        if call.when == "teardown":
            report = result.get_result()
            report.nodes_files_lines = self.testmon.get_batch_coverage_data()
            result.force_result(
                report
            )  # under xdist, report is serialized on the worker and sent to the controller

    @pytest.hookimpl
    def pytest_runtest_logreport(self, report):
        if self._running_as == "worker":
            return

        self.reports[report.nodeid][report.when] = report
        if report.when == "teardown" and hasattr(report, "nodes_files_lines"):
            if report.nodes_files_lines:
                test_executions_fingerprints = self.testmon_data.get_tests_fingerprints(
                    report.nodes_files_lines, self.reports
                )
                self.testmon_data.save_test_execution_file_fps(
                    test_executions_fingerprints
                )

    def pytest_keyboard_interrupt(self, excinfo):  # pylint: disable=unused-argument
        if self._running_as == "single":
            nodes_files_lines = self.testmon.get_batch_coverage_data()

            test_executions_fingerprints = self.testmon_data.get_tests_fingerprints(
                nodes_files_lines, self.reports
            )
            self.testmon_data.save_test_execution_file_fps(test_executions_fingerprints)
            self.testmon.close()

    def pytest_sessionfinish(self, session):  # pylint: disable=unused-argument
        if self._running_as in ("single", "controller"):
            self.testmon_data.finish_execution(
                time.time() - self._sessionstarttime,
                session.config.testmon_config.select,
            )
        self.testmon.close()


class TestmonXdistSync:
    def __init__(self, sync=True):
        self.await_nodes = 0
        self.sync = sync
        self._selection = None

    def pytest_configure_node(self, node):
        """Controller side, once per worker: send it what to deselect and how to order.

        Deciding once here, instead of each worker asking the storage, keeps the workers'
        collections identical (xdist requires it) whatever happens to testmon.net meanwhile.
        """
        # Count the node here, before it starts: counting it when it reports ready would let a
        # fast worker's collection trigger sync_db_fs_tests while a slow one is still collecting.
        self.await_nodes += 1

        if self._selection is None:
            select: TestmonSelect = node.config.pluginmanager.get_plugin(
                "TestmonSelect"
            )
            self._selection = {
                "deselected_files": select.deselected_files,
                "deselected_tests": select.deselected_tests,
                "avg_durations": dict(select.avg_durations),
            }
        node.workerinput["testmon_exec_id"] = node.config.testmon_data.exec_id
        node.workerinput["testmon_selection"] = self._selection

    def pytest_xdist_node_collection_finished(self, node, ids):  # pylint: disable=invalid-name
        self.await_nodes += -1
        if self.await_nodes == 0 and self.sync:
            node.config.testmon_data.sync_db_fs_tests(retain=set(ids))


def sort_items_by_duration(items, avg_durations) -> None:
    items.sort(key=lambda item: avg_durations[item.nodeid])
    items.sort(
        key=lambda item: avg_durations[get_test_execution_class_name(item.nodeid)]
    )
    items.sort(
        key=lambda item: avg_durations[get_test_execution_module_name(item.nodeid)]
    )


def format_time_saved(seconds):
    if not seconds:
        seconds = 0
    if seconds >= 3600:
        return f"{int(seconds / 3600)}h {int((seconds % 3600) / 60)}m"
    return f"{int(seconds / 60)}m {int((seconds % 60) % 60)}s"


class TestmonSelect:
    def __init__(self, config, testmon_data: TestmonData, selection=None):
        """`selection`: on an xdist worker, the controller's decision (no testmon_data)."""
        self.testmon_data: TestmonData = testmon_data
        self.config = config
        self._interrupted = False
        self._avg_durations = None

        if selection is not None:
            self.deselected_files = selection["deselected_files"]
            self.deselected_tests = selection["deselected_tests"]
            self._avg_durations = defaultdict(int, selection["avg_durations"])
            return

        failing_test_names = testmon_data.failed_test_names
        failing_files = {home_file(test_name) for test_name in failing_test_names}

        self.deselected_files = [
            file for file in testmon_data.stable_files if file not in failing_files
        ]
        self.deselected_tests = [
            test_name
            for test_name in testmon_data.stable_test_names
            if test_name not in failing_test_names
        ]

    @property
    def avg_durations(self):
        if self._avg_durations is None:
            self._avg_durations = self.testmon_data.avg_durations
        return self._avg_durations

    def pytest_ignore_collect(self, collection_path: Path, config):
        strpath = cached_relpath(str(collection_path), str(config.rootpath))
        if strpath in self.deselected_files and self.config.testmon_config.select:
            return True
        return None

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, session, config, items):  # pylint: disable=unused-argument
        selected = []
        deselected = []
        for item in items:
            if item.nodeid in self.deselected_tests:
                deselected.append(item)
            else:
                selected.append(item)

        sort_items_by_duration(selected, self.avg_durations)

        if self.config.testmon_config.select:
            items[:] = selected
            session.config.hook.pytest_deselected(
                items=([FakeItemFromTestmon(session.config)] * len(deselected))
            )
        else:
            sort_items_by_duration(deselected, self.avg_durations)
            items[:] = selected + deselected

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        if len(self.deselected_tests) and exitstatus == ExitCode.NO_TESTS_COLLECTED:
            session.exitstatus = ExitCode.OK

    @pytest.hookimpl(trylast=True)
    def pytest_terminal_summary(self):
        if self._interrupted or self.testmon_data is None:
            return

        if not self.config.option.verbose >= 2:
            return

        (
            run_saved_time,
            run_all_time,
            run_saved_tests,
            run_all_tests,
            total_saved_time,
            total_all_time,
            total_saved_tests,
            total_tests_all,
        ) = self.testmon_data.fetch_saving_stats(self.config.testmon_config.select)

        terminal_reporter = TerminalReporter(self.config)
        potential_or_not = ""
        if not self.config.testmon_config.select:
            potential_or_not = "Potential t"
        else:
            potential_or_not = "T"
        terminal_reporter.section(
            f"{potential_or_not}estmon savings (deselected/no testmon)",
            "=",
            **{"blue": True},
        )

        try:
            tests_all_ratio = f"{100.0 * total_saved_tests / total_tests_all:.0f}"
        except ZeroDivisionError:
            tests_all_ratio = "0"
        try:
            tests_current_ratio = f"{100.0 * run_saved_tests / run_all_tests:.0f}"
        except ZeroDivisionError:
            tests_current_ratio = "0"
        msg = f"this run: {run_saved_tests}/{run_all_tests} ({tests_current_ratio}%) tests, "
        msg += format_time_saved(run_saved_time) + "/" + format_time_saved(run_all_time)
        msg += f", all runs: {total_saved_tests}/{total_tests_all} ({tests_all_ratio}%) tests, "
        msg += (
            format_time_saved(total_saved_time)
            + "/"
            + format_time_saved(total_all_time)
        )
        terminal_reporter.write_line(msg)

    def pytest_keyboard_interrupt(self, excinfo):  # pylint: disable=unused-argument
        self._interrupted = True


class FakeItemFromTestmon:  # pylint: disable=too-few-public-methods
    def __init__(self, config):
        self.config = config
