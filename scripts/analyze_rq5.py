#!/usr/bin/env python3
"""RQ5: summary tables of the qualitative coding (docs/rq5_codebook.md).

Inputs: the scan (for phases, via analyze_timing.py) and data/sample/rq5_coding.tsv.
Outputs in <out_dir>, prefixed with <label>:
  _rq5_change.tsv     change type per event
  _rq5_trigger.tsv    trigger per event, and per RQ1 phase for the artifact actions
  _rq5_problems.tsv   problems per event (a pair can have several)
  _rq5_examples.tsv   every pair with a problem, with its note

Usage:
  python3 scripts/analyze_rq5.py <scan.tsv> <rq5_coding.tsv> <out_dir> <label> [collection_date]
"""
import csv
import os
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_timing import EVENTS, load, phase  # noqa: E402

CHANGE = ["bump", "adapt", "remove", "replace", "none"]
TRIGGER = ["bot", "breakage", "deprecation", "targeted", "routine", "incidental"]
PROBLEMS = ["incompatibility", "environment", "regression", "multiline", "deferral"]


def pct(n, d):
    return f"{n} ({100 * n / d:.0f}%)" if d else "0"


def write_tsv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(header)
        w.writerows(rows)


def main(scan, coding, out_dir, label, collection="2026-10-28"):
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, label)
    pairs = {(p["repo"], p["event"]): p for p in load(scan, date.fromisoformat(collection))}
    codes = {(r["repo"], r["event"]): r for r in csv.DictReader(open(coding), delimiter="\t")}
    assert set(codes) == set(pairs), "coding and scan disagree on the exposed pairs"

    by_ev = {ev: [codes[k] for k in codes if k[1] == ev] for ev in EVENTS}

    rows = []
    for c in CHANGE:
        rows.append([c] + [pct(sum(r["change_type"] == c for r in by_ev[ev]), len(by_ev[ev])) for ev in EVENTS])
    write_tsv(f"{base}_rq5_change.tsv", ["change type"] + [f"{ev} (n={len(by_ev[ev])})" for ev in EVENTS], rows)

    mig = {ev: [r for r in by_ev[ev] if r["change_type"] != "none"] for ev in EVENTS}
    art_phases = ["before any breakage", "during brownouts", "after cutoff (broken)"]
    art_by_phase = {ph: [codes[k] for k in codes if k[1] == "artifact_v3" and phase(pairs[k]) == ph]
                    for ph in art_phases}
    trows = []
    for t in TRIGGER:
        trows.append([t] + [pct(sum(r["trigger"] == t for r in mig[ev]), len(mig[ev])) for ev in EVENTS]
                     + [pct(sum(r["trigger"] == t for r in art_by_phase[ph]), len(art_by_phase[ph]))
                        for ph in art_phases])
    write_tsv(f"{base}_rq5_trigger.tsv",
              ["trigger"] + [f"{ev} migrations (n={len(mig[ev])})" for ev in EVENTS]
              + [f"artifact: {ph} (n={len(art_by_phase[ph])})" for ph in art_phases], trows)

    prows = []
    for p in PROBLEMS:
        prows.append([p] + [pct(sum(p in r["problems"].split(";") for r in by_ev[ev]), len(by_ev[ev]))
                            for ev in EVENTS])
    anyp = [sum(r["problems"] != "none" for r in by_ev[ev]) for ev in EVENTS]
    prows.append(["any problem"] + [pct(n, len(by_ev[ev])) for n, ev in zip(anyp, EVENTS)])
    write_tsv(f"{base}_rq5_problems.tsv", ["problem"] + [f"{ev} (n={len(by_ev[ev])})" for ev in EVENTS], prows)

    ex = [[r["repo"], r["event"], r["change_type"], r["trigger"], r["problems"], r["note"]]
          for k, r in sorted(codes.items()) if r["problems"] != "none"]
    write_tsv(f"{base}_rq5_examples.tsv", ["repo", "event", "change", "trigger", "problems", "note"], ex)

    for name, rr in (("change", rows), ("trigger", trows), ("problems", prows)):
        print(f"[{label}] {name}")
        for r in rr:
            print("  " + " | ".join(r))


if __name__ == "__main__":
    main(*sys.argv[1:])
