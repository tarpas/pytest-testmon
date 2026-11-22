"""Benchmark: plain pytest vs testmon with the ctrace and sysmon collectors.

Usage: python bench.py <venv python> <work dir> <reps> ["scenario" ...]

  <venv python>   python of a venv with this checkout installed
                  (pip install -e .), plus pytest-cov and pytest-xdist
  <work dir>      holds a more-itertools/ clone (tag: MITER_TAG in
                  .github/workflows/benchmark.yml); the synthetic projects
                  (tiny/, param/) are regenerated there on every run
  <reps>          timed runs per scenario and variant
  "scenario"      only these scenarios, names exactly as printed, e.g.
                  python bench.py .venv/bin/python work 3 "full: 5000 tiny tests"

Environment:
  BENCH_VARIANTS=plain,sysmon   only these variants
  BENCH_JSON=bench.json         also write the timings as JSON (input of delta.py)

Two kinds of scenarios:
  * full: starts from an empty .testmondata, every test runs and is recorded.
    Measures testmon's collection overhead.
  * rerun: a first, untimed testmon run fills .testmondata, then an optional
    edit is applied and the timed run follows (the edit is reverted after).
    Measures what testmon is used for day to day: selection, deselection and
    recording the few tests that run.

"plain" has no .testmondata: it skips the fill run and the edit and always runs
the whole unchanged suite. On reruns, the delta against plain is what testmon
saves.

Each row prints the median of the reps, in seconds. Variants are interleaved
within each repetition to spread machine noise.
"""

import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

PARAM_SIZE = 10000
# pytest's exit code when no test ran: fine for a testmon rerun with no change,
# a failure anywhere else
NO_TESTS_COLLECTED = 5


@dataclass
class Edit:
    """Replace `old` by `new` in `path` (relative to the project); `old` must
    occur exactly once."""

    path: str
    old: str
    new: str


@dataclass
class Scenario:
    project: str  # directory pytest runs in
    args: list
    rerun: bool = False  # fill .testmondata with an untimed run first
    edit: Edit | None = None  # applied between the fill run and the timed run


@dataclass
class Variant:
    opts: list  # pytest options
    env: dict = field(default_factory=dict)
    uses_testmon: bool = True


VARIANTS = {
    "plain": Variant(["-p", "no:testmon"], uses_testmon=False),
    "ctrace": Variant(["--testmon"], {"TESTMON_CORE": "ctrace"}),
    "sysmon": Variant(["--testmon"], {"TESTMON_CORE": "sysmon"}),
}


def make_tiny(root):
    """5000 one-line tests: 20 files of 250 tests, all calling lib.inc()."""
    os.makedirs(os.path.join(root, "tests"), exist_ok=True)
    with open(os.path.join(root, "lib.py"), "w") as fh:
        fh.write("def inc(x):\n    return x + 1\n")
    for m in range(20):
        with open(os.path.join(root, "tests", f"test_t{m}.py"), "w") as fh:
            fh.write("from lib import inc\n")
            for i in range(250):
                fh.write(f"def test_{i}():\n    assert inc({i}) == {i + 1}\n")


def make_param(root):
    """One file, PARAM_SIZE parametrized items and test_other.

    Every item of the file is collected on a rerun, so selection work grows
    with the number of stable tests in collected files."""
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "test_param.py"), "w") as fh:
        fh.write(
            "import pytest\n\n\n"
            f"@pytest.mark.parametrize('i', range({PARAM_SIZE}))\n"
            "def test_p(i):\n    assert i >= 0\n\n\n"
            "def test_other():\n    assert True\n"
        )


def build_scenarios(work_dir):
    miter = os.path.join(work_dir, "more-itertools")
    tiny = os.path.join(work_dir, "tiny")
    param = os.path.join(work_dir, "param")
    # Always regenerated (cheap): CI caches <work dir>, and a cached copy would
    # not follow changes to the generators.
    make_tiny(tiny)
    make_param(param)
    return {
        "full: more-itertools": Scenario(miter, ["tests"]),
        "full: more-itertools --cov": Scenario(
            miter, ["tests", "--cov=more_itertools"]
        ),
        "full: more-itertools -n 4": Scenario(miter, ["tests", "-n", "4"]),
        "full: 5000 tiny tests": Scenario(tiny, ["tests"]),
        f"full: {PARAM_SIZE} params": Scenario(param, ["."]),
        "rerun: more-itertools, no change": Scenario(miter, ["tests"], rerun=True),
        "rerun: more-itertools, edit chunked()": Scenario(
            miter,
            ["tests"],
            rerun=True,
            # chunked() is a helper of many other functions; the AST changes, so
            # this is a real dependency change (a comment would only change fsha)
            edit=Edit(
                "more_itertools/more.py",
                "iterator = iter(partial(take, n, iter(iterable)), [])",
                "iterator = iter(partial(take, n, iter(iterable)), list())",
            ),
        ),
        "rerun: 5000 tiny tests, no change": Scenario(tiny, ["tests"], rerun=True),
        "rerun: 5000 tiny tests, edit 1 test": Scenario(
            tiny,
            ["tests"],
            rerun=True,
            edit=Edit(
                "tests/test_t0.py", "assert inc(0) == 1\n", "assert inc(0) == 1 + 0\n"
            ),
        ),
        f"rerun: {PARAM_SIZE} params, edit 1 test": Scenario(
            param,
            ["."],
            rerun=True,
            edit=Edit("test_param.py", "assert True\n", "assert not False\n"),
        ),
    }


