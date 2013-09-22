#!/usr/bin/env python2
import os
import itertools
import fnmatch
import time
from os.path import basename
from pprint import pprint
import coverage
import nose
import watchdog.observers
import watchdog.events

def run_tests(tests):
    if tests:
        argv = ["-x", "-s", "-v", "--tests="
                + ",".join("%s:%s" % (test[1], test[2]) for test in tests)]
        nose.run(argv=argv)

def get_tests(context):
    if isinstance(context, nose.case.Test):
        return [context]
    tests = [get_tests(x) for x in context]
    return list(itertools.chain(*tests))

def get_files_recursively(path, pattern):
    files = []
    for root, dirnames, filenames in os.walk(path):
        for filename in fnmatch.filter(filenames, pattern):
            files.append(os.path.join(root, filename))
    return files

def create_mapping():
    print "Analysing code...",
    tests = get_tests(nose.loader.TestLoader().loadTestsFromDir(os.getcwd()))
    py_files = get_files_recursively(os.getcwd(), "*.py")
    mapping = {}
    for test in tests:
        cov = coverage.coverage()
        cov.start()
        test.runTest(None)
        cov.stop()
        cov.save()
        for file in py_files:
            analysis = cov.analysis(file)
            if analysis[1] != analysis[2]: # this file was used
                mapping[file] = mapping.get(file, set()) | set([test.address()])
    print "done."
    return mapping

class EventHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self, mapping):
        watchdog.events.FileSystemEventHandler.__init__(self)
        self.mapping = mapping
    
    def on_any_event(self, e):
        dest_path = getattr(e, "dest_path", "")
        if not e.src_path.endswith(".py") and not dest_path.endswith(".py"):
            # only python files are of interest to us
            return
        if type(e) == watchdog.events.FileCreatedEvent:
            self._file_created(e.src_path)
        if type(e) == watchdog.events.FileDeletedEvent:
            self._file_deleted(e.src_path)
        if type(e) == watchdog.events.FileModifiedEvent:
            self._file_modified(e.src_path)
        if type(e) == watchdog.events.FileMovedEvent:
            self._file_deleted(e.src_path)
            # we could be overwriting existing file
            self._file_modified(e.dest_path)
            self._file_created(e.dest_path)
    
    def _file_deleted(self, path):
        if basename(path).startswith("test_"):
            self.mapping = create_mapping() # TODO: optimize by focusing only on this new test
        else:
            # we may invalidate some tests by removing vital files
            run_tests(mapping.get(path, []))
    
    def _file_created(self, path):
        if basename(path).startswith("test_"):
            # new test is created
            self.mapping = create_mapping() # TODO: optimize by focusing only on this new test
        else:
            # it is improbable that new code will invalidate tests
            pass
    
    def _file_modified(self, path):
        if basename(path).startswith("test_"):
            # we have tests mapped to themselves
            run_tests(mapping.get(path, []))
        else:
            # we may invalidate some tests
            run_tests(mapping.get(path, []))

if __name__ == "__main__":
    mapping = create_mapping()
    
    observer = watchdog.observers.Observer()
    observer.schedule(EventHandler(mapping), path=os.getcwd(), recursive=True)
    observer.start()
    print "Ready. Watching for changes."
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
