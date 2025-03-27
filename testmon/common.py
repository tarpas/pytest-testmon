import logging
import os
import re
import sys

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


logging.basicConfig(
    level=logging.getLevelName(logging.INFO),
    format='%(asctime)s - [%(levelname)s] - [%(threadName)s] - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)


def get_logger(name):
    return logging.getLogger(name)


logger = get_logger(__name__)


def get_system_packages(track_sys_packages, ignore):
    if track_sys_packages:
        return __drop_patch_version(", ".join(
            sorted(
                {
                    f"{package} {version}"
                    for (package, version) in get_system_packages_raw()
                    if not package in (ignore or {"pytest-testmon", "pytest-testmon"})
                }
            )
        ))
    else:
        return "default_syc_packages"



def get_python_version(track_python_version):
    if track_python_version:
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    else:
        return "default_python_version"


def __drop_patch_version(system_packages):
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
    path = git_path(path)
    if not path:
        return None
    current_branch = git_current_branch(path)
    if not current_branch:
        return None
    git_branch_file = os.path.join(path, "refs", "heads", current_branch)
    try:
        with open(git_branch_file, "r", encoding="utf8") as branch_file:
            head_sha = branch_file.read().strip()
        return head_sha
    except FileNotFoundError:
        pass
    return None
