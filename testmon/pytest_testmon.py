import os
from collections import defaultdict

import pytest
from _pytest.python import Function

from testmon.testmon_core import (
    Testmon,
    eval_environment,
    TestmonData,
    home_file,
    TestmonException,
    get_node_class_name,
    get_node_module_name,
    LIBRARIES_KEY,
)

from testmon import configure as configure

from _pytest import runner
import pkg_resources


def serialize_report(rep):
    import py

    d = rep.__dict__.copy()
    if hasattr(rep.longrepr, "toterminal"):
        d["longrepr"] = str(rep.longrepr)
    else:
        d["longrepr"] = rep.longrepr
    for name in d:
        if isinstance(d[name], py.path.local):
            d[name] = str(d[name])
        elif name == "result":
            d[name] = None
    return d


def pytest_addoption(parser):
    group = parser.getgroup("testmon")

    group.addoption(
        "--testmon",
        action="store_true",
        dest="testmon",
        help="Select tests affected by changes (based on previously collected data) and collect + write new data "
        "(.testmondata file). Either collection or selection might be deactivated (sometimes automatically). "
        "See below.",
    )

    group.addoption(
        "--testmon-nocollect",
        action="store_true",
        dest="testmon_nocollect",
        help="Run testmon but deactivate the collection and writing of testmon data. Forced if you run under debugger "
        "or coverage.",
    )

    group.addoption(
        "--testmon-noselect",
        action="store_true",
        dest="testmon_noselect",
        help="Run testmon but deactivate selection, so all tests selected by other means will be collected and "
        "executed. Forced if you use -k, -l, -lf, test_file.py::test_name (to be implemented)",
    )

    group.addoption(
        "--testmon-forceselect",
        action="store_true",
        dest="testmon_forceselect",
        help="Run testmon and select only tests affected by changes and satisfying pytest selectors at the same time.",
    )

    group.addoption(
        "--no-testmon",
        action="store_true",
        dest="no-testmon",
        help=(
            "Turn off (even if activated from config by default).\n"
            "Forced if neither read nor write is possible (debugger plus test selector)."
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

    parser.addini("environment_expression", "environment expression", default="")


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


def init_testmon_data(config, read_source=True):
    if not hasattr(config, "testmon_data"):
        environment = config.getoption("environment_expression") or eval_environment(
            config.getini("environment_expression")
        )
        libraries = ", ".join(sorted(str(p) for p in pkg_resources.working_set))
        testmon_data = TestmonData(
            config.rootdir.strpath, environment=environment, libraries=libraries
        )
        if read_source:
            testmon_data.determine_stable()
        config.testmon_data = testmon_data


def register_plugins(config, should_select, should_collect, cov_plugin):
    if should_select:
        config.pluginmanager.register(
            TestmonSelect(config, config.testmon_data), "TestmonSelect"
        )

    if should_collect:
        config.pluginmanager.register(
            TestmonCollect(
                Testmon(
                    config.rootdir.strpath,
                    testmon_labels=testmon_options(config),
                    cov_plugin=cov_plugin,
                ),
                config.testmon_data,
            ),
            "TestmonCollect",
        )


def pytest_configure(config):
    coverage_stack = None

    cov_plugin = None

    message, should_collect, should_select = configure.header_collect_select(
        config, coverage_stack, cov_plugin=cov_plugin
    )
    config.testmon_config = (message, should_collect, should_select)
    if should_select or should_collect:

        try:
            init_testmon_data(config)
            register_plugins(config, should_select, should_collect, cov_plugin)
        except TestmonException as e:
            pytest.exit(str(e))


def pytest_report_header(config):
    message, should_collect, should_select = config.testmon_config

    if should_collect or should_select:
        unstable_files = getattr(config.testmon_data, "unstable_files", set())
        stable_files = getattr(config.testmon_data, "stable_files", set()) - {
            LIBRARIES_KEY
        }
        environment = config.testmon_data.environment
        libraries_miss = getattr(config.testmon_data, "libraries_miss", None)

    if should_collect or should_select:

        message += changed_message(
            config,
            environment,
            libraries_miss,
            should_select,
            stable_files,
            unstable_files,
        )

    return message


def changed_message(
    config,
    environment,
    libraries_miss,
    should_select,
    stable_files,
    unstable_files,
):
    message = ""
    if should_select:
        changed_files_msg = ", ".join(unstable_files)
        if changed_files_msg == "" or len(changed_files_msg) > 100:
            changed_files_msg = str(len(config.testmon_data.unstable_files))

        if changed_files_msg == "0" and len(stable_files) == 0:
            message += "new DB, "
        else:
            message += "changed files{}: {}, skipping collection of {} files, ".format(
                "(libraries upgrade/install)" if libraries_miss else "",
                changed_files_msg,
                len(stable_files),
            )
    if config.testmon_data.environment:
        message += "environment: {}".format(environment)
    return message


def pytest_unconfigure(config):
    if hasattr(config, "testmon_data"):
        config.testmon_data.close_connection()


class TestmonCollect(object):
    def __init__(self, testmon, testmon_data):
        self.testmon_data: TestmonData = testmon_data
        self.testmon = testmon

        self.reports = defaultdict(lambda: {})
        self.raw_nodeids = []

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_pycollect_makeitem(self, collector, name, obj):
        makeitem_result = yield
        items = makeitem_result.get_result() or []
        try:
            self.raw_nodeids.extend(
                [item.nodeid for item in items if isinstance(item, pytest.Item)]
            )
        except TypeError:
            pass

    def pytest_collection_modifyitems(self, session, config, items):
        _, should_collect, should_select = config.testmon_config
        if should_collect and not session.testsfailed:
            config.testmon_data.sync_db_fs_nodes(retain=set(self.raw_nodeids))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        if isinstance(item, Function) and item.config.testmon_config[1]:
            self.testmon.start()
            result = yield
            if result.excinfo and issubclass(result.excinfo[0], BaseException):
                self.testmon.stop()
            else:
                self.testmon.stop_and_save(
                    self.testmon_data,
                    item.nodeid,
                    self.reports[item.nodeid],
                )
        else:
            yield

    def pytest_runtest_logreport(self, report):
        assert report.when not in self.reports, "{} {} {}".format(
            report.nodeid, report.when, self.reports
        )
        self.reports[report.nodeid][report.when] = serialize_report(report)

    def pytest_sessionfinish(self, session):
        self.testmon_data.db.remove_unused_fingerprints()
        self.testmon.close()


def did_fail(reports):
    return reports["failed"]


def get_failing(all_nodes):
    failing_files, failing_nodes = set(), {}
    for nodeid, result in all_nodes.items():
        if did_fail(all_nodes[nodeid]):
            failing_files.add(home_file(nodeid))
            failing_nodes[nodeid] = result
    return failing_files, failing_nodes


class TestmonSelect:
    def __init__(self, config, testmon_data):
        self.testmon_data: TestmonData = testmon_data
        self.config = config

        failing_files, failing_nodes = get_failing(testmon_data.all_nodes)

        self.deselected_files = [
            file for file in testmon_data.stable_files if file not in failing_files
        ]
        self.deselected_nodes = [
            node for node in testmon_data.stable_nodeids if node not in failing_nodes
        ]

    def sort_items_by_duration(self, items) -> None:
        def duration_or_zero(key) -> float:
            try:
                return avg_durations[key]
            except KeyError:
                return 0

        avg_durations = self.testmon_data.nodes_classes_modules_avg_durations

        items.sort(key=lambda item: duration_or_zero(item.nodeid))
        items.sort(key=lambda item: duration_or_zero(get_node_class_name(item.nodeid)))
        items.sort(key=lambda item: duration_or_zero(get_node_module_name(item.nodeid)))

    def pytest_ignore_collect(self, path, config):
        strpath = os.path.relpath(path.strpath, config.rootdir.strpath)
        if strpath in self.deselected_files:
            return True

    @pytest.mark.trylast
    def pytest_collection_modifyitems(self, session, config, items):
        for item in items:
            assert item.nodeid not in self.deselected_files, (
                item.nodeid,
                self.deselected_files,
            )

        selected = []
        for item in items:
            if item.nodeid not in self.deselected_nodes:
                selected.append(item)
        items[:] = selected

        if self.testmon_data.all_nodes:
            self.sort_items_by_duration(items)

        session.config.hook.pytest_deselected(
            items=([FakeItemFromTestmon(session.config)] * len(self.deselected_nodes))
        )


class FakeItemFromTestmon(object):
    def __init__(self, config):
        self.config = config
