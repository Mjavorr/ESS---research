#!/usr/bin/env python3
"""RQ1 and RQ2: when do projects migrate, and does the deprecation regime matter?

Input is the output of scan_migrations.py. For every exposed (repository, event)
pair the time origin is the event's first warning (T_warn). Migrated pairs are
events at their migration date; pairs that never migrated are right-censored at
the earlier of the data-collection date and the repository's last commit (a
repository that stopped being developed had no further chance to migrate).

Outputs (in <out_dir>, file names prefixed with <label>):
  _phases.tsv      RQ1: migrations per phase of each deprecation's timeline
  _survival.tsv    RQ2: Kaplan-Meier summary per event (+ log-rank test)
  _paired.tsv      RQ2: repositories exposed to both events, side by side
  _km.pdf/.png     Kaplan-Meier curves (share still using the deprecated component)
  _weekly.pdf/.png migrations per week on the calendar, with the key dates

Usage:
  python3 scripts/analyze_timing.py <scan.tsv> <out_dir> <label> [collection_date]
"""
import csv
import math
import os
import sys
from datetime import date, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, MonthLocator
from scipy.stats import chi2, wilcoxon

D = date.fromisoformat

# Timeline of each deprecation (sources in docs/events.md).
EVENTS = {
    "artifact_v3": {
        "name": "Artifact actions v1–v3",
        "short": "artifact",
        "color": "#2a78d6",
        "t_warn": D("2024-04-16"),
        "marks": [  # (date, label) drawn on the figures
            (D("2024-04-16"), "deprecation notice"),
            (D("2024-06-30"), "v1/v2 cutoff"),
            (D("2025-01-09"), "first brownout"),
            (D("2025-01-30"), "v3 cutoff"),
        ],
        # KM figure: (from, to, label, y, side) - a span is drawn as a band
        "km_marks": [
            (D("2024-06-30"), None, "v1/v2 cutoff", 98, "right"),
            (D("2025-01-09"), D("2025-01-30"), "v3 brownouts, then cutoff", 98, "right"),
        ],
    },
    "set_output": {
        "name": "set-output / save-state",
        "short": "set-output",
        "color": "#eb6834",
        "t_warn": D("2022-10-11"),
        "marks": [
            (D("2022-10-11"), "deprecation notice"),
            (D("2023-05-31"), "announced cutoff"),
            (D("2023-07-24"), "cutoff postponed"),
        ],
        "km_marks": [
            (D("2023-05-31"), None, "announced cutoff", 6, "left"),
            (D("2023-07-24"), None, "postponed", 6, "right"),
        ],
    },
}
BROWNOUT_START, V3_CUTOFF = D("2025-01-09"), D("2025-01-30")
SO_CUTOFF, SO_POSTPONED = D("2023-05-31"), D("2023-07-24")
INK, INK2, GRID = "#1f1f1e", "#62615b", "#e4e3df"


# ---------------------------------------------------------------- statistics

def kaplan_meier(times, events):
    """Return [(t, S(t), n_at_risk)] at each distinct event time, S starting at 1."""
    data = sorted(zip(times, events))
    n = len(data)
    s, out, i = 1.0, [(0, 1.0, n)], 0
    while i < len(data):
        t = data[i][0]
        d = sum(1 for tt, e in data if tt == t and e)
        c = sum(1 for tt, e in data if tt == t and not e)
        if d:
            s *= 1 - d / n
            out.append((t, s, n))
        n -= d + c
        i += d + c
    return out


def km_at(curve, t):
    s = 1.0
    for tt, ss, _ in curve:
        if tt <= t:
            s = ss
    return s


def km_median(curve):
    return next((t for t, s, _ in curve if s <= 0.5), None)


def logrank(t1, e1, t2, e2):
    """Two-group log-rank test; returns (chi2 statistic, p-value)."""
    pts = sorted({t for t, e in zip(t1 + t2, e1 + e2) if e})
    o1 = ex1 = var = 0.0
    for t in pts:
        n1 = sum(1 for x in t1 if x >= t)
        n2 = sum(1 for x in t2 if x >= t)
        d1 = sum(1 for x, e in zip(t1, e1) if x == t and e)
        d2 = sum(1 for x, e in zip(t2, e2) if x == t and e)
        n, d = n1 + n2, d1 + d2
        if n < 2:
            continue
        o1 += d1
        ex1 += d * n1 / n
        var += d * (n1 / n) * (n2 / n) * (n - d) / (n - 1)
    stat = (o1 - ex1) ** 2 / var
    return stat, chi2.sf(stat, 1)


# ---------------------------------------------------------------- data

