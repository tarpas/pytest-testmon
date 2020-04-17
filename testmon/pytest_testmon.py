import os
from collections import defaultdict

import pytest
from _pytest.python import Function
from testmon.testmon_core import (
    Testmon,
    eval_environment,
    TestmonData,
    home_file,
    TestmonConfig,
    TestmonException,
)
from _pytest import runner


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
        help="""
        Turn off (even if activated from config by default). Forced if neither read nor write is possible (debugger
        plus test selector)
        """,
    )

    group.addoption(
        "--testmon-env",
        action="store",
        type=str,
        dest="environment_expression",
        default="",
        help="""
        This allows you to have separate coverage data within one .testmondata file, e.g. when using the same source
        code serving different endpoints or django settings.
        """,
    )

    group.addoption(
        "--testmon-nosort",
        action="store_true",
        dest="testmon_nosort",
        help="""
        Testmon sorts tests by execution time normally, this disables that feature. Useful
        when number of tests is large (>10000).
        """,
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
        environment = eval_environment(config.getini("environment_expression"))
        testmon_data = TestmonData(config.rootdir.strpath, environment=environment)
        if read_source:
            testmon_data.determine_stable()
        config.testmon_data = testmon_data


def pytest_configure(config):
    coverage_stack = None

    plugin = None

    testmon_config = TestmonConfig()
    message, should_collect, should_select = testmon_config.header_collect_select(
        config, coverage_stack, cov_plugin=plugin
    )
    config.testmon_config = (message, should_collect, should_select)
    if should_select or should_collect:
        config.option.continue_on_collection_errors = True

        try:
            init_testmon_data(config)

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
                            cov_plugin=plugin,
                        ),
                        config.testmon_data,
                    ),
                    "TestmonCollect",
                )
        except TestmonException as e:
            pytest.exit(str(e))


def pytest_report_header(config):
    message, should_collect, should_select = config.testmon_config
    if not should_collect and not should_select:
        return message

    environment = "environment: {}, ".format(config.testmon_data.environment) if config.testmon_data.environment else ""
    if not should_select:
        return message + environment

    changed_files = "\n".join(config.testmon_data.unstable_files)
    if not changed_files:
        changed_files = "0"
    elif len(changed_files) > 100 and config.getoption("verbose") < 1:
        changed_files = len(config.testmon_data.unstable_files)
    else:
        changed_files = "{} files\n{}\n".format(
            len(config.testmon_data.unstable_files),
            changed_files
        )
    new_db = "new DB, " if changed_files == 0 and len(config.testmon_data.stable_files) == 0 else ""
    return "{message}{environment}{new_db}skipping collection of {stable_files} files, changed files: {changed_files}".format(
        message=message,
        environment=environment,
        new_db=new_db,
        stable_files=len(config.testmon_data.stable_files),
        changed_files=changed_files,
    )

    return message


def pytest_unconfigure(config):
    if hasattr(config, "testmon_data"):
        config.testmon_data.close_connection()


def sort_items_by_duration(items, testmon_data):
    durations = defaultdict(lambda: {"node_count": 0, "duration": 0})
    for item in items:
        item.duration = 0
        if item.nodeid in testmon_data.all_nodes:
            report = testmon_data.get_report(item.nodeid)
            if report:
                item.duration = sum(
                    [report["duration"] for report in report.values()]
                )
        item.module_name = item.location[0]
        item_hierarchy = item.location[2].split(".")
        item.node_name = item_hierarchy[-1]
        item.class_name = item_hierarchy[0]

        durations[item.class_name]["node_count"] += 1
        durations[item.class_name]["duration"] += item.duration
        durations[item.module_name]["node_count"] += 1
        durations[item.module_name]["duration"] += item.duration

    for key, stats in durations.items():
        durations[key]["avg_duration"] = stats["duration"] / stats["node_count"]

    items.sort(key=lambda item: item.duration)
    items.sort(key=lambda item: durations[item.class_name]["avg_duration"])
    items.sort(key=lambda item: durations[item.module_name]["avg_duration"])


class TestmonCollect(object):
    def __init__(self, testmon, testmon_data):
        self.testmon_data = testmon_data
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
        if should_select or should_collect:
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
                    item.config.rootdir.strpath,
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
        self.testmon_data.remove_unused_fingerprints()
        self.testmon.close()


class TestmonSelect:
    def __init__(self, config, testmon_data):
        self.testmon_data = testmon_data
        self.config = config

        self.deselected_files = testmon_data.stable_files
        self.deselected_nodes = testmon_data.stable_nodeids
        self.failing_nodes = testmon_data.failing_nodes

    def add_failing_reports_from_db(self, failing_stable_nodes):
        """If the nodeid is failed but stable, add it's report instead of running it."""
        for nodeid in failing_stable_nodes:
            node_report = self.testmon_data.get_report(nodeid)
            if not node_report:
                continue
            for phase in ("setup", "call", "teardown"):
                if phase in node_report:
                    test_report = runner.TestReport(**node_reports[phase])
                    self.config.hook.pytest_runtest_logreport(report=test_report)

    def pytest_ignore_collect(self, path, config):
        strpath = os.path.relpath(path.strpath, config.rootdir.strpath)
        if strpath in self.deselected_files:
            return True

    @pytest.mark.trylast
    def pytest_collection_modifyitems(self, session, config, items):
        selected = []
        for item in items:
            if item.nodeid in self.failing_nodes or item.nodeid not in self.deselected_nodes:
                selected.append(item)

        items[:] = selected

        if self.testmon_data.all_nodes and not config.getoption("testmon_nosort"):
            sort_items_by_duration(items, self.testmon_data)

        session.config.hook.pytest_deselected(
            items=([FakeItemFromTestmon(session.config)] * len(self.deselected_nodes))
        )

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtestloop(self, session):
        yield
        self.add_failing_reports_from_db(
            self.deselected_nodes.intersection(self.failing_nodes)
        )


class FakeItemFromTestmon(object):
    def __init__(self, config):
        self.config = config
