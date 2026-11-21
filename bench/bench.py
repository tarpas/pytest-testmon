"""Benchmark: plain pytest vs branch ctrace vs branch sysmon.

Usage: python bench.py <venv python> <work dir> <reps> [scenario...]

  <venv python>   python of a venv with the branch installed (pip install -e .),
                  plus pytest-cov and pytest-xdist
  <main worktree> checkout of upstream main (git worktree add <dir> main):
                  put first on PYTHONPATH for the "main ctrace" variant
  <work dir>      holds more-itertools/ (git clone --depth 1 --branch v10.5.0
                  https://github.com/more-itertools/more-itertools) and
                  tiny/ is generated there on first use
  [scenario...]   only these scenarios (names as printed)

BENCH_VARIANTS="plain,branch sysmon" limits the variants.
  <reps>          runs per variant; the median and min are printed

Every run starts from an empty .testmondata (full collection run). Variants
are interleaved within each repetition to spread machine noise.
"""

import json
import os
import shutil
import statistics
import subprocess
import sys
import time

py, work, reps = sys.argv[1], sys.argv[2], int(sys.argv[3])
only = sys.argv[4:]
MITER = os.path.join(work, "more-itertools")


def make_tiny(root):
    os.makedirs(os.path.join(root, "tests"), exist_ok=True)
    with open(os.path.join(root, "lib.py"), "w") as fh:
        fh.write("def inc(x):\n    return x + 1\n")
    for m in range(20):
        with open(os.path.join(root, "tests", f"test_t{m}.py"), "w") as fh:
            fh.write("from lib import inc\n")
            for i in range(250):
                fh.write(f"def test_{i}():\n    assert inc({i}) == {i + 1}\n")


SCENARIOS = {
    "more-itertools": (MITER, ["tests"]),
    "more-itertools --cov": (MITER, ["tests", "--cov=more_itertools"]),
    "5000 tiny tests": (os.path.join(work, "tiny"), ["tests"]),
    "more-itertools -n 4": (MITER, ["tests", "-n", "4"]),
}
if not os.path.isdir(SCENARIOS["5000 tiny tests"][0]):
    make_tiny(SCENARIOS["5000 tiny tests"][0])

base_env = {k: v for k, v in os.environ.items() if not k.startswith(("TESTMON", "COVERAGE"))}
base_env["PYTHONDONTWRITEBYTECODE"] = "1"
VARIANTS = {
    "plain": ({}, ["-p", "no:testmon"]),
    "branch ctrace": ({"TESTMON_CORE": "ctrace"}, ["--testmon"]),
    "branch sysmon": ({"TESTMON_CORE": "sysmon"}, ["--testmon"]),
}
if os.environ.get("BENCH_VARIANTS"):  # e.g. "plain,main ctrace,branch sysmon"
    VARIANTS = {v: VARIANTS[v] for v in os.environ["BENCH_VARIANTS"].split(",")}


def run(cwd, args, extra_env, opts):
    for name in os.listdir(cwd):
        if name.startswith(".testmondata") or name in (".coverage", ".pytest_cache"):
            p = os.path.join(cwd, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    env = dict(base_env, PYTHONPATH=cwd, **extra_env)
    t = time.perf_counter()
    r = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *opts, *args],
                       cwd=cwd, env=env, capture_output=True, text=True)
    elapsed = time.perf_counter() - t
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
    if r.returncode != 0:
        raise SystemExit(f"FAILED {cwd} {opts} {args}: {tail}")
    return elapsed, tail


pyver = subprocess.check_output([py, "-c", "import sys;print(sys.version.split()[0])"], text=True).strip()
print(f"python: {pyver}, reps={reps}")
results = {}
print(f"{'scenario':24} " + " ".join(f"{v:>15}" for v in VARIANTS))
for scen, (cwd, args) in SCENARIOS.items():
    if only and scen not in only:
        continue
    times = {v: [] for v in VARIANTS}
    for _ in range(reps):  # interleave variants to spread machine noise
        for v, (extra_env, opts) in VARIANTS.items():
            times[v].append(run(cwd, args, extra_env, opts)[0])
    results[scen] = times
    print(f"{scen:24} " + " ".join(f"{statistics.median(t):6.2f} (min{min(t):5.2f})" for t in times.values()), flush=True)

if os.environ.get("BENCH_JSON"):
    with open(os.environ["BENCH_JSON"], "w") as fh:
        json.dump({"python": pyver, "reps": reps, "results": results}, fh, indent=2)
