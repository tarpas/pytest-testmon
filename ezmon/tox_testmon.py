from pathlib import Path
import pluggy

from tox.config import DepConfig

hookimpl = pluggy.HookimplMarker("tox")


def _uses_testmon(envconfig):

    for command in envconfig.commands:
        if "--ezmon" in command:
            return True
    return False


def touch_stampfile(venv):
    Path(venv.path.join(".testmon_installed")).touch()


def installed_testmon(venv):
    return Path(venv.path.join(".testmon_installed")).exists()


@hookimpl
def tox_runenvreport(venv, action):
    if "TESTMON_DATAFILE" in venv.envconfig.setenv:
        datafile = venv.envconfig.setenv["TESTMON_DATAFILE"]
        action.setactivity("ezmon", f"keeping TESTMON_DATAFILE={datafile}")
    else:
        datafile = str(venv.path.join(".testmondata"))
        action.setactivity("ezmon", f"setting TESTMON_DATAFILE={datafile}")
        venv.envconfig.setenv["TESTMON_DATAFILE"] = datafile

    if _uses_testmon(venv.envconfig) and "pytest-ezmon" not in (
        x.name for x in venv.envconfig.deps
    ):
        if not installed_testmon(venv):
            action.setactivity("ezmon", "installing pytest-ezmon")
            venv._install([DepConfig("pytest-ezmon")], action=action)

            touch_stampfile(venv)
