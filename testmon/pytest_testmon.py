import time
import xmlrpc.client
import os

from collections import defaultdict
from datetime import date, timedelta

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
        "--testmon-connect-timeout",
        action="store",
        type=int,
        default=60,
        dest="testmon_connect_timeout",
        help=(
            "Set the timeout for opening a connection to the sqlite database."
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
        "--tmnet",
        action="store_true",
        dest="tmnet",
        help=(
            "This is used for internal beta. Please don't use. You can go to https://www.testmon.net/ to register."
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
    ]:
        if config.getoption(label):
            result.append(label.replace("testmon_", ""))
    return result


def init_testmon_data(config, connect_timeout):
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
            elif tmnet_api_key is None:
                logger.warning(
                    "TMNET_API_KEY not set.",
                )
            rpc_proxy = xmlrpc.client.ServerProxy(
                url,
                allow_none=True,
                headers=[("x-api-key", tmnet_api_key)],
            )

    testmon_data = TestmonData(
        rootdir=config.rootdir.strpath,
        database=rpc_proxy,
        environment=environment,
        system_packages=system_packages,
        connect_timeout=connect_timeout,
    )
    testmon_data.determine_stable(bool(rpc_proxy))
    config.testmon_data = testmon_data


def parallelism_status(config):
    if hasattr(config, "workerinput"):
        return "worker"

    if getattr(config.option, "dist", "no") == "no":
        return "single"

    return "controller"


def register_plugins(config, should_select, should_collect, cov_plugin):
    if should_select or should_collect:
        config.pluginmanager.register(
            TestmonSelect(config, config.testmon_data), "TestmonSelect"
        )

    if should_collect:
        config.pluginmanager.register(
            TestmonCollect(
                TestmonCollector(
                    config.rootdir.strpath,
                    testmon_labels=testmon_options(config),
                    cov_plugin=cov_plugin,
                ),
                config.testmon_data,
                host=parallelism_status(config),
            ),
            "TestmonCollect",
        )


def pytest_configure(config):
    coverage_stack = None
    try:
        from tmnet.testmon_core import (
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
    config.testmon_config = tm_conf
    if tm_conf.select or tm_conf.collect:
        try:
            init_testmon_data(config, connect_timeout=tm_conf.connect_timeout)
            register_plugins(config, tm_conf.select, tm_conf.collect, cov_plugin)
        except TestmonException as error:
            pytest.exit(str(error))


def pytest_report_header(config):
    tm_conf = config.testmon_config

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
                "\nWe'd like to hear from testmon users! "
                "🙏🙏 go to https://testmon.org/survey to leave feedback ✅❌"
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

        if changed_files_msg == "0" and len(stable_files) == 0 and not packages_change:
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
    if hasattr(config, "testmon_data"):
        config.testmon_data.close_connection()


class TestmonCollect:
    def __init__(self, testmon, testmon_data, host="single", cov_plugin=None):
        self.testmon_data = testmon_data
        self.testmon = testmon
        self._host = host

        self.reports = defaultdict(lambda: {})
        self.raw_test_names = []
        self.cov_plugin = cov_plugin
        self._sessionstarttime = time.time()

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_pycollect_makeitem(self, collector, name, obj):
        makeitem_result = yield
        items = makeitem_result.get_result() or []
        try:
            self.raw_test_names.extend(
                [item.nodeid for item in items if isinstance(item, pytest.Item)]
            )
        except TypeError:
            pass

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, session, config, items):
        should_sync = not session.testsfailed
        if getattr(config, "workerinput", {}).get("workerid", "gw0") != "gw0":
            should_sync = False
        if should_sync:
            config.testmon_data.sync_db_fs_tests(retain=set(self.raw_test_names))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        self.testmon.start_testmon(item.nodeid, nextitem.nodeid if nextitem else None)
        result = yield
        if result.excinfo and issubclass(result.excinfo[0], BaseException):
            self.testmon.discard_current()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        result = yield

        if call.when == "teardown":
            report = result.get_result()
            report.nodes_files_lines = self.testmon.get_batch_coverage_data()
            result.force_result(report)

    @pytest.hookimpl
    def pytest_runtest_logreport(self, report):
        if self._host == "worker":
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

    def pytest_keyboard_interrupt(self, excinfo):
        if self._host == "single":
            nodes_files_lines = self.testmon.get_batch_coverage_data()

            test_executions_fingerprints = self.testmon_data.get_tests_fingerprints(
                nodes_files_lines, self.reports
            )
            self.testmon_data.save_test_execution_file_fps(test_executions_fingerprints)
            self.testmon.close()

    def pytest_sessionfinish(self, session):
        if self._host in ("single", "controller"):
            self.testmon_data.db.finish_execution(
                self.testmon_data.exec_id,
                time.time() - self._sessionstarttime,
                session.config.testmon_config.select,
            )
        self.testmon.close()


def did_fail(reports):
    return reports["failed"]


def get_failing(all_test_executions):
    failing_files, failing_tests = set(), {}
    for test_name, result in all_test_executions.items():
        if did_fail(all_test_executions[test_name]):
            failing_files.add(home_file(test_name))
            failing_tests[test_name] = result
    return failing_files, failing_tests


def sort_items_by_duration(items, avg_durations):
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
    def __init__(self, config, testmon_data):
        self.testmon_data = testmon_data
        self.config = config

        failing_files, failing_test_names = get_failing(testmon_data.all_tests)

        self.deselected_files = [
            file for file in testmon_data.stable_files if file not in failing_files
        ]
        self.deselected_tests = [
            test_name
            for test_name in testmon_data.stable_test_names
            if test_name not in failing_test_names
        ]
        self._interrupted = False

    def pytest_ignore_collect(self, path, config):
        strpath = cached_relpath(path.strpath, config.rootdir.strpath)
        if strpath in self.deselected_files and self.config.testmon_config.select:
            return True
        return None

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, session, config, items):
        selected = []
        deselected = []
        for item in items:
            if item.nodeid in self.deselected_tests:
                deselected.append(item)
            else:
                selected.append(item)

        sort_items_by_duration(selected, self.testmon_data.avg_durations)

        if self.config.testmon_config.select:
            items[:] = selected
            session.config.hook.pytest_deselected(
                items=([FakeItemFromTestmon(session.config)] * len(deselected))
            )
        else:
            sort_items_by_duration(deselected, self.testmon_data.avg_durations)
            items[:] = selected + deselected

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        if len(self.deselected_tests) and exitstatus == ExitCode.NO_TESTS_COLLECTED:
            session.exitstatus = ExitCode.OK

    @pytest.hookimpl(trylast=True)
    def pytest_terminal_summary(self):
        if self._interrupted:
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

    def pytest_keyboard_interrupt(self, excinfo):
        self._interrupted = True


class FakeItemFromTestmon:
    def __init__(self, config):
        self.config = config
