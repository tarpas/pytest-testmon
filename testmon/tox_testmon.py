import os

from pathlib import Path
import pluggy

from tox.config import DepConfig

hookimpl = pluggy.HookimplMarker("tox")


def _uses_testmon(envconfig):

    for command in envconfig.commands:
        if "--testmon" in command:
            return True
    return False


def touch_stampfile(venv):
    Path(venv.path.join(".testmon_installed")).touch()


def installed_testmon(venv):
    return os.path.exists(venv.path.join(".testmon_installed"))


@hookimpl
def tox_runenvreport(venv, action):
    if "TESTMON_DATAFILE" in venv.envconfig.setenv:
        datafile = venv.envconfig.setenv["TESTMON_DATAFILE"]
        action.setactivity("testmon", f"keeping TESTMON_DATAFILE={datafile}")
    else:
        datafile = str(venv.path.join(".testmondata"))
        action.setactivity("testmon", f"setting TESTMON_DATAFILE={datafile}")
        venv.envconfig.setenv["TESTMON_DATAFILE"] = datafile

    if _uses_testmon(venv.envconfig) and "pytest-testmon" not in (
        x.name for x in venv.envconfig.deps
    ):
        if not installed_testmon(venv):
            action.setactivity("testmon", "installing pytest-testmon")
            venv._install([DepConfig("pytest-testmon")], action=action)

            touch_stampfile(venv)
