"""
Main module of testmon pytest plugin.
"""
from __future__ import division
import os

from testmon.testmon_core import Testmon, eval_variants

TESTS_CACHE_KEY = '/Testmon/nodedata-'
MTIMES_CACHE_KEY = '/Testmon/mtimes-'


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
        '--recollect',
        action='store_true',
        dest='recollect',
        help="Recollect new tests (and new test files)"
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

    parser.addini("run_variants", "run variatns",
                  type="linelist", default=[])


def print_nonrun(config, session):
    print("Testmon: not running anything because no tracked files changed. To see tracked files use --by-test-count, "
        "to collect new tests and test_files use --testmon --recollect\n"
          "%s deselected" % len(config.testmon.node_data))


def testmon_options(config):
    result = []
    for label in ['testmon', 'testmon_singleprocess',
                  'recollect', 'testmon_off', 'testmon_readonly']:
        if config.getoption(label):
            result.append(label.replace('testmon_', ''))
    return result


def init_testmon(config):
    if not hasattr(config, 'testmon'):
        variant = eval_variants(config.getini('run_variants'))
        project_dirs = config.getoption('project_directory') or [config.rootdir.strpath]
        testmon = Testmon(project_dirs,
                          testmon_options(config),
                          variant=variant)
        testmon.read_fs()
        config.testmon = testmon
        return testmon
    else:
        return config.testmon

def pytest_cmdline_main(config):
    if config.option.by_test_count:
        from _pytest.main import wrap_session

        return wrap_session(config, by_test_count)
    elif config.option.testmon and \
            not config.option.recollect and \
            os.path.exists(os.path.join(config.rootdir.strpath, '.testmondata')):
        config.testmon = init_testmon(config)

        if len(config.testmon.node_data) > 0 and (
                        len(config.testmon.affected) == 0 and len(config.testmon.lastfailed) == 0):
            from _pytest.main import wrap_session

            return wrap_session(config, print_nonrun)


def is_active(config):
    return config.getoption('testmon') and not (config.getoption("testmon_off"))


def pytest_configure(config):
    if is_active(config):
        config.pluginmanager.register(TestmonDeselect(config),
                                      "TestmonDeselect")


def by_test_count(config, session):
    testmon = init_testmon(config)
    test_counts = testmon.modules_test_counts()
    for k in sorted(test_counts.items(), key=lambda ite: ite[1]):
        print("%s: %s" % (k[1], os.path.relpath(k[0])))


class TestmonDeselect(object):
    def __init__(self, config):
        self.testmon = init_testmon(config)
        self.testmon_save = True
        self.config = config
        self.lastfailed = self.testmon.lastfailed

    def pytest_report_header(self, config):
        changed_files = ",".join([os.path.relpath(path, config.rootdir.strpath)
                                  for path
                                  in self.testmon.modules_cache])
        if changed_files=='' or len(changed_files)>100:
            changed_files = len(self.testmon.modules_cache)
        active_message = "testmon={}, changed files: {}".format(config.getoption('testmon'),
                                                              changed_files)
        if self.testmon.variant:
            return active_message + ", run variant: {}".format(self.testmon.variant)
        else:
            return active_message + "."

    def pytest_collection_modifyitems(self, session, config, items):
        selected, deselected = [], []
        for item in items:
            if item.nodeid in self.lastfailed or self.testmon.test_should_run(item.nodeid):
                selected.append(item)
            else:
                deselected.append(item)
        items[:] = selected
        if deselected:
            config.hook.pytest_deselected(items=deselected)

    def pytest_runtest_call(self, __multicall__, item):
        if self.config.getoption('testmon') == u'readonly':
            return __multicall__.execute()
        result = self.testmon.track_dependencies(__multicall__.execute, item.nodeid)
        return result

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

    def pytest_internalerror(self, excrepr, excinfo):
        self.testmon_save = False

    def pytest_keyboard_interrupt(self, excinfo):
        self.testmon_save = False

    def pytest_sessionfinish(self, session):
        if self.testmon_save:
            self.testmon.save()
        self.testmon.close()
