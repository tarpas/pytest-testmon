import xmlrpc
from collections import defaultdict
from datetime import date, timedelta

import pytest
import pkg_resources

from _pytest.config import ExitCode, Config

from testmon.configure import TmConf

from testmon.testmon_core import (
    TestmonCollector,
    eval_environment,
    TestmonData,
    home_file,
    TestmonException,
    get_test_execution_class_name,
    get_test_execution_module_name,
    nofili2fingerprints,
    cached_relpath,
)
from testmon import configure

SURVEY_NOTIFICATION_INTERVAL = timedelta(days=28)


def pytest_addoption(parser):
    group = parser.getgroup("testmon")

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
        "--testmon-nocollect",
        action="store_true",
        dest="testmon_nocollect",
        help=(
            "Run testmon but deactivate the collection and writing of testmon data. "
            "Forced if you run under debugger or coverage."
        ),
    )

    group.addoption(
        "--testmon-noselect",
        action="store_true",
        dest="testmon_noselect",
        help=(
            "Run testmon but deactivate selection, so all tests selected by other "
            "means will be collected and executed. "
            "Forced if you use -k, -l, -lf, test_file.py::test_name"
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
        help=("Run testmon in the network mode. "),
    )

    parser.addini("environment_expression", "environment expression", default="")
    parser.addini("testmon_url", "URL of the testmon.net api server.")
    parser.addini("testmon_api_key", "testmon api key")


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


def init_testmon_data(config):
    environment = config.getoption("environment_expression") or eval_environment(
        config.getini("environment_expression")
    )
    packages = ", ".join(sorted(str(p) for p in pkg_resources.working_set))

    url = config.getini("testmon_url")
    api_key = config.getini("testmon_api_key")
    rpc_proxy = None

    if config.testmon_config.tmnet:
        rpc_proxy = getattr(config, "tmnet", None)

        if not url:
            url = "https://tmnet-4.fly.dev/"

        if not rpc_proxy:
            print(f"using remote server at {url}")
            project_name = api_key.rsplit("_")[0]
            project_url = url + project_name
            rpc_proxy = xmlrpc.client.ServerProxy(project_url, allow_none=True)

    testmon_data = TestmonData(
        config.rootdir.strpath,
        environment=environment,
        system_packages=packages,
        remote_db=rpc_proxy,
    )
    testmon_data.determine_stable()
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
            init_testmon_data(config)
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
                else f"changed files: {changed_files_msg}, skipping collection of {len(stable_files)} files, "
            )
    if config.testmon_data.environment:
        message += f"environment: {environment}"
    return message


def pytest_unconfigure(config):
    if hasattr(config, "testmon_data"):
        config.testmon_data.close_connection()


def process_result(result):
    failed = any(r.outcome == "failed" for r in result.values())
    duration = sum(value.duration for value in result.values())
    return failed, duration


class TestmonCollect:
    def __init__(self, testmon, testmon_data, host="single", cov_plugin=None):
        self.testmon_data = testmon_data
        self.testmon = testmon
        self._host = host

        self.reports = defaultdict(lambda: {})
        self.raw_test_names = []
        self.cov_plugin = cov_plugin

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
                test_executions_fingerprints = nofili2fingerprints(
                    report.nodes_files_lines, self.testmon_data
                )
                test_outcomes = {
                    test_name: process_result(self.reports[test_name])
                    for test_name in test_executions_fingerprints
                }
                self.testmon_data.save_test_execution_file_fps(
                    test_executions_fingerprints, test_outcomes
                )

    def pytest_keyboard_interrupt(self, excinfo):
        if self._host == "single":
            nodes_files_lines = self.testmon.get_batch_coverage_data()

            test_executions_fingerprints = nofili2fingerprints(
                nodes_files_lines, self.testmon_data
            )
            fa_durs = {
                test_name: process_result(self.reports[test_name])
                for test_name in test_executions_fingerprints
            }
            self.testmon_data.save_test_execution_file_fps(
                test_executions_fingerprints, fa_durs
            )
            self.testmon.close()

    def pytest_sessionfinish(self, session):
        if self._host in ("single", "controller"):
            self.testmon_data.db.remove_unused_file_fps()
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
                items=(
                    [FakeItemFromTestmon(session.config)] * len(self.deselected_tests)
                )
            )
        else:
            sort_items_by_duration(deselected, self.testmon_data.avg_durations)
            items[:] = selected + deselected

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        if len(self.deselected_tests) and exitstatus == ExitCode.NO_TESTS_COLLECTED:
            session.exitstatus = ExitCode.OK


class FakeItemFromTestmon:
    def __init__(self, config):
        self.config = config
