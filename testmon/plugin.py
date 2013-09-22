from __future__ import division
import os
import time
import pdb
import trace
import sys
import hashlib
import fnmatch
import pytest

from collections import defaultdict

TESTS_CACHE_KEY = '/Testmon/nodeid'
MTIMES_CACHE_KEY = '/Testmon/mtimes'

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

class DepGraph(object):
    
    def __init__(self, config):
        self.cache = config.cache.get(TESTS_CACHE_KEY, {})

    def test_should_run(self, nodeid, changed_py_files):
        if (nodeid not in self.cache) or (self.cache[nodeid]['runs_modules'] is False):
            # not enough data, means test should run
            return True
        else:
            return set(self.cache[nodeid]['runs_modules']) & set(changed_py_files)

    def by_test_count(self):        
        tests_for_modules = defaultdict(lambda : 0)
        for test, value in self.cache.items():
            runs_modules = value['runs_modules']
            for rm in runs_modules: 
                tests_for_modules[rm] += 1
        return tests_for_modules

def pytest_cmdline_main(config):
    if config.option.by_test_count:
        from _pytest.main import wrap_session
        return wrap_session(config, by_test_count)

def pytest_configure(config):
    config.depgraph = DepGraph(config)
    config.changed_py_files, config.new_mtimes = track_changed_files(config,
                                           config.getoption('project_directory'))

def by_test_count(config, session):
    tests_for_modules = config.depgraph.by_test_count()
    for k in sorted(tests_for_modules.items(), key=lambda ite:ite[1]):
        print "%s: %s" % (k[1], os.path.relpath(k[0]))

def pytest_report_header(config):
    from datetime import datetime as dt
    delta = dt(2015, 03, 20, 6, 59) - dt.utcnow()
    if delta.days >= 0:
        igg = "http://igg.me/at/testmon closes in" \
        " {} days {} hours, please contribute.\n".format(delta.days, 
                                                         delta.seconds//3600)
    else:
        igg = ""    
    if len(config.changed_py_files) > 10:
         return "{}changed_files: too many to list".format(igg)
    else:
        pdir = config.getoption('project_directory')
        return "{}changed files: {}".format(igg,
                                            [os.path.relpath(p, pdir) 
                                             for p in config.changed_py_files],
                                            )
        
def get_files_recursively(path, pattern):
    """
    Returns filenames in a directory path recursively matching a pattern
    """
    for root, dirnames, filenames in os.walk(path):
        for filename in fnmatch.filter(filenames, pattern):
            yield os.path.join(root, filename)

def track_changed_files(config, project_directory):
    """
    Reduces the list of files to only include those
    that have changed since the last run.
    """
    filenames = get_files_recursively(project_directory, "*.py")
    cached_mtimes = config.cache.get(MTIMES_CACHE_KEY, {})
    res = []
    
    for py_file in filenames:
        current_mtime = os.path.getmtime(py_file)

        if cached_mtimes.get(py_file) != current_mtime:
            res.append(py_file)
            cached_mtimes[py_file] = current_mtime
    return res, cached_mtimes

def pytest_collection_modifyitems(session, config, items):
    if config.getoption('testmon'):
        selected, deselected = [], []
        for item in items:
            if config.depgraph.test_should_run(item.nodeid, config.changed_py_files):
                selected.append(item)
            else:
                deselected.append(item)
        items[:] = selected
        if deselected: config.hook.pytest_deselected(items=deselected)
    
        #TODO "clearing changed files" - where does this belong? 
        config.cache.set(MTIMES_CACHE_KEY, config.new_mtimes)

def _get_python_lib_paths():
    res = [sys.prefix]
    for attr in ['exec_prefix', 'real_prefix', 'base_prefix']:
        if getattr(sys, attr, sys.prefix) not in res:
            res.append(getattr(sys, attr))
    return res

def execute(callable_to_track):
    t = trace.Trace(trace=False, 
        ignoredirs=_get_python_lib_paths())
    ret = t.runfunc(callable_to_track)
    used_files = {os.path.abspath(py_file) for py_file, line_no in t.results().counts.keys()}
    return used_files, ret

def pytest_runtest_call(__multicall__, item):
    if not item.config.getoption('testmon'):
        return __multicall__.execute()
    
    cache = item.config.cache

    used_files, ret = execute(__multicall__.execute)
    
    if not used_files:
        print "Warning: tracing of %s failed!" % item.nodeid

    tests_meta = cache.get(TESTS_CACHE_KEY, {})
    test_meta = tests_meta.setdefault(item.nodeid, {})
    test_meta['runs_modules'] = used_files

    cache.set(TESTS_CACHE_KEY, tests_meta)
    return ret