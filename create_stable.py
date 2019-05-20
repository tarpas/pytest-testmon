#!/usr/bin/env python3
import subprocess
import os

OUTPUT_DIR = 'testmon'


"""
Replace names and options to distinguish from dev version
"""


def replace_line(line, old_substring, new_substring):
    return line.replace(old_substring, new_substring)


def edit_file(file_path, replace_pairs):
    with open(file_path, 'r') as f:
        lines = f.readlines()

    filename = file_path.split('/')[-1]
    with open(f'{OUTPUT_DIR}/{filename}', 'w') as f:
        for line in lines:
            for replace in replace_pairs:
                line = replace_line(line, replace[0], replace[1])
            f.write(line)


def replace_setup():
    print('Replacing setup.py ...')
    path = "setup.py"
    replace_pairs = (
        ('name=\'pytest-testmon-dev\'', 'name=\'pytest-testmon\''),
        ('(\'README.rst\')', '(\'../README.rst\')'),
        ('packages=[\'testmon_dev\',],', ''),
        ('testmon_dev = testmon_dev.pytest_testmon', 'testmon = pytest_testmon'),
        ('testmon_dev = testmon_dev.tox_testmon', 'testmon = tox_testmon')
    )
    edit_file(path, replace_pairs)


def replace_pytest_testmon():
    print('Replacing pytest_testmon.py ...')
    path = "testmon_dev/pytest_testmon.py"
    replace_pairs = [
        ["from testmon_dev.testmon_core", "from testmon.testmon_core"],
        ["PLUGIN_NAME = 'testmon-dev'", "PLUGIN_NAME='testmon'"]
    ]
    edit_file(path, replace_pairs)


def replace_testmon_core():
    print('Replacing testmon_core.py ...')
    path = "testmon_dev/testmon_core.py"
    replace_pairs = [
        ["from testmon_dev.process_code", "from testmon.process_code"]
    ]
    edit_file(path, replace_pairs)


def replace_process_code():
    print('Replacing process_code.py ...')
    path = "testmon_dev/process_code.py"
    replace_pairs = [
    ]
    edit_file(path, replace_pairs)


def replace_tox_testmon():
    print('Replacing tox_testmon.py ...')
    path = "testmon_dev/tox_testmon.py"
    replace_pairs = [
    ]
    edit_file(path, replace_pairs)


if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

replace_setup()
replace_pytest_testmon()
replace_testmon_core()
replace_process_code()
replace_tox_testmon()
print('DONE')
