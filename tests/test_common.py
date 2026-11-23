# pylint: disable=unused-argument
from subprocess import run

import pytest

from testmon.common import get_system_packages, git_current_head
from testmon.testmon_core import TestmonData

pytest_plugins = ("pytester",)


class TestMisc:
    def test_get_system_packages(self, monkeypatch):
        monkeypatch.setattr(
            "testmon.common.get_system_packages_raw", lambda: [("a", "1.2.3")]
        )
        assert get_system_packages() == "a 1.2.3"

    def test_get_system_packages_ignore(self):
        assert "pytest " not in get_system_packages(ignore={"pytest"})


@pytest.fixture(params=["branch", "slash", "packed", "detached", "worktree", "gitfile"])
def git_repository(tmp_path, request):
    repository = tmp_path / "repository"
    repository.mkdir()

    def git(*args):
        return (
            run(
                ["git", "-c", "core.autocrlf=true", *args],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            .stdout.decode()
            .strip()
        )

    init_args = (
        ["--separate-git-dir", str(tmp_path / "gitdir")]
        if request.param == "gitfile"
        else []
    )
    git("init", "-b", "main", *init_args)
    git("config", "user.name", "testmon tests")
    git("config", "user.email", "tests@testmon.org")
    git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "Initial commit")
    expected = git("rev-parse", "HEAD")
    if request.param == "slash":
        git("branch", "-m", "feature/topic")
    elif request.param == "packed":
        git("pack-refs", "--all")
    elif request.param == "detached":
        git("checkout", "--detach")
    elif request.param == "worktree":
        worktree = tmp_path / "worktree"
        git("worktree", "add", "--detach", str(worktree))
        repository = worktree
    return repository, expected


def test_git_current_head(git_repository, monkeypatch):
    repository, expected = git_repository
    assert git_current_head(repository) == expected
    nested = repository / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    assert git_current_head() == expected
    assert git_current_head("") == expected


def test_execution_metadata_git_head(git_repository, monkeypatch, mocker):
    repository, expected = git_repository
    monkeypatch.chdir(repository)
    proxy = mocker.Mock()
    proxy.initiate_execution.return_value = {
        "exec_id": 1,
        "packages_changed": False,
        "filenames": [],
    }
    with TestmonData.for_local_run(
        str(repository), database=proxy, system_packages="", python_version="3.11"
    ):
        metadata = proxy.initiate_execution.call_args.args[3]
        assert metadata["git_head_sha"] == expected


@pytest.mark.parametrize("kind", ["outside", "unborn", "missing"])
def test_git_current_head_unavailable(tmp_path, kind):
    if kind == "unborn":
        run(
            ["git", "-c", "core.autocrlf=true", "init", str(tmp_path)],
            check=True,
            capture_output=True,
        )
    elif kind == "missing":
        tmp_path = tmp_path / "missing"
    assert git_current_head(tmp_path) is None


def test_git_current_head_without_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    assert git_current_head() is None
