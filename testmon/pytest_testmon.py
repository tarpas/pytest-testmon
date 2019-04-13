"""
Main module of testmon pytest plugin.
"""
from __future__ import division
import os
from collections import defaultdict

import pytest

from testmon.testmon_core import Testmon, eval_variant, TestmonData
from _pytest import runner


def serialize_report(rep):
    import py
    d = rep.__dict__.copy()
    if hasattr(rep.longrepr, 'toterminal'):
        d['longrepr'] = str(rep.longrepr)
    else:
        d['longrepr'] = rep.longrepr
    for name in d:
        if isinstance(d[name], py.path.local):
            d[name] = str(d[name])
        elif name == "result":
            d[name] = None  # for now
    return d


def pytest_addoption(parser):
    group = parser.getgroup('testmon')

    group.addoption(
        '--testmon',
        action='store_true',
        dest='testmon',
        help="Select only tests affected by recent changes.",
    )

    group.addoption(
        '--tlf',
        action='store_true',
        dest='tlf',
        help="Re-execute last failures regardless of source change status",
    )

    group.addoption(
        '--by-test-count',
        action='store_true',
        dest='by_test_count',
        help="Print modules by test count (from lowest to highest count)"
    )

    group.addoption(
        '--testmon-off',
        action='store_true',
        dest='testmon_off',
        help="Turn off (even if activated from config by default)"
    )

    group.addoption(
        '--testmon-singleprocess',
        action='store_true',
        dest='testmon_singleprocess',
        help="Don't track subprocesses"
    )

    group.addoption(
        '--testmon-readonly',
        action='store_true',
        dest='testmon_readonly',
        help="Don't track, just deselect based on existing .testmondata"
    )

    group.addoption(
        '--project-directory',
        action='append',
        dest='project_directory',
        help="Top level directory of project",
        default=None
    )

    parser.addini("run_variant_expression", "run variant expression",
                  default='')


def testmon_options(config):
    result = []
    for label in ['testmon', 'testmon_singleprocess',
                  'testmon_off', 'testmon_readonly']:
        if config.getoption(label):
            result.append(label.replace('testmon_', ''))
    return result


def init_testmon_data(config, read_source=True):
    if not hasattr(config, 'testmon_data'):
        variant = eval_variant(config.getini('run_variant_expression'))
        config.project_dirs = config.getoption('project_directory') or [config.rootdir.strpath]
        testmon_data = TestmonData(config.project_dirs[0],
                                   variant=variant)
        testmon_data.read_data()
        if read_source:
            testmon_data.read_source()
        config.testmon_data = testmon_data


def pytest_cmdline_main(config):
    if config.option.by_test_count:
        init_testmon_data(config, read_source=False)
        from _pytest.main import wrap_session

        return wrap_session(config, by_test_count)


def is_active(config):
    return (config.getoption('testmon') or config.getoption('testmon_readonly')) and not (
        config.getoption("testmon_off"))


def pytest_configure(config):
    if is_active(config):
        config.option.continue_on_collection_errors = True
        init_testmon_data(config)
        config.pluginmanager.register(TestmonDeselect(config, config.testmon_data),
                                      "TestmonDeselect")


def pytest_unconfigure(config):
    if hasattr(config, 'testmon_data'):
        config.testmon_data.close_connection()


def by_test_count(config, session):
    file_data = config.testmon_data.file_data()
    for filename, nodeids in sorted(file_data.items(), key=lambda ite: len(ite[1]), reverse=True):
        print("%s: %s" % (len(nodeids), os.path.relpath(filename)))


class TestmonDeselect(object):
    def __init__(self, config, testmon_data):
        self.testmon_data = testmon_data
        self.testmon = Testmon(config.project_dirs, testmon_labels=testmon_options(config))

        self.collection_ignored = set()
        self.testmon_save = True
        self.config = config
        self.reports = defaultdict(lambda: {})
        self.selected, self.deselected = [], set()
        self.file_data = self.testmon_data.file_data()
        self.f_to_ignore = self.testmon_data.stable_files
        if self.config.getoption('tlf'):
            self.f_to_ignore -= self.testmon_data.f_last_failed

    def test_should_run(self, nodeid):
        if self.config.getoption('tlf'):
            if nodeid in self.testmon_data.fail_reports:
                return True
        if nodeid in self.testmon_data.stable_nodeids:
            return False
        else:
            return True

    def report_if_failed(self, nodeid):
        node_reports = self.testmon_data.fail_reports.get(nodeid, {})
        for phase in ('setup', 'call', 'teardown'):
            if phase in node_reports:
                test_report = runner.TestReport(**node_reports[phase])
                self.config.hook.pytest_runtest_logreport(report=test_report)

    def pytest_report_header(self, config):
        changed_files = ",".join(self.testmon_data.source_tree.changed_files)
        if changed_files == '' or len(changed_files) > 100:
            changed_files = len(self.testmon_data.source_tree.changed_files)
        active_message = "testmon={}, changed files: {}, skipping collection of {} files".format(
            config.getoption('testmon'),
            changed_files, len(self.f_to_ignore))
        if self.testmon_data.variant:
            return active_message + ", run variant: {}".format(self.testmon_data.variant)
        else:
            return active_message + "."

    def pytest_ignore_collect(self, path, config):
        strpath = os.path.relpath(path.strpath, config.rootdir.strpath)
        if strpath in (self.f_to_ignore):
            self.collection_ignored.update(self.testmon_data.f_tests[strpath])
            return True

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(self, session, config, items):
        self.testmon_data.collect_garbage(retain=self.collection_ignored.union(set([item.nodeid for item in items])))

        yield

        for item in items:
            assert item.nodeid not in self.collection_ignored, (item.nodeid, self.collection_ignored)

        for item in items:
            if self.test_should_run(item.nodeid):
                self.selected.append(item)
            else:
                self.deselected.add(item.nodeid)
        items[:] = self.selected

        session.config.hook.pytest_deselected(
            items=([self.FakeItemFromTestmon(session.config)] *
                   len(self.collection_ignored.union(self.deselected))))

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtestloop(self, session):
        yield

        # Report known failures in the end.
        ignored_deselected = self.collection_ignored.union(self.deselected)
        for nodeid in ignored_deselected:
            self.report_if_failed(nodeid)

    @pytest.mark.hookwrapper
    def pytest_runtest_protocol(self, item, nextitem):
        if self.config.getoption('testmon_readonly'):
            yield
        else:
            self.testmon.start()
            result = yield
            if result.excinfo and issubclass(result.excinfo[0], (
                    KeyboardInterrupt, pytest.exit.Exception)):
                self.testmon.stop()
            else:
                self.testmon.stop_and_save(self.testmon_data, item.config.rootdir.strpath, item.nodeid,
                                           self.reports[item.nodeid])

    def pytest_runtest_logreport(self, report):
        assert report.when not in self.reports, \
            "{} {} {}".format(report.nodeid, report.when, self.reports)
        self.reports[report.nodeid][report.when] = serialize_report(report)

    class FakeItemFromTestmon(object):
        def __init__(self, config):
            self.config = config

    def pytest_internalerror(self, excrepr, excinfo):
        self.testmon_save = False

    def pytest_keyboard_interrupt(self, excinfo):
        self.testmon_save = False

    def pytest_sessionfinish(self, session):
        if self.testmon_save and not self.config.getoption('collectonly') and not self.config.getoption('testmon_readonly'):
            self.testmon_data.write_data()
        self.testmon.close()
