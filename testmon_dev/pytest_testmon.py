
"""
Main module of testmon pytest plugin.
"""
from __future__ import division
import os
from collections import defaultdict

import pytest

from testmon_dev.testmon_core import Testmon, eval_variant, TestmonData
from _pytest import runner

PLUGIN_NAME = 'testmon-dev'
TLF_OPTION = 'tlf'
OFF_OPTION = 'off'
SINGLE_PROCESS_OPTION = 'singleprocess'
READONLY_OPTION = 'readonly'
PROJECT_DIRECTORY_OPTION = 'project-directory'
PROJECT_DIRECTORY_OPTION_DEST = 'project_directory'


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
        '--{}'.format(PLUGIN_NAME),
        action='store_true',
        dest=PLUGIN_NAME,
        help="Select only tests affected by recent changes.",
    )

    group.addoption(
        '--{}-{}'.format(PLUGIN_NAME, TLF_OPTION),
        action='store_true',
        dest=TLF_OPTION,
        help="Re-execute last failures regardless of source change status",
    )

    group.addoption(
        '--{}-{}'.format(PLUGIN_NAME, OFF_OPTION),
        action='store_true',
        dest='{}_{}'.format(PLUGIN_NAME, OFF_OPTION),
        help="Turn off (even if activated from config by default)"
    )

    group.addoption(
        '--{}-{}'.format(PLUGIN_NAME, SINGLE_PROCESS_OPTION),
        action='store_true',
        dest='{}_{}'.format(PLUGIN_NAME, SINGLE_PROCESS_OPTION),
        help="Don't track subprocesses"
    )

    group.addoption(
        '--{}-{}'.format(PLUGIN_NAME, READONLY_OPTION),
        action='store_true',
        dest='{}_{}'.format(PLUGIN_NAME, READONLY_OPTION),
        help="Don't track, just deselect based on existing .testmondata"
    )

    group.addoption(
        '--{}-{}'.format(PLUGIN_NAME, PROJECT_DIRECTORY_OPTION),
        action='append',
        dest=PROJECT_DIRECTORY_OPTION_DEST,
        help="Top level directory of project",
        default=None
    )

    parser.addini("run_variant_expression", "run variant expression",
                  default='')


def testmon_options(config):
    result = []
    for label in [PLUGIN_NAME, '{}_{}'.format(PLUGIN_NAME, SINGLE_PROCESS_OPTION),
                  '{}_{}'.format(PLUGIN_NAME, OFF_OPTION), '{}_{}'.format(PLUGIN_NAME, READONLY_OPTION)]:
        if config.getoption(label):
            result.append(label.replace('{}_'.format(PLUGIN_NAME), ''))
    return result


def init_testmon_data(config, read_source=True):
    if not hasattr(config, 'testmon_data'):
        variant = eval_variant(config.getini('run_variant_expression'))
        config.project_dirs = config.getoption(PROJECT_DIRECTORY_OPTION_DEST) or [config.rootdir.strpath]
        testmon_data = TestmonData(config.project_dirs[0],
                                   variant=variant)
        testmon_data.read_data()
        if read_source:
            testmon_data.read_source()
        config.testmon_data = testmon_data


def is_active(config):
    return (config.getoption(PLUGIN_NAME) or config.getoption('{}_{}'.format(PLUGIN_NAME, READONLY_OPTION))) and not (
        config.getoption('{}_{}'.format(PLUGIN_NAME, OFF_OPTION)))


def pytest_configure(config):
    if is_active(config):
        config.option.continue_on_collection_errors = True
        init_testmon_data(config)
        config.pluginmanager.register(TestmonSelect(config, config.testmon_data),
                                      "TestmonSelect")
        config.pluginmanager.register(TestmonCollect(config, config.testmon_data),
                                      "TestmonCollect")


def pytest_unconfigure(config):
    if hasattr(config, 'testmon_data'):
        config.testmon_data.close_connection()