def load(path, collection):
    rows = list(csv.DictReader(open(path), delimiter="\t"))
    pairs = []
    for r in rows:
        if r["event"] not in EVENTS or r["exposed_at_warning"] in ("0", ""):
            continue
        ev = EVENTS[r["event"]]
        if r["migration_date"]:
            mig, end, observed = D(r["migration_date"]), D(r["migration_date"]), True
        else:
            mig, observed = None, False
            end = min(collection, D(r["last_repo_activity"]))
        pairs.append({
            "repo": r["repo"], "event": r["event"], "migration": mig, "observed": observed,
            "days": (end - ev["t_warn"]).days, "category": r["category"],
            "groups": r.get("group_migrations", ""), "bot": r["author_is_bot"] == "yes",
        })
    return pairs


def phase(p):
    """RQ1 phase of a migration on its deprecation's timeline."""
    if not p["observed"]:
        return "not migrated"
    m = p["migration"]
    if p["event"] == "artifact_v3":
        if p["category"] == "after_enforcement":
            return "after cutoff (broken)"
        if "2025-01-30" in p["groups"] and m >= BROWNOUT_START:
            return "during brownouts"
        return "before any breakage"
    if m < SO_CUTOFF:
        return "before announced cutoff"
    if m < SO_POSTPONED:
        return "between cutoff date and postponement"
    return "after postponement"


PHASES = {
    "artifact_v3": ["before any breakage", "during brownouts", "after cutoff (broken)", "not migrated"],
    "set_output": ["before announced cutoff", "between cutoff date and postponement",
                   "after postponement", "not migrated"],
}


# ---------------------------------------------------------------- figures

def style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def fig_km(curves, out):
    fig, ax = plt.subplots(figsize=(7, 3.6))
    style(ax)
    xmax = max(max(c["times"]) for c in curves.values())
    for key, c in curves.items():
        ev = EVENTS[key]
        xs, ys = [0], [1.0]
        for t, s, _ in c["km"][1:]:
            xs += [t, t]
            ys += [ys[-1], s]
        xs.append(xmax)
        ys.append(ys[-1])
        ax.plot(xs, [y * 100 for y in ys], color=ev["color"], linewidth=2,
                label=f"{ev['name']} (n = {len(c['times'])})")
        cens = [t for t, e in zip(c["times"], c["events"]) if not e]
        ax.plot(cens, [km_at(c["km"], t) * 100 for t in cens], "|", color=ev["color"],
                markersize=7, markeredgewidth=1.2)
        # direct label at the right end of the curve
        ax.annotate(ev["short"], (xmax, ys[-1] * 100), xytext=(4, 0), textcoords="offset points",
                    color=INK, fontsize=8, va="center")
        # key dates of this event, as offsets from its own notice
        for d0, d1, label, y, side in ev["km_marks"]:
            x0 = (d0 - ev["t_warn"]).days
            if d1:
                x1 = (d1 - ev["t_warn"]).days
                ax.axvspan(x0, x1, color=ev["color"], alpha=0.15, linewidth=0)
            else:
                x1 = x0
                ax.axvline(x0, color=ev["color"], linewidth=0.8, linestyle=(0, (3, 3)))
            ax.annotate(label, (x1 if side == "right" else x0, y), fontsize=6.5, color=INK2,
                        ha="left" if side == "right" else "right", va="center",
                        xytext=(3 if side == "right" else -3, 0), textcoords="offset points")
    ax.set_xlim(0, xmax * 1.06)
    ax.set_ylim(0, 102)
    ax.set_xlabel("Days since the deprecation notice", fontsize=8.5, color=INK)
    ax.set_ylabel("Repositories still using the\ndeprecated component (%)", fontsize=8.5, color=INK)
    ax.legend(frameon=False, fontsize=8, loc="upper right", bbox_to_anchor=(1.0, 0.86))
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(f"{out}.{ext}", dpi=200)
    plt.close(fig)


