import logging
import os
from pathlib import Path


def dummy():
    pass


def get_logger(name):
    logging.basicConfig(format="%(levelname)s: %(message)s.", level=logging.WARNING)
    return logging.getLogger(name)


logger = get_logger(__name__)


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
