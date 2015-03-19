#!/usr/bin/env python
from __future__ import print_function
import os
import sys
import time
import argparse
import subprocess

import watchdog.observers
import watchdog.events

import shlex


def run_pytest(changed_file=".py"):

    cmd_line = shlex.split(args.pytest_cmd)
    cmd_line += ['--testmon',
                 '--project-directory=%s' % args.project_directory]
    print("Calling py.test: {}".format(cmd_line))

    try:
        subprocess.check_call(cmd_line)
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)


class EventHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self):
        watchdog.events.FileSystemEventHandler.__init__(self)
    
    def on_any_event(self, e):
        if e.src_path.endswith(".py") or getattr(e, 'dest_path', '').endswith(".py"):
            run_pytest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--project-directory',
                        help="Directory to start discovery ('.' default)",
                        default=os.getcwd())
    parser.add_argument('--pytest-cmd',
                        help="base py.test command to run (can have arguments)",
                        default='py.test-2.7')
    args = parser.parse_args()
    run_pytest()

    observer = watchdog.observers.Observer()
    observer.schedule(EventHandler(), path=args.project_directory, recursive=True)
    observer.start()
    print("Ready. Watching for changes.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
