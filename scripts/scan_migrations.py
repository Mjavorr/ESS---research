#!/usr/bin/env python3
"""Pilot re-scan: exposure and migration timing for two GitHub Actions deprecations.

For every cloned repository it reports, per deprecation event:
  - how many active (non-commented) occurrences existed on the default branch
    just before the first warning (T_warn),
  - the migration commit = earliest commit after which no occurrence remains
    on the default branch,
  - the timing category relative to T_warn / T_enforce.

Usage: python3 scripts/scan_migrations.py <clones_dir> <out.tsv>
"""
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date

EVENTS = {
    # Official artifact actions only, ignore commented-out lines.
    "artifact_v3": {
        "regex": r"^[^#]*uses:[[:space:]]*['\"]?actions/(upload|download)-artifact@v[123]([^0-9.]|$)",
        "loose": r"actions/(upload|download)-artifact@v[123]",
        "t_warn": "2024-04-16",    # GitHub changelog: deprecation notice
        "t_enforce": "2025-01-30",  # changelog 2024-04-16: v3 stops working 30 Jan 2025
        # Version groups with their own cutoff (same changelog: v1/v2 on 30 Jun 2024).
        # A repository counts as migrating "after enforcement" if any group it used at
        # T_warn disappeared only after that group's cutoff.
        "groups": [
            (r"^[^#]*uses:[[:space:]]*['\"]?actions/(upload|download)-artifact@v[12]([^0-9.]|$)", "2024-06-30"),
            (r"^[^#]*uses:[[:space:]]*['\"]?actions/(upload|download)-artifact@v3([^0-9.]|$)", "2025-01-30"),
        ],
    },
    "set_output": {
        "regex": r"^[^#]*::(set-output|save-state)",
        "loose": r"::(set-output|save-state)",
        "t_warn": "2022-10-11",    # GitHub changelog: deprecation notice
        "t_enforce": None,          # announced for 2023-05-31, postponed on 2023-07-24, never enforced
    },
}
WF = ".github/workflows"
BOTS = ("[bot]", "dependabot", "renovate", "github-actions")


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout.strip()


def count(repo, sha, regex, retries=3):
    """Number of matching lines in the workflow files at `sha`.

    git grep exits 0 (matches), 1 (no match) or >1 (error). With partial clones
    an error usually means a blob could not be fetched; treating it as "no match"
    would silently drop exposures, so we retry and then fail loudly.
    """
    for attempt in range(retries):
        r = subprocess.run(["git", "-C", repo, "grep", "-E", "-c", regex, sha, "--", WF],
                           capture_output=True, text=True)
        if r.returncode in (0, 1):
            return sum(int(l.rsplit(":", 1)[1]) for l in r.stdout.splitlines() if l)
    raise RuntimeError(f"git grep failed in {repo} at {sha}: {r.stderr.strip()[:300]}")


def find_migration(repo_dir, regex, t_warn):
    """Earliest default-branch commit after T_warn after which `regex` no longer matches.

    Candidates are all first-parent commits touching workflows since T_warn, oldest
    first (merge commits included, so migrations landing through a merge are found).
    Binary search assumes the count stays 0 once it reaches 0; the hit is verified.
    Returns [sha, date, author, subject] or four empty strings.
    """
    fmt = "--format=%H%x1f%cs%x1f%an%x1f%s"
    cands = [c.split("\x1f", 3) for c in git(
        repo_dir, "log", "--reverse", "--first-parent", f"--since={t_warn}",
        fmt, "--", WF).splitlines() if c.count("\x1f") == 3]
    lo, hi = 0, len(cands) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if count(repo_dir, cands[mid][0], regex) == 0:
            hi = mid
        else:
            lo = mid + 1
    if cands and count(repo_dir, cands[lo][0], regex) == 0 and (
            lo == 0 or count(repo_dir, cands[lo - 1][0], regex) > 0):
        sha, d, author, subj = cands[lo]
        return [sha[:10], d, author, subj[:100]]
    return ["", "", "", ""]


def scan(repo_dir):
    name = os.path.basename(repo_dir).replace("__", "/", 1)
    head = git(repo_dir, "rev-parse", "HEAD")
    if not head:
        return [[name, "-", "CLONE_FAIL"]]
    last_activity = git(repo_dir, "log", "-1", "--format=%cs", "HEAD")
    rows = []
    for ev, cfg in EVENTS.items():
        warn_sha = git(repo_dir, "rev-list", "-1", "--first-parent", f"--before={cfg['t_warn']}", "HEAD")
        exposed = count(repo_dir, warn_sha, cfg["regex"]) if warn_sha else 0
        now = count(repo_dir, head, cfg["regex"])
        mig = ["", "", "", ""]
        category = "not_exposed"
        basis = ""
        if exposed:
            if now:
                category = "never (as of collection)"
            else:
                mig = find_migration(repo_dir, cfg["regex"], cfg["t_warn"])
                late = []
                if "groups" in cfg:
                    for regex, cutoff in cfg["groups"]:
                        if count(repo_dir, warn_sha, regex):
                            gm = find_migration(repo_dir, regex, cfg["t_warn"])
                            if gm[1] and gm[1] >= cutoff:
                                late.append(cutoff)
                            basis += f"{cutoff}:{gm[1] or '?'};"
                elif cfg["t_enforce"] and mig[1] and mig[1] >= cfg["t_enforce"]:
                    late.append(cfg["t_enforce"])
                if not mig[1]:
                    category = "migrated (commit not resolved)"
                elif late:
                    category = "after_enforcement"
                else:
                    category = "during_warning"
        days = ""
        if mig[1]:
            days = (date.fromisoformat(mig[1]) - date.fromisoformat(cfg["t_warn"])).days
        is_bot = "yes" if mig[2] and any(b in mig[2].lower() for b in BOTS) else ("no" if mig[2] else "")
        rows.append([name, ev, exposed, now, category, days, *mig[:3], is_bot, mig[3], last_activity, basis])
    return rows


if __name__ == "__main__":
    clones, out = sys.argv[1], sys.argv[2]
    dirs = sorted(os.path.join(clones, d) for d in os.listdir(clones))
    header = ["repo", "event", "exposed_at_warning", "still_present_now", "category",
              "days_from_warning", "migration_commit", "migration_date", "migration_author",
              "author_is_bot", "migration_subject", "last_repo_activity",
              "group_migrations"]  # per version group: "<cutoff>:<migration date>;"
    with ProcessPoolExecutor(max_workers=12) as ex:
        results = [r for rows in ex.map(scan, dirs) for r in rows]
    with open(out, "w") as f:
        f.write("\t".join(header) + "\n")
        for r in results:
            f.write("\t".join(map(str, r)) + "\n")
