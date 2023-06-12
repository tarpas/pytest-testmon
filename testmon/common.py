import logging
import os
import re

try:
    import importlib.metadata

    def get_system_packages_raw():
        return (
            (pkg.metadata["Name"], pkg.version)
            for pkg in importlib.metadata.distributions()
        )

except ImportError:
    import pkg_resources

    def get_system_packages_raw():
        return ((pkg.project_name, pkg.version) for pkg in pkg_resources.working_set)


from pathlib import Path


def dummy():
    pass


def get_logger(name):
    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    return logging.getLogger(name)


logger = get_logger(__name__)


def get_system_packages(ignore=None):
    return ", ".join(
        sorted(
            {
                f"{package} {version}"
                for (package, version) in get_system_packages_raw()
                if not ignore or not package in ignore
            }
        )
    )


def drop_patch_version(system_packages):
    return re.sub(
        r"\b([\w_-]+\s\d+\.\d+)\.\w+\b",
        r"\1",
        system_packages,
    )


def git_path(start_path=None):
    start_path = Path(start_path or os.getcwd()).resolve()
    current_path = start_path
    while current_path != current_path.parent:
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
            return head_content.split("/")[-1]
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
