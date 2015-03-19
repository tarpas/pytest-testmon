"""
Main module of testmon pytest plugin.
"""
from __future__ import division

import fnmatch
import os
import sys

import coverage
from testmon.testmon_models import DepGraph

TESTS_CACHE_KEY = '/Testmon/nodeid'
MTIMES_CACHE_KEY = '/Testmon/mtimes'


def get_files_recursively(path, pattern):
    """
    Returns filenames in a directory path recursively matching a pattern
    """
    for root, dirnames, filenames in os.walk(path):
        for filename in fnmatch.filter(filenames, pattern):
            yield os.path.join(root, filename)


def track_changed_files(mtimes, project_directory):
    """
    Reduces the list of files to only include those
    that have changed since the last run.
    """
    filenames = get_files_recursively(project_directory, "*.py")
    mtimes_to_update = mtimes
    res = []

    for py_file in filenames:
        current_mtime = os.path.getmtime(py_file)

        if mtimes_to_update.get(py_file) != current_mtime:
            res.append(py_file)
            mtimes_to_update[py_file] = current_mtime
    return res, mtimes_to_update


def _get_python_lib_paths():
    res = [sys.prefix]
    for attr in ['exec_prefix', 'real_prefix', 'base_prefix']:
        if getattr(sys, attr, sys.prefix) not in res:
            res.append(getattr(sys, attr))
    return [os.path.join(d, "*") for d in res]


def track_execute(callable_to_track, cov):
    cov.erase()
    cov.start()
    result = callable_to_track()
    cov.stop()
    cov.save()
    return result, cov.data


def data_to_dependencies(data):
    # for filename, value in data.lines.items():
    #     logging.info(filename)
    #     for k in value:
    #         logging.info(str(k))
    return data.measured_files()


def pytest_addoption(parser):
    parser.addoption(
        '--project-directory',
        action='store',
        dest='project_directory',
        help="Top level directory of project",
        default=os.getcwd()
    )

    parser.addoption(
        '--by-test-count',
        action='store_true',
        dest='by_test_count',
        help="(testmon) Print modules by test count (from lowest to highest count)"
    )
    parser.addoption(
        '--testmon',
        action='store_true',
        dest='testmon',
        help="(testmon) Select only tests affected by recent changes."
    )


def pytest_cmdline_main(config):
    if config.option.by_test_count:
        from _pytest.main import wrap_session
        return wrap_session(config, by_test_count)


def pytest_configure(config):
    node_data = config.cache.get(TESTS_CACHE_KEY, {})
    mtimes = config.cache.get(MTIMES_CACHE_KEY, {})

    changed_py_files, new_mtimes = track_changed_files(mtimes,
                                                       config.getoption('project_directory'))

    depgraph = DepGraph(node_data)

    if config.getoption('testmon'):
        config.pluginmanager.register(TestmonDeselect(config,
                                                      depgraph,
                                                      changed_py_files,
                                                      new_mtimes), "TestmonDeselect")


def pytest_report_header(config):
    from datetime import datetime as dt
    delta = dt(2015, 3, 20, 6, 59) - dt.utcnow()
    if delta.days >= 0:
        igg = "Crowdfunding more features like per-method granularity, quickest first, failed first:  http://igg.me/at/testmon closes in" \
            " {} days {} hours".format(delta.days,
                                       delta.seconds // 3600)
    else:
        igg = ""
    return igg


def by_test_count(config, session):
    test_counts = DepGraph(config.cache.get(TESTS_CACHE_KEY, {}),
                           ).modules_test_counts()
    for k in sorted(test_counts.items(), key=lambda ite: ite[1]):
        print("%s: %s" % (k[1], os.path.relpath(k[0])))


class TestmonDeselect(object):

    def __init__(self, config, depgraph, changed_files, new_mtimes):
        self.testmon_save = True
        self.depgraph = depgraph
        self.changed_files = changed_files
        self.new_mtimes = new_mtimes
        self.cov = coverage.coverage(cover_pylib=False,
                                     omit=_get_python_lib_paths())
        self.cov.use_cache(False)

    def pytest_report_header(self, config):
        if len(self.changed_files) > 10:
            return "changed_files: too many to list"
        else:
            pdir = config.getoption('project_directory')
            return "changed files: {}".format([os.path.relpath(p, pdir)
                                              for p in self.changed_files],
                                              )

    def pytest_collection_modifyitems(self, session, config, items):
        selected, deselected = [], []
        for item in items:
            if self.depgraph.test_should_run(item.nodeid, self.changed_files):
                selected.append(item)
            else:
                deselected.append(item)
        items[:] = selected
        if deselected:
            config.hook.pytest_deselected(items=deselected)

    def pytest_runtest_call(self, __multicall__, item):
        result, data = track_execute(__multicall__.execute, self.cov)
        dependencies = data_to_dependencies(data)

        self.depgraph.set_dependencies(item.nodeid, dependencies)
        if not dependencies:
            print("Warning: tracing of %s failed!" % item.nodeid)

        return result

    def pytest_internalerror(self, excrepr, excinfo):
        self.testmon_save = False

    def pytest_keyboard_interrupt(self, excinfo):
        self.testmon_save = False

    def pytest_sessionfinish(self, session):
        if self.testmon_save:
            config = session.config
            config.cache.set(MTIMES_CACHE_KEY, self.new_mtimes)
            config.cache.set(TESTS_CACHE_KEY, self.depgraph.node_data)
