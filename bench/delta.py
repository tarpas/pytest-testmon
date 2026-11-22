"""Markdown tables comparing the variants, from the JSON bench.py writes.

Usage: python delta.py bench.json > bench-delta.md

Prints GitHub-flavoured markdown on stdout:
  * "vs plain", when plain was measured;
  * "sysmon vs ctrace", when both were measured.
"""

import json
import statistics
import sys

PLAIN, CTRACE, SYSMON = "plain", "ctrace", "sysmon"


def pct_change(new, base):
    """Relative change of new over base: "+10%" means new is 10% slower."""
    return f"{(new / base - 1) * 100:+.0f}%"


def main():
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
    timings = data["timings"]  # {scenario: {variant: [seconds per rep]}}
    variants = list(next(iter(timings.values())))

    def median(scenario, variant):
        return statistics.median(timings[scenario][variant])

    print(f"### Python {data['python']} ({data['reps']} reps)\n")

    testmon_variants = [v for v in variants if v != PLAIN]
    if PLAIN in variants:
        print("#### vs plain (median)\n")
        print("Full runs: testmon's overhead. Reruns: plain runs the whole suite, so a")
        print("negative delta is the time testmon saves.\n")
        print(
            "| scenario | plain (s) | "
            + " | ".join(f"{v} (s)" for v in testmon_variants)
            + " |"
        )
        print("|---|---|" + "---|" * len(testmon_variants))
        for scenario in timings:
            base = median(scenario, PLAIN)
            cells = (
                f"{median(scenario, v):.2f} ({pct_change(median(scenario, v), base)})"
                for v in testmon_variants
            )
            print(f"| {scenario} | {base:.2f} | " + " | ".join(cells) + " |")

    if {CTRACE, SYSMON} <= set(variants):
        print("\n#### sysmon vs ctrace (median)\n")
        print("Negative delta: sysmon is faster.\n")
        print("| scenario | ctrace (s) | sysmon (s) | delta |")
        print("|---|---|---|---|")
        for scenario in timings:
            ctrace, sysmon = median(scenario, CTRACE), median(scenario, SYSMON)
            print(
                f"| {scenario} | {ctrace:.2f} | {sysmon:.2f} | {pct_change(sysmon, ctrace)} |"
            )


if __name__ == "__main__":
    main()
