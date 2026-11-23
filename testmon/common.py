import logging
import os
import re
from subprocess import CalledProcessError, DEVNULL, PIPE, run

try:
    # Python >= 3.8
    import importlib.metadata

    def get_system_packages_raw():
        return (
            (pkg.metadata["Name"], pkg.version)
            for pkg in importlib.metadata.distributions()
        )

except ImportError:
    # Python < 3.7
    import pkg_resources

    def get_system_packages_raw():
        return (
            (pkg.project_name, pkg.version)
            for pkg in pkg_resources.working_set  # pylint: disable=not-an-iterable
        )


from pathlib import Path

from typing import TypedDict, List, Dict


class FileFp(TypedDict):
    filename: str
    method_checksums: List[int] = None
    mtime: float = None  # optimization helper, not really a part of the data structure fundamentally
    fsha: int = None  # optimization helper, not really a part of the data structure fundamentally
    fingerprint_id: int = None  # optimization helper,


TestName = str

TestFileFps = Dict[TestName, List[FileFp]]

Duration = float
Failed = bool


class DepsNOutcomes(TypedDict):
    deps: List[FileFp]
    failed: Failed
    duration: Duration
    forced: bool = None


TestExecutions = Dict[TestName, DepsNOutcomes]


def dummy():
    pass


def get_logger(name):
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Configure the logger
    tm_logger = logging.getLogger(name)
    tm_logger.setLevel(logging.INFO)
    tm_logger.addHandler(handler)
    return tm_logger


logger = get_logger(__name__)


def get_system_packages(ignore=None):
    if not ignore:
        ignore = set(("pytest-testmon", "pytest-testmon"))
    return ", ".join(
        sorted(
            {
                f"{package} {version}"
                for (package, version) in get_system_packages_raw()
                if package not in ignore and package != "UNKNOWN" and version != "0.0.0"
            }
        )
    )


def drop_patch_version(system_packages):
    return re.sub(
        r"\b([\w_-]+\s\d+\.\d+)\.\w+\b",  # extract (Package M.N).P / drop .patch
        r"\1",
        system_packages,
    )


#
# .git utilities
#
def git_path(start_path=None):  # parent dirs only
    start_path = Path(start_path or os.getcwd()).resolve()
    current_path = start_path
    while current_path != current_path.parent:  # '/'.parent == '/'
        path = current_path / ".git"
        if path.exists() and path.is_dir():
            return str(path)
        current_path = current_path.parent
    return None


def git_current_branch(path=None):
    path = git_path(path)
    if not path:
        return None
    git_head_file = os.path.join(path, "HEAD")
    try:
        with open(git_head_file, "r", encoding="utf8") as head_file:
            head_content = head_file.read().strip()
        if head_content.startswith("ref:"):
            return head_content.split("/")[-1]  # e.g. ref: refs/heads/master
    except FileNotFoundError:
        pass
    return None


def git_current_head(path=None):
    try:
        result = run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=path or None,
            check=True,
            stdout=PIPE,
            stderr=DEVNULL,
            text=True,
            encoding="ascii",
        )
    except (OSError, CalledProcessError):
        return None
    return result.stdout.strip()
