"""
Main module of testmon pytest plugin.
"""
from __future__ import division
import os
import pytest

from testmon.testmon_core import Testmon, eval_variant, TestmonData


def pytest_addoption(parser):
    group = parser.getgroup('testmon')

    group.addoption(
        '--testmon',
        action='store_true',
        dest='testmon',
        help="Select only tests affected by recent changes.",
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


def init_testmon_data(config):
    if not hasattr(config, 'testmon_data'):
        variant = eval_variant(config.getini('run_variant_expression'))
        config.project_dirs = config.getoption('project_directory') or [config.rootdir.strpath]
        testmon_data = TestmonData(config.project_dirs[0],
                                   variant=variant)
        affected = testmon_data.read_fs()
        config.testmon_data = testmon_data
        return affected

def pytest_cmdline_main(config):
    init_testmon_data(config)
    if config.option.by_test_count:
        from _pytest.main import wrap_session

        return wrap_session(config, by_test_count)


def is_active(config):
    return config.getoption('testmon') and not (config.getoption("testmon_off"))


def pytest_configure(config):
    if is_active(config):
        config.pluginmanager.register(TestmonDeselect(config, config.testmon_data),
                                      "TestmonDeselect")


def by_test_count(config, session):
    test_counts = config.testmon_data.modules_test_counts()
    for k in sorted(test_counts.items(), key=lambda ite: ite[1]):
        print("%s: %s" % (k[1], os.path.relpath(k[0])))


class TestmonDeselect(object):
    def __init__(self, config, testmon_data):
        self.testmon_data = testmon_data
        self.testmon = Testmon(config.project_dirs, testmon_labels=testmon_options(config) )
        self.testmon_save = True
        self.config = config
        self.lastfailed = self.testmon_data.lastfailed

    def pytest_report_header(self, config):
        changed_files = ",".join([os.path.relpath(path, config.rootdir.strpath)
                                  for path
                                  in self.testmon_data.modules_cache])
        if changed_files=='' or len(changed_files)>100:
            changed_files = len(self.testmon_data.modules_cache)
        active_message = "testmon={}, changed files: {}, skipping collection of {} items".format(config.getoption('testmon'),
                                                              changed_files, sum(self.testmon_data.unaffected_paths.values()))
        if self.testmon_data.variant:
            return active_message + ", run variant: {}".format(self.testmon_data.variant)
        else:
            return active_message + "."

    def pytest_collection_modifyitems(self, session, config, items):
        selected, deselected = [], []
        self.testmon_data.collect_garbage(allnodeids=[item.nodeid for item in items])
        for item in items:
            if item.nodeid in self.lastfailed or self.testmon_data.test_should_run(item.nodeid):
                selected.append(item)
            else:
                deselected.append(item)
        items[:] = selected
        if deselected:
            config.hook.pytest_deselected(items=deselected)

    @pytest.mark.hookwrapper
    def pytest_runtest_protocol(self, item, nextitem):
        if self.config.getoption('testmon') == u'readonly':
            yield

        self.testmon.start()
        result = yield
        # NOTE: pytest-watch also sends KeyboardInterrupt when changes are
        # detected.  This should still save the collected data up until then.
        if result.excinfo and issubclass(result.excinfo[0], KeyboardInterrupt):
            self.testmon.stop()
        else:
            self.testmon.stop_and_save(self.testmon_data, item.config.rootdir.strpath, item.nodeid)

    def pytest_runtest_logreport(self, report):
        if report.failed and "xfail" not in report.keywords:
            if report.nodeid not in self.lastfailed:
                self.lastfailed.append(report.nodeid)
        elif not report.failed:
            if report.when == "call":
                try:
                    if report.nodeid in self.lastfailed:
                        self.lastfailed.remove(report.nodeid)
                except KeyError:
                    pass

    class FakeItemFromTestmon(object):
        def __init__(self, config):
            self.config = config

    def pytest_ignore_collect(self, path, config):
        strpath = path.strpath
        if strpath in self.testmon_data.unaffected_paths:
            config.hook.pytest_deselected(
                items=([self.FakeItemFromTestmon(config)] *
                     self.testmon_data.unaffected_paths[strpath]))
            return True

    def pytest_internalerror(self, excrepr, excinfo):
        self.testmon_save = False

    def pytest_sessionfinish(self, session):
        if self.testmon_save:
            self.testmon_data.write_data()
        self.testmon.close()

    def pytest_terminal_summary(self, terminalreporter, exitstatus=None):
        if (not self.testmon_save and
                terminalreporter.config.getvalue('verbose')):
            terminalreporter.line('testmon: not saving data')
