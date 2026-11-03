#!/usr/bin/env python3
"""RQ3 (which projects migrate in time?) and RQ4 (who performs the migration?).

Inputs: the scan (scan_migrations.py) and the features (extract_features.py) of the
same repositories. Timing, censoring and phases are taken from analyze_timing.py so
that every RQ uses the same definitions.

RQ3
  - "timely" = migrated before anything broke: artifact actions before any breakage
    (first brownout / v1-v2 cutoff), set-output before the announced cutoff (2023-05-31).
  - descriptive comparison of timely vs. not timely (medians, Mann-Whitney U / Fisher)
  - Cox proportional-hazards model of time to migration (censoring as in RQ1/RQ2) with
    few covariates: about one per ten migrations.
RQ4
  - who authored the change: bot, core maintainer or external contributor,
    overall and per phase; how many changes a bot initiated.

Usage:
  python3 scripts/analyze_factors.py <scan.tsv> <features.tsv> <out_dir> <label> [collection_date]
"""
import csv
import math
import os
import sys
from datetime import date

import numpy as np
from scipy.stats import fisher_exact, mannwhitneyu
from statsmodels.duration.hazard_regression import PHReg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_timing import EVENTS, load, phase  # noqa: E402

TIMELY = {"artifact_v3": "before any breakage", "set_output": "before announced cutoff"}
NUMERIC = [  # (column, label, transform for the model)
    ("stars", "stars", math.log10),
    ("contributors", "contributors", math.log10),
    ("commits_6m", "commits in 6 months before warning", math.log1p),
    ("workflow_files", "workflow files", math.log1p),
    ("occurrences", "deprecated occurrences", math.log1p),
    ("age_years", "age (years)", float),
]
BINARY = [("dependabot_actions", "Dependabot for Actions"), ("renovate", "Renovate"),
          ("update_bot", "Dependabot or Renovate")]
MODEL = ["stars", "commits_6m", "occurrences", "update_bot"]  # Cox covariates


def write_tsv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(header)
        w.writerows(rows)


def main(scan, features, out_dir, label, collection="2026-10-28"):
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, label)
    pairs = {(p["repo"], p["event"]): p for p in load(scan, date.fromisoformat(collection))}
    feats = {(r["repo"], r["event"]): r for r in csv.DictReader(open(features), delimiter="\t")}
    data = []
    for k, p in pairs.items():
        f = feats[k]
        f["update_bot"] = str(int(f["dependabot_actions"] == "1" or f["renovate"] == "1"))
        data.append({**p, **f, "phase": phase(p), "timely": phase(p) == TIMELY[p["event"]]})

    # ---------------- RQ3: descriptive comparison
    drows = []
    for ev in EVENTS:
        d = [x for x in data if x["event"] == ev]
        yes, no = [x for x in d if x["timely"]], [x for x in d if not x["timely"]]
        for col, lab, _ in NUMERIC:
            a = [float(x[col]) for x in yes]
            b = [float(x[col]) for x in no]
            p = mannwhitneyu(a, b).pvalue
            drows.append([ev, lab, len(yes), f"{np.median(a):g}", len(no), f"{np.median(b):g}",
                          "Mann-Whitney U", f"{p:.3f}"])
        for col, lab in BINARY:
            a1 = sum(x[col] == "1" for x in yes)
            b1 = sum(x[col] == "1" for x in no)
            p = fisher_exact([[a1, len(yes) - a1], [b1, len(no) - b1]]).pvalue
            drows.append([ev, lab, len(yes), f"{a1} ({100 * a1 / len(yes):.0f}%)", len(no),
                          f"{b1} ({100 * b1 / len(no):.0f}%)", "Fisher", f"{p:.3f}"])
    write_tsv(f"{base}_rq3_descriptive.tsv",
              ["event", "variable", "n_timely", "timely (median or count)", "n_not_timely",
               "not timely (median or count)", "test", "p"], drows)

    # ---------------- RQ3: Cox model of time to migration
    crows = []
    for ev in EVENTS:
        d = [x for x in data if x["event"] == ev]
        tf = {c: t for c, _, t in NUMERIC}
        X = np.array([[tf[c](float(x[c])) if c in tf else float(x[c]) for c in MODEL] for x in d])
        t = np.array([max(x["days"], 0.5) for x in d], dtype=float)
        s = np.array([int(x["observed"]) for x in d])
        res = PHReg(t, X, status=s, ties="efron").fit()
        ci = res.conf_int()
        for i, c in enumerate(MODEL):
            crows.append([ev, c, f"{math.exp(res.params[i]):.2f}",
                          f"{math.exp(ci[i][0]):.2f}–{math.exp(ci[i][1]):.2f}", f"{res.pvalues[i]:.3f}"])
        crows.append([ev, f"n={len(d)}, migrations={int(s.sum())}", "", "", ""])
    write_tsv(f"{base}_rq3_cox.tsv", ["event", "covariate (log10 stars, log1p counts)",
                                     "hazard ratio", "95% CI", "p"], crows)

    # ---------------- RQ4: who migrates
    rrows = []
    for ev in EVENTS:
        d = [x for x in data if x["event"] == ev and x["observed"]]
        for ph in [None] + sorted({x["phase"] for x in d}):
            sub = [x for x in d if ph is None or x["phase"] == ph]
            cnt = {k: sum(x["author_kind"] == k for x in sub) for k in ("bot", "core", "external")}
            bi = sum(x["bot_initiated"] == "1" for x in sub)
            rrows.append([ev, ph or "all migrations", len(sub)]
                         + [f"{cnt[k]} ({100 * cnt[k] / len(sub):.0f}%)" for k in ("bot", "core", "external")]
                         + [bi])
    write_tsv(f"{base}_rq4_authors.tsv", ["event", "phase", "migrations", "bot", "core", "external",
                                         "bot_initiated"], rrows)

    print(f"[{label}] RQ3 descriptive (timely vs not):")
    for r in drows:
        print("  " + " | ".join(map(str, r)))
    print("RQ3 Cox:")
    for r in crows:
        print("  " + " | ".join(map(str, r)))
    print("RQ4:")
    for r in rrows:
        print("  " + " | ".join(map(str, r)))


if __name__ == "__main__":
    main(*sys.argv[1:])