def fig_weekly(pairs, out):
    keys = list(EVENTS)
    fig, axes = plt.subplots(len(keys), 1, figsize=(7, 4.4))
    for ax, key in zip(axes, keys):
        ev = EVENTS[key]
        style(ax)
        dates = [p["migration"] for p in pairs if p["event"] == key and p["observed"]]
        start = ev["t_warn"] - timedelta(days=ev["t_warn"].weekday() + 28)
        end = max(dates) + timedelta(days=7)
        weeks = {}
        for d in dates:
            wk = d - timedelta(days=d.weekday())
            weeks[wk] = weeks.get(wk, 0) + 1
        ax.bar(list(weeks), list(weeks.values()), width=5, color=ev["color"], linewidth=0)
        top = max(weeks.values())
        for d, label in ev["marks"]:
            ax.axvline(d, color=INK2, linewidth=0.8, linestyle=(0, (3, 3)))
            ax.annotate(label, (d, top * 1.05), fontsize=6.5, color=INK2, rotation=90,
                        ha="right", va="top", xytext=(-2, 0), textcoords="offset points")
        ax.set_xlim(start, end)
        ax.set_ylim(0, top * 1.1)
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        span = (end - start).days
        ax.xaxis.set_major_locator(MonthLocator(bymonth=(1, 4, 7, 10) if span < 900 else (1, 7)))
        ax.xaxis.set_major_formatter(DateFormatter("%b %Y"))
        ax.set_title(f"{ev['name']}: migrations per week (n = {len(dates)})",
                     fontsize=8.5, color=INK, loc="left")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(f"{out}.{ext}", dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------- main

def write_tsv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(header)
        w.writerows(rows)


def main(scan, out_dir, label, collection="2026-10-28"):
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, label)
    pairs = load(scan, D(collection))

    # RQ1: phases
    rows = []
    for key in EVENTS:
        ps = [p for p in pairs if p["event"] == key]
        for ph in PHASES[key]:
            n = sum(1 for p in ps if phase(p) == ph)
            rows.append([key, ph, n, f"{100 * n / len(ps):.1f}"])
    write_tsv(f"{base}_phases.tsv", ["event", "phase", "repositories", "percent"], rows)

    # RQ2: survival per event
    curves, srows = {}, []
    for key in EVENTS:
        ps = [p for p in pairs if p["event"] == key]
        t = [p["days"] for p in ps]
        e = [p["observed"] for p in ps]
        km = kaplan_meier(t, e)
        curves[key] = {"times": t, "events": e, "km": km}
        srows.append([key, len(ps), sum(e), len(ps) - sum(e), km_median(km)]
                     + [f"{100 * (1 - km_at(km, d)):.1f}" for d in (30, 90, 180, 365, 730)]
                     + [sum(1 for p in ps if p["bot"])])
    stat, pval = logrank(curves["artifact_v3"]["times"], curves["artifact_v3"]["events"],
                         curves["set_output"]["times"], curves["set_output"]["events"])
    srows.append(["log-rank artifact vs set-output", f"chi2={stat:.2f}", f"p={pval:.3g}"])
    write_tsv(f"{base}_survival.tsv",
              ["event", "exposed", "migrated", "censored", "km_median_days",
               "migrated_by_30d_%", "by_90d_%", "by_180d_%", "by_365d_%", "by_730d_%",
               "migrations_by_bot_author"], srows)

    # RQ2: repositories exposed to both events
    by = {}
    for p in pairs:
        by.setdefault(p["repo"], {})[p["event"]] = p
    both = {r: v for r, v in by.items() if len(v) == 2}
    prow, diffs = [], []
    for r, v in sorted(both.items()):
        a, s = v["artifact_v3"], v["set_output"]
        prow.append([r, a["days"] if a["observed"] else f">{a['days']}", phase(a),
                     s["days"] if s["observed"] else f">{s['days']}", phase(s)])
        if a["observed"] and s["observed"]:
            diffs.append(a["days"] - s["days"])
    write_tsv(f"{base}_paired.tsv", ["repo", "artifact_days", "artifact_phase",
                                     "set_output_days", "set_output_phase"], prow)
    w = wilcoxon(diffs) if len(diffs) >= 6 else None

    fig_km(curves, f"{base}_km")
    fig_weekly(pairs, f"{base}_weekly")

    # console summary
    print(f"[{label}] {len({p['repo'] for p in pairs})} exposed repositories, {len(pairs)} (repo, event) pairs")
    for r in rows:
        print(f"  {r[0]:12} {r[1]:38} {r[2]:>4}  {r[3]:>5}%")
    for r in srows[:-1]:
        print(f"  {r[0]:12} n={r[1]} migrated={r[2]} KM median={r[4]} d; migrated by 30/90/180/365/730 d: "
              + "/".join(r[5:10]) + " %")
    print(f"  log-rank: chi2={stat:.2f}, p={pval:.3g}")
    print(f"  both events: {len(both)} repos, {len(diffs)} migrated twice; "
          + (f"median(artifact - set-output) = {sorted(diffs)[len(diffs)//2]} d, Wilcoxon p={w.pvalue:.3g}"
             if w else "too few pairs for a test"))


if __name__ == "__main__":
    main(*sys.argv[1:])
