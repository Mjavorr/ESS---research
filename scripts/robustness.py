#!/usr/bin/env python3
"""Robustness checks for RQ2 and RQ3.

1. Proportional-hazards assumption of the RQ3 Cox models: correlation of the
   Schoenfeld residuals of each covariate with the rank of the event time
   (Grambsch-Therneau style check). A small p-value means the covariate's effect
   changes over time, so its hazard ratio is an average that must be read with care.
2. Multiple testing: Holm correction of the RQ3 p-values (the descriptive tests and
   the Cox coefficients, each family corrected separately).
3. Censoring: RQ2 recomputed with pairs that never migrated censored at the
   data-collection date instead of their last commit.

Usage:
  python3 scripts/robustness.py <scan.tsv> <features.tsv> <results_dir> <label> [collection_date]
"""
import csv
import math
import os
import sys
from datetime import date

import numpy as np
from scipy.stats import spearmanr
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.stats.multitest import multipletests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_timing import EVENTS, kaplan_meier, km_at, km_median, load, logrank  # noqa: E402
from analyze_factors import MODEL, NUMERIC  # noqa: E402


def write_tsv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(header)
        w.writerows(rows)


def main(scan, features, results, label, collection="2026-10-28"):
    base = os.path.join(results, label)
    coll = date.fromisoformat(collection)
    pairs = {(p["repo"], p["event"]): p for p in load(scan, coll)}
    feats = {(r["repo"], r["event"]): r for r in csv.DictReader(open(features), delimiter="\t")}
    tf = {c: t for c, _, t in NUMERIC}
    rows = []

    # 1. proportional hazards
    for ev in EVENTS:
        keys = [k for k in pairs if k[1] == ev]
        for k in keys:
            f = feats[k]
            f["update_bot"] = str(int(f["dependabot_actions"] == "1" or f["renovate"] == "1"))
        X = np.array([[tf[c](float(feats[k][c])) if c in tf else float(feats[k][c]) for c in MODEL]
                      for k in keys])
        t = np.array([max(pairs[k]["days"], 0.5) for k in keys], dtype=float)
        s = np.array([int(pairs[k]["observed"]) for k in keys])
        res = PHReg(t, X, status=s, ties="efron").fit()
        sr = res.schoenfeld_residuals
        ev_idx = ~np.isnan(sr[:, 0])
        ranks = t[ev_idx].argsort().argsort()
        for i, c in enumerate(MODEL):
            rho, p = spearmanr(sr[ev_idx, i], ranks)
            rows.append(["proportional hazards", ev, c, f"rho={rho:.2f}", f"p={p:.3f}",
                         "ok" if p >= 0.05 else "effect varies over time"])

    # 2. Holm correction of the RQ3 p-values
    for name in ("rq3_descriptive", "rq3_cox"):
        tab = list(csv.DictReader(open(f"{base}_{name}.tsv"), delimiter="\t"))
        tab = [r for r in tab if r.get("p") not in (None, "")]
        raw = [float(r["p"]) for r in tab]
        adj = multipletests(raw, method="holm")[1]
        for r, p0, p1 in zip(tab, raw, adj):
            var = r.get("variable") or r.get("covariate (log10 stars, log1p counts)")
            rows.append([f"Holm, {name}", r["event"], var, f"p={p0:.3f}", f"p_holm={p1:.3f}",
                         "significant" if p1 < 0.05 else "not significant"])

    # 3. censoring at the collection date
    curves = {}
    for ev in EVENTS:
        ps = [p for k, p in pairs.items() if k[1] == ev]
        t = [p["days"] if p["observed"] else (coll - EVENTS[ev]["t_warn"]).days for p in ps]
        e = [p["observed"] for p in ps]
        km = kaplan_meier(t, e)
        curves[ev] = (t, e)
        rows.append(["censoring at collection date", ev, "KM median days", str(km_median(km)),
                     f"by 365 d: {100 * (1 - km_at(km, 365)):.1f}%", ""])
    stat, p = logrank(*curves["artifact_v3"], *curves["set_output"])
    rows.append(["censoring at collection date", "both", "log-rank", f"chi2={stat:.2f}", f"p={p:.3g}", ""])

    write_tsv(f"{base}_robustness.tsv", ["check", "event", "item", "value", "p / detail", "verdict"], rows)
    for r in rows:
        print(" | ".join(r))


if __name__ == "__main__":
    main(*sys.argv[1:])
