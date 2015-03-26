#!/usr/bin/env python
from __future__ import print_function

import argparse
import os
import subprocess
import sys
import time

import watchdog.events
import watchdog.observers


def run_pytest(changed_file=".py"):

    cmd_line = ['py.test-2.7',
                '-v',
                '--testmon',
                '--project-directory=%s' % args.project_directory]

    try:
        subprocess.call(cmd_line)
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
