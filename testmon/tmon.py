#!/usr/bin/env python
from __future__ import print_function

import argparse
import os
import subprocess
import sys
import time

import watchdog.events
import watchdog.observers

import shlex


def run_pytest(event=None):

    cmd_line = shlex.split(args.pytest_cmd)
    cmd_line += ['--testmon',
                 '--project-directory=%s' % args.project_directory]
    print("Calling py.test: {}".format(cmd_line))

    callback = None
    try:
        subprocess.check_call(cmd_line)
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)
        if args.cb_failure:
            callback = shlex.split(args.cb_failure)
    else:
        if args.cb_success:
            callback = shlex.split(args.cb_success)

    if event and callback:
        callback = map(lambda x: x.format(event.src_path), callback)
        print("Calling callback: {}".format(callback))
        subprocess.call(callback)


class EventHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self):
        watchdog.events.FileSystemEventHandler.__init__(self)

    def on_any_event(self, e):
        if e.src_path.endswith(".py") or getattr(e, 'dest_path', '').endswith(".py"):
            run_pytest(event=e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--project-directory',
                        help="Directory to start discovery ('.' default)",
                        default=os.getcwd())
    parser.add_argument('--pytest-cmd',
                        help="base py.test command to run (can have arguments)",
                        default='py.test-2.7')
    parser.add_argument('--cb-success',
                        help="Command to be run on success")
    parser.add_argument('--cb-failure',
                        help="Command to be run on failure")
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
