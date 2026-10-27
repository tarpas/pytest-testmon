#!/usr/bin/env python
"""
Throwaway script: compare pytest-cov vs --testmon-cov output side-by-side.

Creates a temp project, runs both tools, parses the Cobertura XML, and prints
a per-file / per-line diff so you can see where block-level reconstruction
diverges from real line-level coverage.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# ── sample project ──────────────────────────────────────────────────────────

SAMPLE_MODULE = """\
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    def multiply(self, a, b):
        return a * b

    def divide(self, a, b):
        if b == 0:
            raise ValueError("division by zero")
        return a / b


def greet(name):
    if name:
        return f"Hello, {name}!"
    return "Hello, stranger!"


def unused_function():
    x = 1
    y = 2
    return x + y
"""

SAMPLE_TESTS = """\
from mymod import Calculator, greet


def test_add():
    c = Calculator()
    assert c.add(1, 2) == 3


def test_subtract():
    c = Calculator()
    assert c.subtract(5, 3) == 2


def test_divide():
    c = Calculator()
    assert c.divide(10, 2) == 5.0


def test_divide_by_zero():
    c = Calculator()
    try:
        c.divide(1, 0)
    except ValueError:
        pass


def test_greet_with_name():
    assert greet("World") == "Hello, World!"


def test_greet_without_name():
    assert greet("") == "Hello, stranger!"
"""

# ── helpers ─────────────────────────────────────────────────────────────────


def parse_cobertura(xml_path):
    """Return {filename: {line_number: hits}} from a Cobertura XML."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    result = {}
    for pkg in root.findall(".//package"):
        for cls in pkg.findall(".//class"):
            fname = cls.get("filename")
            lines = {}
            for line in cls.findall(".//line"):
                lines[int(line.get("number"))] = int(line.get("hits"))
            result[fname] = lines
    return result


def run(cmd, cwd):
    print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode not in (0, 5):  # 5 = no tests collected, ok for testmon-cov standalone
        print(f"  STDOUT:\n{r.stdout}")
        print(f"  STDERR:\n{r.stderr}")
        sys.exit(f"command failed (rc={r.returncode})")
    return r


def compare(cov_data, tm_data, source_lines):
    """Print a side-by-side comparison for one file. Return (match, mismatch) counts."""
    all_lines = sorted(set(cov_data.keys()) | set(tm_data.keys()))
    match = mismatch = cov_only = tm_only = 0

    print(f"  {'Line':>5}  {'Source':<55} {'pytest-cov':>10} {'testmon-cov':>11}  {'':>5}")
    print(f"  {'─'*5}  {'─'*55} {'─'*10} {'─'*11}  {'─'*5}")

    for ln in all_lines:
        src = source_lines.get(ln, "").rstrip()
        if len(src) > 55:
            src = src[:52] + "..."
        c = cov_data.get(ln)
        t = tm_data.get(ln)

        c_str = str(c) if c is not None else "-"
        t_str = str(t) if t is not None else "-"

        if c is not None and t is not None:
            if (c > 0) == (t > 0):
                flag = "  ✓"
                match += 1
            else:
                flag = "  ✗ DIFF"
                mismatch += 1
        elif c is not None:
            flag = "  cov-only"
            cov_only += 1
        else:
            flag = "  tm-only"
            tm_only += 1

        print(f"  {ln:>5}  {src:<55} {c_str:>10} {t_str:>11} {flag}")

    return match, mismatch, cov_only, tm_only


# ── main ────────────────────────────────────────────────────────────────────


def main():
    tmpdir = tempfile.mkdtemp(prefix="testmon_cov_compare_")
    print(f"Working in: {tmpdir}\n")

    # write sample project
    Path(tmpdir, "mymod.py").write_text(SAMPLE_MODULE)
    Path(tmpdir, "test_mymod.py").write_text(SAMPLE_TESTS)

    # 1) pytest-cov run
    print("═" * 80)
    print("Step 1: pytest-cov")
    print("═" * 80)
    run(
        [
            sys.executable, "-m", "pytest", "-q",
            "--cov=.", "--cov-report", "xml:cov_report.xml",
            "--override-ini=addopts=",
        ],
        cwd=tmpdir,
    )
    cov_xml = os.path.join(tmpdir, "cov_report.xml")

    # 2) testmon collection run
    print("\n" + "═" * 80)
    print("Step 2: pytest --testmon (collect data)")
    print("═" * 80)
    # clean any leftover testmon db
    db_path = os.path.join(tmpdir, ".testmondata")
    if os.path.exists(db_path):
        os.remove(db_path)
    run(
        [
            sys.executable, "-m", "pytest", "-q",
            "--testmon",
            "--override-ini=addopts=",
        ],
        cwd=tmpdir,
    )

    # 3) testmon-cov report
    print("\n" + "═" * 80)
    print("Step 3: pytest --testmon-cov (generate report)")
    print("═" * 80)
    run(
        [
            sys.executable, "-m", "pytest", "-q",
            "--testmon-cov=tm_report.xml",
            "--override-ini=addopts=",
        ],
        cwd=tmpdir,
    )
    tm_xml = os.path.join(tmpdir, "tm_report.xml")

    # 4) parse and compare
    print("\n" + "═" * 80)
    print("Comparison")
    print("═" * 80)
    cov_all = parse_cobertura(cov_xml)
    tm_all = parse_cobertura(tm_xml)

    all_files = sorted(set(cov_all.keys()) | set(tm_all.keys()))

    total_match = total_mismatch = total_cov_only = total_tm_only = 0

    for fname in all_files:
        # read source for display
        src_path = os.path.join(tmpdir, fname)
        if os.path.exists(src_path):
            source_lines = {
                i + 1: line
                for i, line in enumerate(Path(src_path).read_text().splitlines())
            }
        else:
            source_lines = {}

        cov_data = cov_all.get(fname, {})
        tm_data = tm_all.get(fname, {})

        print(f"\n┌── {fname} ──")
        m, mm, co, to = compare(cov_data, tm_data, source_lines)
        total_match += m
        total_mismatch += mm
        total_cov_only += co
        total_tm_only += to
        print(f"└── match={m}  diff={mm}  cov-only={co}  tm-only={to}")

    print(f"\n{'═' * 80}")
    print(
        f"TOTAL: match={total_match}  diff={total_mismatch}  "
        f"cov-only={total_cov_only}  tm-only={total_tm_only}"
    )
    if total_mismatch:
        print("Lines marked DIFF are where block-level reconstruction diverges from real line coverage.")
    else:
        print("No coverage disagreements found!")
    print(f"{'═' * 80}")

    # cleanup
    print(f"\nTemp dir left at: {tmpdir}")
    print("Delete with:  rm -rf", tmpdir)


if __name__ == "__main__":
    main()
