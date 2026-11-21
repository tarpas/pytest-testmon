"""Delta tables from bench.py JSON.

Usage: python delta.py bench.json
"""

import json
import statistics
import sys

data = json.load(open(sys.argv[1]))
res = data["results"]
variants = list(next(iter(res.values())))


def med(s, v):
    return statistics.median(res[s][v])


def best(s, v):
    return min(res[s][v])


def pct(a, b):
    return f"{(a / b - 1) * 100:+.0f}%"


print(f"### Python {data['python']} ({data['reps']} reps)\n")

others = [v for v in variants if v != "plain"]
if "plain" in variants:
    print("#### Overhead vs plain (median)\n")
    print("| scenario | " + " | ".join(others) + " |")
    print("|---|" + "---|" * len(others))
    for s in res:
        print(f"| {s} | " + " | ".join(pct(med(s, v), med(s, "plain")) for v in others) + " |")

if {"branch ctrace", "branch sysmon"} <= set(variants):
    print("\n#### branch sysmon vs branch ctrace\n")
    print("| scenario | ctrace (s) | sysmon (s) | delta | speedup | delta (min) |")
    print("|---|---|---|---|---|---|")
    for s in res:
        c, m = med(s, "branch ctrace"), med(s, "branch sysmon")
        print(f"| {s} | {c:.2f} | {m:.2f} | {pct(m, c)} | {c / m:.2f}x "
              f"| {pct(best(s, 'branch sysmon'), best(s, 'branch ctrace'))} |")
