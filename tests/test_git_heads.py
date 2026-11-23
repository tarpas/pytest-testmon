"""git_heads in the repository layouts where reading .git by hand goes wrong, and in a shallow
clone, where git itself hides a commit's parents."""

from subprocess import run
from unittest import mock

import pytest

from testmon.common import git_heads
from testmon.testmon_core import TestmonData

LAYOUTS = ["branch", "slash", "packed", "detached", "worktree", "gitfile", "shallow"]


def git(directory, *args):
    """Run git for a test repository, whatever the user's configuration says."""
    options = (
        "user.name=testmon",
        "user.email=tests@testmon.org",
        "commit.gpgsign=false",
    )
    command = ["git"]
    for option in options:
        command += ["-c", option]
    result = run(
        command + list(args), cwd=directory, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


@pytest.fixture(params=LAYOUTS)
def merged(tmp_path, request):
    """A directory whose HEAD is a merge commit, in one of LAYOUTS; and the commit with its
    two parents."""
    directory = tmp_path / "repository"
    directory.mkdir()
    if request.param == "gitfile":
        git(directory, "init", "--separate-git-dir", str(tmp_path / "elsewhere.git"))
    else:
        git(directory, "init")
    git(directory, "symbolic-ref", "HEAD", "refs/heads/main")

    def commit(message):
        git(directory, "commit", "--allow-empty", "-m", message)
        return git(directory, "rev-parse", "HEAD")

    commit("base")
    git(directory, "checkout", "-b", "feature")
    feature = commit("feature")
    git(directory, "checkout", "main")
    main = commit("main")
    git(directory, "merge", "--no-ff", "-m", "merge", "feature")
    heads = [git(directory, "rev-parse", "HEAD"), main, feature]

    if request.param == "slash":
        git(directory, "branch", "-m", "topic/with/slashes")
    elif request.param == "packed":
        git(directory, "pack-refs", "--all")
    elif request.param == "detached":
        git(directory, "checkout", "--detach")
    elif request.param == "worktree":
        git(directory, "worktree", "add", "--detach", str(tmp_path / "linked"))
        directory = tmp_path / "linked"
    elif request.param == "shallow":  # what actions/checkout makes by default
        git(tmp_path, "clone", "--depth", "1", directory.as_uri(), "shallow")
        directory = tmp_path / "shallow"
        assert git(directory, "rev-parse", "--is-shallow-repository") == "true"
    return directory, heads


def test_git_heads(merged, monkeypatch):
    directory, heads = merged
    assert git_heads(str(directory)) == heads

    nested = directory / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    assert git_heads() == heads


@pytest.mark.parametrize("where", ["no repository", "no commit", "no directory"])
def test_git_heads_without_a_commit(tmp_path, monkeypatch, where):
    # tmp_path may lie inside a repository; git must not find that one.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    if where == "no commit":
        git(tmp_path, "init")
    elif where == "no directory":
        tmp_path = tmp_path / "missing"
    assert git_heads(str(tmp_path)) == []


def test_git_heads_without_git(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    assert git_heads(str(tmp_path)) == []


@pytest.mark.parametrize("merged", ["detached"], indirect=True)
def test_heads_go_to_testmon_net_only(merged, monkeypatch):
    directory, heads = merged
    proxy = mock.Mock()
    proxy.initiate_execution.return_value = {
        "exec_id": 1,
        "packages_changed": False,
        "filenames": [],
    }
    with TestmonData.for_local_run(
        str(directory), database=proxy, system_packages="", python_version="3.11"
    ):
        metadata = proxy.initiate_execution.call_args.args[3]
    assert metadata["git_heads"] == heads
    assert metadata["git_head_sha"] == heads[0]

    # A run with .testmondata has no use for the commits: it must not ask git for them.
    monkeypatch.setattr(
        "testmon.testmon_core.git_heads", mock.Mock(side_effect=AssertionError)
    )
    with TestmonData.for_local_run(
        str(directory), system_packages="", python_version="3.11"
    ):
        pass
