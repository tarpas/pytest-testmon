import logging
import os
import re

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


def get_packages_from_requirements(paths, rootdir=None) -> str:
    """
    Build a packages string from requirements.txt files and uv.lock files.

    requirements.txt: recurses into -r / --requirement and -c / --constraint
    includes, skips other pip options (lines starting with -).
    uv.lock (a path whose file name is exactly "uv.lock"): one spec per locked
    package, see _read_uv_lock.
    Returns a sorted, deduplicated comma-joined string of package specs.
    """
    specs: set[str] = set()
    _read_requirements(list(paths), rootdir or os.getcwd(), specs, seen=set())
    return ", ".join(sorted(specs))


def _read_requirements(paths, base_dir, specs, seen):
    for path in paths:
        abs_path = os.path.normpath(
            path if os.path.isabs(path) else os.path.join(base_dir, path)
        )
        if abs_path in seen:
            continue
        seen.add(abs_path)
        try:
            if os.path.basename(abs_path) == "uv.lock":
                specs.update(_read_uv_lock(abs_path))
                continue
            with open(abs_path, encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            logger.warning("testmon: requirements file not found: %s", abs_path)
            continue
        file_dir = os.path.dirname(abs_path)
        for raw_line in lines:
            line = raw_line.split("#")[0].strip()
            if not line:
                continue
            if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
                include = line.split(None, 1)[1].strip()
                _read_requirements([include], file_dir, specs, seen)
            elif line.startswith("-"):
                continue  # skip other pip options / flags
            else:
                specs.add(line)


def _read_uv_lock(abs_path):
    """
    Return one spec per package in a uv.lock file.

    A package from a registry gives "name==version". Any other source (git,
    url, path, ...) is added in brackets, because its version can stay the
    same while the code changes: a git source carries the commit.
    The project itself (source "virtual") is left out.
    Wheel lists, hashes and markers are not part of the result, so a lock that
    is written again without a version change gives the same specs.
    """
    try:
        import tomllib  # pylint: disable=import-outside-toplevel
    except ImportError as exc:  # Python 3.10
        raise RuntimeError(
            "testmon: reading uv.lock in testmon_packages_from needs Python 3.11 or newer"
        ) from exc

    with open(abs_path, "rb") as f:
        lock = tomllib.load(f)

    specs = set()
    for package in lock.get("package", []):
        source = package.get("source", {})
        if "virtual" in source:
            continue
        spec = package["name"]
        if "version" in package:
            spec = f"{spec}=={package['version']}"
        if "registry" not in source:
            details = ", ".join(f"{key}={source[key]}" for key in sorted(source))
            spec = f"{spec} ({details})"
        specs.add(spec)
    return specs


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
    """
    Return the git dir of the checkout containing *start_path*.

    Stops at the nearest `.git` entry. In a linked worktree or submodule `.git`
    is a file (`gitdir: <path>`) pointing at the checkout's own git dir, e.g.
    `<main>/.git/worktrees/<name>`, whose HEAD is the worktree's branch.
    """
    start_path = Path(start_path or os.getcwd()).resolve()
    current_path = start_path
    while current_path != current_path.parent:  # '/'.parent == '/'
        path = current_path / ".git"
        if path.is_dir():
            return str(path)
        if path.is_file():
            return _read_gitdir_file(path)
        current_path = current_path.parent
    return None


def _read_gitdir_file(path):
    try:
        content = path.read_text(encoding="utf8").strip()
    except OSError:
        return None
    if not content.startswith("gitdir:"):
        return None
    git_dir = (path.parent / content[len("gitdir:") :].strip()).resolve()
    return str(git_dir) if git_dir.is_dir() else None


def _git_common_dir(git_dir):
    """Shared dir holding refs/ and packed-refs (differs from git_dir in a worktree)."""
    try:
        with open(os.path.join(git_dir, "commondir"), "r", encoding="utf8") as f:
            common = f.read().strip()
    except FileNotFoundError:
        return git_dir
    return str((Path(git_dir) / common).resolve())


def _read_head(git_dir):
    try:
        with open(os.path.join(git_dir, "HEAD"), "r", encoding="utf8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def git_current_branch(path=None):
    # Explicit override always wins.
    if branch := os.environ.get("TESTMON_BRANCH", "").strip():
        return branch

    # GitHub Actions: GITHUB_HEAD_REF is the PR source branch (only set on PRs).
    if branch := os.environ.get("GITHUB_HEAD_REF", "").strip():
        return branch

    # GitHub Actions: GITHUB_REF_NAME is the branch name on push events but
    # looks like "123/merge" on PR events — skip those.
    if branch := os.environ.get("GITHUB_REF_NAME", "").strip():
        if "/" not in branch:
            return branch

    # GitLab CI / generic CI env vars.
    for var in ("CI_COMMIT_BRANCH", "GIT_BRANCH", "BRANCH_NAME"):
        if branch := os.environ.get(var, "").strip():
            return branch

    # Fall back to reading the checkout's own HEAD file directly.
    git_dir = git_path(path)
    if not git_dir:
        return None
    head = _read_head(git_dir)
    if head and head.startswith("ref:"):
        ref = head[len("ref:") :].strip()
        # "ref: refs/heads/feature/x" → "feature/x"
        return ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else ref
    return None  # detached HEAD with no CI env var


def git_pr_target_branch() -> str | None:
    """
    Return the target (base) branch of the current PR/MR, or None if not in a PR context.

    Priority:
      TESTMON_FALLBACK_BRANCH   – explicit override
      GITHUB_BASE_REF           – GitHub Actions (PR/push to branch)
      CI_MERGE_REQUEST_TARGET_BRANCH_NAME – GitLab CI merge request
      BITBUCKET_PR_DESTINATION_BRANCH     – Bitbucket Pipelines
      CHANGE_TARGET             – Jenkins multibranch pipeline
    """
    for var in (
        "TESTMON_FALLBACK_BRANCH",
        "GITHUB_BASE_REF",
        "CI_MERGE_REQUEST_TARGET_BRANCH_NAME",
        "BITBUCKET_PR_DESTINATION_BRANCH",
        "CHANGE_TARGET",
    ):
        if branch := os.environ.get(var, "").strip():
            return branch
    return None


def git_current_head(path=None):
    git_dir = git_path(path)
    if not git_dir:
        return None
    head = _read_head(git_dir)
    if not head:
        return None
    if not head.startswith("ref:"):
        return head  # detached HEAD holds the sha itself
    ref = head[len("ref:") :].strip()
    common_dir = _git_common_dir(git_dir)
    try:
        with open(os.path.join(common_dir, ref), "r", encoding="utf8") as ref_file:
            return ref_file.read().strip()
    except (FileNotFoundError, NotADirectoryError):
        pass
    try:
        with open(os.path.join(common_dir, "packed-refs"), "r", encoding="utf8") as f:
            for line in f:
                parts = line.strip().split(" ", 1)
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
    except FileNotFoundError:
        pass
    return None