class TestmonCollect(object):
    def __init__(self, config, testmon_data):
        self.testmon_data = testmon_data
        self.testmon = Testmon(config.project_dirs, testmon_labels=testmon_options(config))

        self.testmon_save = True
        self.config = config
        self.reports = defaultdict(lambda: {})
        self.file_data = self.testmon_data.file_data()
        self.f_to_ignore = self.testmon_data.stable_files
        if self.config.getoption(TLF_OPTION):
            self.f_to_ignore -= self.testmon_data.f_last_failed


    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        if self.config.getoption('{}_{}'.format(PLUGIN_NAME, READONLY_OPTION)):
            yield
        else:
            self.testmon.start()
            result = yield
            if result.excinfo and issubclass(result.excinfo[0], BaseException):
                self.testmon.stop()
            else:
                self.testmon.stop_and_save(self.testmon_data, item.config.rootdir.strpath, item.nodeid,
                                           self.reports[item.nodeid])

    def pytest_runtest_logreport(self, report):
        assert report.when not in self.reports, \
            "{} {} {}".format(report.nodeid, report.when, self.reports)
        self.reports[report.nodeid][report.when] = serialize_report(report)

    def pytest_internalerror(self, excrepr, excinfo):
        self.testmon_save = False

    def pytest_keyboard_interrupt(self, excinfo):
        self.testmon_save = False

    def pytest_sessionfinish(self, session):
        if self.testmon_save and not self.config.getoption('collectonly') and not self.config.getoption('{}_{}'.format(PLUGIN_NAME, READONLY_OPTION)):
            self.testmon_data.write_common_data()
        self.testmon.close()


class TestmonSelect():
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
        if self.config.getoption(TLF_OPTION):
            self.f_to_ignore -= self.testmon_data.f_last_failed

    def test_should_run(self, nodeid):
        if self.config.getoption(TLF_OPTION):
            reports = self.testmon_data.reports.get(nodeid)
            if reports:
                return self.did_fail(reports)
        if nodeid in self.testmon_data.stable_nodeids:
            return False
        else:
            return True

    def did_fail(self, reports):
        return bool([True for report in reports.values() if report.get('outcome') == u'failed'])

    def report_from_db(self, nodeid):
        node_reports = self.testmon_data.reports.get(nodeid, {})
        if self.did_fail(node_reports):
            for phase in ('setup', 'call', 'teardown'):
                if phase in node_reports:
                    test_report = runner.TestReport(**node_reports[phase])
                    self.config.hook.pytest_runtest_logreport(report=test_report)

    def pytest_report_header(self, config):
        changed_files = ",".join(self.testmon_data.source_tree.changed_files)
        if changed_files == '' or len(changed_files) > 100:
            changed_files = len(self.testmon_data.source_tree.changed_files)
        active_message = "testmon={}, changed files: {}, skipping collection of {} files".format(
            config.getoption(PLUGIN_NAME),
            changed_files, len(self.testmon_data.stable_files))
        if self.testmon_data.variant:
            return active_message + ", run variant: {}".format(self.testmon_data.variant)
        else:
            return active_message + "."

    def pytest_ignore_collect(self, path, config):
        strpath = os.path.relpath(path.strpath, config.rootdir.strpath)
        if strpath in (self.f_to_ignore):
            self.collection_ignored.update(self.testmon_data.f_tests[strpath])
            return True

    def sort_items_by_duration(self, items):
        durations = defaultdict(lambda: {'node_count': 0, 'duration': 0})
        for item in items:
            item.duration = sum([report['duration'] for report in self.testmon_data.reports[item.nodeid].values()])
            item.module_name = item.location[0]
            item_hierarchy = item.location[2].split('.')
            item.node_name = item_hierarchy[-1]
            item.class_name = item_hierarchy[0]

            durations[item.class_name]['node_count'] += 1
            durations[item.class_name]['duration'] += item.duration
            durations[item.module_name]['node_count'] += 1
            durations[item.module_name]['duration'] += item.duration

        for key, stats in durations.items():
            durations[key]['avg_duration'] = stats['duration'] / stats['node_count']

        items.sort(key=lambda item: item.duration)
        items.sort(key=lambda item: durations[item.class_name]['avg_duration'])
        items.sort(key=lambda item: durations[item.module_name]['avg_duration'])


    @pytest.mark.trylast
    def pytest_collection_modifyitems(self, session, config, items):
        self.testmon_data.collect_garbage(retain=self.collection_ignored.union(set([item.nodeid for item in items])))

        for item in items:
            assert item.nodeid not in self.collection_ignored, (item.nodeid, self.collection_ignored)

        for item in items:
            if self.test_should_run(item.nodeid):
                self.selected.append(item)
            else:
                self.deselected.add(item.nodeid)
        items[:] = self.selected

        if self.testmon_data.reports:
            self.sort_items_by_duration(items)

        session.config.hook.pytest_deselected(
            items=([FakeItemFromTestmon(session.config)] *
                   len(self.collection_ignored.union(self.deselected))))

    def pytest_runtestloop(self, session):
        ignored_deselected = self.collection_ignored.union(self.deselected)
        for nodeid in ignored_deselected:
            self.report_from_db(nodeid)


class FakeItemFromTestmon(object):
    def __init__(self, config):
        self.config = config

class Item:
    def __init__(self, pytest_item):
        self.item = pytest_item

    @property
    def module_name(self):
        return self.item.location[0]

