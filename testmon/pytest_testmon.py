"""
Main module of testmon pytest plugin.
"""
from __future__ import division
import os
import sys

from testmon.testmon_core import Testmon
import json
import gzip


TESTS_CACHE_KEY = '/Testmon/nodedata-'
MTIMES_CACHE_KEY = '/Testmon/mtimes-'


def pytest_addoption(parser):
    parser.addoption(
        '--project-directory',
        action='append',
        dest='project_directory',
        help="Top level directory of project",
        default=[os.getcwd()]
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
    parser.addini("run_variants", "run variatns",
                  type="linelist", default=[])


def pytest_cmdline_main(config):
    if config.option.by_test_count:
        from _pytest.main import wrap_session

        return wrap_session(config, by_test_count)


def read_data(variant):
    try:
        with gzip.GzipFile(".testmondata", "r") as f:
            return json.loads(f.read().decode('UTF-8')).get(variant, ({}, {}))
    except IOError:
        return {}, {}


def pytest_configure(config):
    if config.getoption('testmon'):
        variant = get_variant(config)

        mtimes, node_data = read_data(variant)

        testmon = Testmon(node_data,
                          config.getoption('project_directory'),
                          variant)
        testmon.read_fs(mtimes)

        config.pluginmanager.register(TestmonDeselect(testmon, config),
                                      "TestmonDeselect")


def get_variant(config):
    eval_locals = {'os': os, 'sys': sys}

    eval_values = []
    for var in config.getini('run_variants'):
        try:
            eval_values.append(eval(var, {}, eval_locals))
        except Exception as e:
            eval_values.append(repr(e))

    return ":".join([str(value) for value in eval_values if value])


def pytest_report_header(config):
    if get_variant(config):
        return "Run variant: {}".format(get_variant(config))


def by_test_count(config, session):
    mtimes, nodes = read_data(get_variant(config))
    test_counts = Testmon(nodes,
                          [],
                          ).modules_test_counts()
    for k in sorted(test_counts.items(), key=lambda ite: ite[1]):
        print("%s: %s" % (k[1], os.path.relpath(k[0])))


class TestmonDeselect(object):

    def __init__(self, testmon, config):
        self.testmon_save = True
        self.testmon = testmon
        self.lastfailed = config.cache.get("cache/lastfailed", set())

    def pytest_report_header(self, config):
        # TODO changed method names?
        # That would require
        pass

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
        result = self.testmon.track_execute(__multicall__.execute, item.nodeid)
        return result

    def pytest_internalerror(self, excrepr, excinfo):
        self.testmon_save = False

    def pytest_keyboard_interrupt(self, excinfo):
        self.testmon_save = False

    def pytest_sessionfinish(self, session):
        if self.testmon_save:
            config = session.config
            with gzip.GzipFile(".testmondata", "w", 1) as f:
                f.write(json.dumps({self.testmon.variant:
                               [self.testmon.mtimes,
                                self.testmon.node_data,]}).encode('UTF-8'))