def select_variants():
    names = os.environ.get("BENCH_VARIANTS")
    if not names:
        return VARIANTS
    unknown = set(names.split(",")) - set(VARIANTS)
    if unknown:
        raise SystemExit(
            f"unknown BENCH_VARIANTS {sorted(unknown)}, choose from {list(VARIANTS)}"
        )
    return {name: VARIANTS[name] for name in names.split(",")}


# Ambient TESTMON*/COVERAGE*/PYTEST* variables (e.g. PYTEST_ADDOPTS) would
# change what a variant measures.
# No .pyc writes: every run compiles (and pytest rewrites asserts) the same way.
BASE_ENV = {
    k: v
    for k, v in os.environ.items()
    if not k.startswith(("TESTMON", "COVERAGE", "PYTEST"))
}
BASE_ENV["PYTHONDONTWRITEBYTECODE"] = "1"


def clean(project):
    """Remove testmon's, coverage's and pytest's state from the project, so the
    run starts cold."""
    for name in os.listdir(project):
        if name.startswith((".testmondata", ".coverage")) or name == ".pytest_cache":
            path = os.path.join(project, name)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)


def run_pytest(python, project, scenario_args, variant, allow_no_tests=False):
    """Run pytest once; return (seconds, summary), where summary is pytest's last
    output line (e.g. "1 passed, 4999 deselected in 0.08s")."""
    env = dict(BASE_ENV, PYTHONPATH=project, **variant.env)
    cmd = [
        python,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *variant.opts,
        *scenario_args,
    ]
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True)
    seconds = time.perf_counter() - start
    stdout = proc.stdout.strip()
    summary = stdout.splitlines()[-1] if stdout else proc.stderr[-300:]
    ok_codes = (0, NO_TESTS_COLLECTED) if allow_no_tests else (0,)
    if proc.returncode not in ok_codes:
        raise SystemExit(f"FAILED {project} {variant.opts} {scenario_args}: {summary}")
    return seconds, summary


@contextmanager
def applied_edit(project, edit):
    """The edit is on disk inside the block and reverted after."""
    if edit is None:
        yield
        return
    path = os.path.join(project, edit.path)
    with open(path) as fh:
        original = fh.read()
    if original.count(edit.old) != 1:
        raise SystemExit(f"edit target not found exactly once in {path}: {edit.old!r}")
    with open(path, "w") as fh:
        fh.write(original.replace(edit.old, edit.new))
    try:
        yield
    finally:
        with open(path, "w") as fh:
            fh.write(original)


def timed_run(python, scenario, variant):
    """One timed run of the scenario; the fill run of a rerun isn't timed."""
    clean(scenario.project)
    if not variant.uses_testmon:  # plain: the whole unchanged suite
        return run_pytest(python, scenario.project, scenario.args, variant)
    if scenario.rerun:
        run_pytest(python, scenario.project, scenario.args, variant)
    with applied_edit(scenario.project, scenario.edit):
        return run_pytest(
            python,
            scenario.project,
            scenario.args,
            variant,
            allow_no_tests=scenario.rerun,
        )


def main():
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    # absolute: pytest runs with the project as cwd
    python = os.path.abspath(sys.argv[1])
    work_dir, reps, only = sys.argv[2], int(sys.argv[3]), sys.argv[4:]
    scenarios = build_scenarios(work_dir)
    unknown = set(only) - set(scenarios)
    if unknown:
        raise SystemExit(
            f"unknown scenarios {sorted(unknown)}, choose from {list(scenarios)}"
        )
    variants = select_variants()
    width = max(map(len, scenarios))

    python_version = subprocess.check_output(
        [python, "-c", "import sys; print(sys.version.split()[0])"], text=True
    ).strip()
    print(f"python: {python_version}, reps={reps}")
    print(f"{'scenario':{width}} " + " ".join(f"{name:>8}" for name in variants))

    timings = {}  # {scenario: {variant: [seconds per rep]}}
    last_summaries = {}  # {scenario: {variant: pytest summary of the last rep}}
    for name, scenario in scenarios.items():
        if only and name not in only:
            continue
        times = {variant: [] for variant in variants}
        summaries = {}
        for _ in range(reps):  # interleave variants to spread machine noise
            for variant_name, variant in variants.items():
                seconds, summaries[variant_name] = timed_run(python, scenario, variant)
                times[variant_name].append(seconds)
        timings[name] = times
        last_summaries[name] = summaries
        cells = (f"{statistics.median(t):8.2f}" for t in times.values())
        print(f"{name:{width}} " + " ".join(cells), flush=True)

    # What each timed run actually did, to check that a rerun scenario selects
    # what it claims to.
    print("\npytest summary of the last timed run:")
    for name, summaries in last_summaries.items():
        for variant_name, summary in summaries.items():
            print(f"  {name:{width}} {variant_name:8} {summary}")

    if os.environ.get("BENCH_JSON"):
        with open(os.environ["BENCH_JSON"], "w") as fh:
            json.dump(
                {"python": python_version, "reps": reps, "timings": timings},
                fh,
                indent=2,
            )


if __name__ == "__main__":
    main()
