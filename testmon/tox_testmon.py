"""
A tox plugin to automatically install and use pytest-testmon with tox.

It installs pytest-testmon once `--testmon` is used in one of the commands
(starting with "pytest" or "py.test").

It also sets the TESTMON_DATAFILE environment variable (always) to use a
datafile in the venv's directory.

It uses the tox_runenvreport hook instead of tox_testenv_install_deps (where
it could just add the dep unconditionally) to only install pytest-testmon on
demand.  Changing envconfig.deps on demand would re-create the venv.
"""
import os

import pluggy
from tox.config import DepConfig

hookimpl = pluggy.HookimplMarker("tox")


def _uses_testmon(envconfig):
    """Test if an envconfig uses testmon by looking at the command(s)."""
    for command in envconfig.commands:
        if '--testmon' in command:
            return True
    return False


def touch_stampfile(venv):
    open(venv.path.join('.testmon_installed'), 'a').close()


def installed_testmon(venv):
    return os.path.exists(venv.path.join('.testmon_installed'))


@hookimpl
def tox_runenvreport(venv, action):
    if 'TESTMON_DATAFILE' in venv.envconfig.setenv:
        datafile = venv.envconfig.setenv['TESTMON_DATAFILE']
        action.setactivity('testmon', 'keeping TESTMON_DATAFILE=%s' % datafile)
    else:
        datafile = str(venv.path.join('.testmondata'))
        action.setactivity('testmon', 'setting TESTMON_DATAFILE=%s' % datafile)
        venv.envconfig.setenv['TESTMON_DATAFILE'] = datafile

    if (_uses_testmon(venv.envconfig)
            and 'pytest-testmon' not in (x.name for x in venv.envconfig.deps)):
        if not installed_testmon(venv):
            action.setactivity('testmon', 'installing pytest-testmon')
            # Uses _install for handling configured indexservers.
            # venv.run_install_command(['pytest-testmon'], action=action)
            venv._install([DepConfig('pytest-testmon')], action=action)

            touch_stampfile(venv)
