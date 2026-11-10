#!/usr/bin/env python3
"""Project characteristics (RQ3) and migration authorship (RQ4) per exposed pair.

For every exposed (repository, event) pair of a scan_migrations.py output:

RQ3, measured on the default branch at the event's first warning (T_warn):
  dependabot_actions  .github/dependabot.y(a)ml configures the github-actions ecosystem
  renovate            a Renovate config file exists (Renovate updates Actions by default)
  commits_6m          commits in the 182 days before T_warn
  authors_6m          distinct commit authors in the same window
  workflow_files      number of files in .github/workflows
  occurrences         deprecated occurrences at T_warn (from the scan)
  + stars, contributors, commits, language, age_years from the SEART frame, if given

RQ4, for migrated pairs:
  change_commit       the commit that actually changed the deprecated lines: the migration
                      commit itself, or for a merge commit the latest non-merge commit it
                      brought in that touched those lines
  author              author of change_commit (mailmap applied)
  author_kind         bot | core | external  (see classify_author)
  same_repo_branch    merged from a PR whose branch lives in the repository itself
  bot_initiated       message credits a bot (e.g. a Dependabot PR finished by a human)

Usage:
  python3 scripts/extract_features.py <clones_dir> <scan.tsv> <out.tsv> [frame.tsv]
"""
import csv
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patterns import DEPRECATED_PY, LOOSE  # noqa: E402

WF = ".github/workflows"
T_WARN = {"artifact_v3": date(2024, 4, 16), "set_output": date(2022, 10, 11)}
BOT_RE = re.compile(r"\[bot\]|dependabot|renovate|github-actions|pre-commit-ci|mergify", re.I)
BOT_CREDIT_RE = re.compile(r"(co-authored-by|signed-off-by):.*(dependabot|renovate|\[bot\])", re.I)
RENOVATE_FILES = ["renovate.json", "renovate.json5", ".renovaterc", ".renovaterc.json",
                  ".github/renovate.json", ".github/renovate.json5", ".gitlab/renovate.json"]
# An author counts as core if, in the year before the migration, on the default branch they
#   - authored at least CORE_MIN_COMMITS commits, or
#   - authored at least CORE_MIN_SHARE of all commits (and at least 3), which catches owners
#     of projects with little activity, or
#   - authored a merge commit (they could merge), or
# if the migration PR was merged from a branch of the repository itself (write access).
CORE_MIN_COMMITS = 10
CORE_MIN_SHARE = 0.10


def git(repo, *args, retries=3):
    """Run git; retry transient failures (e.g. lazy fetches), then fail loudly."""
    for _ in range(retries):
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {r.stderr.strip()[:300]}")


def blob(repo, sha, path):
    r = subprocess.run(["git", "-C", repo, "show", f"{sha}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def warn_commit(repo, t_warn):
    return git(repo, "rev-list", "-1", "--first-parent", f"--before={t_warn.isoformat()}", "HEAD")


def rq3(repo, t_warn):
    sha = warn_commit(repo, t_warn)
    dep = (blob(repo, sha, ".github/dependabot.yml") or blob(repo, sha, ".github/dependabot.yaml") or "")
    dependabot_actions = bool(re.search(r"package-ecosystem:\s*['\"]?github-actions", dep))
    renovate = any(blob(repo, sha, f) is not None for f in RENOVATE_FILES)
    since = (t_warn - timedelta(days=182)).isoformat()
    log = git(repo, "log", "HEAD", f"--since={since}", f"--until={t_warn.isoformat()}", "--format=%aE")
    emails = [l.lower() for l in log.splitlines() if l]
    wf = git(repo, "ls-tree", "--name-only", sha, f"{WF}/")
    return {
        "dependabot_actions": int(dependabot_actions), "renovate": int(renovate),
        "commits_6m": len(emails), "authors_6m": len(set(emails)),
        "workflow_files": len([l for l in wf.splitlines() if l]),
    }


def classify_author(repo, name, email, before):
    """bot | core | external, from the default branch history of the preceding year."""
    if BOT_RE.search(name) or BOT_RE.search(email):
        return "bot"
    since = (before - timedelta(days=365)).isoformat()
    until = (before - timedelta(days=1)).isoformat()
    who = {name.lower(), email.lower()}
    n = merges = total = 0
    for line in git(repo, "log", "HEAD", f"--since={since}", f"--until={until}",
                    "--format=%aN%x1f%aE%x1f%P").splitlines():
        a_name, a_email, parents = line.split("\x1f")
        total += 1
        if a_name.lower() in who or a_email.lower() in who:
            n += 1
            merges += len(parents.split()) > 1
    if n >= CORE_MIN_COMMITS or merges > 0 or (n >= 3 and n / total >= CORE_MIN_SHARE):
        return "core"
    return "external"


def rq4(repo, event, mig_sha, owner):
    full = git(repo, "rev-parse", mig_sha)
    parents = git(repo, "rev-list", "--parents", "-n1", full).split()[1:]
    change = full
    if len(parents) > 1:
        # The latest commit brought in by the merge whose diff removed a deprecated line.
        # (-G with the loose pattern only narrows the candidates; the strict pattern decides.)
        inner = git(repo, "log", "--no-merges", "--format=%H", "-G", LOOSE[event],
                    f"{parents[0]}..{full}", "--", WF).splitlines()
        for c in inner:
            diff = git(repo, "diff", "--unified=0", f"{c}^", c, "--", WF)
            if any(l.startswith("-") and not l.startswith("---") and DEPRECATED_PY[event].search(l[1:])
                   for l in diff.splitlines()):
                change = c
                break
    name, email, day, body = git(repo, "log", "-1", "--format=%aN%x1f%aE%x1f%as%x1f%B", change).split("\x1f", 3)
    merged_by = git(repo, "log", "-1", "--format=%aN", full) if change != full else ""
    kind = classify_author(repo, name, email, date.fromisoformat(day))
    # "Merge pull request #N from <owner>/<branch>": a branch of the repository itself
    # means the author had write access.
    m = re.match(r"Merge pull request #\d+ from ([^/\s]+)/", git(repo, "log", "-1", "--format=%s", full))
    same_repo_branch = bool(m and m.group(1).lower() == owner.lower())
    if kind == "external" and same_repo_branch:
        kind = "core"
    return {
        "change_commit": change[:10], "is_merge": int(len(parents) > 1), "author": name,
        "author_kind": kind, "merged_by": merged_by,
        "bot_initiated": int(kind == "bot" or bool(BOT_CREDIT_RE.search(body))),
        "same_repo_branch": int(same_repo_branch),
    }


def work(item):
    clones, r = item
    repo = os.path.join(clones, r["repo"].replace("/", "__", 1))
    out = {"repo": r["repo"], "event": r["event"], "category": r["category"],
           "days_from_warning": r["days_from_warning"], "occurrences": r["exposed_at_warning"]}
    out.update(rq3(repo, T_WARN[r["event"]]))
    if r["migration_commit"]:
        out.update(rq4(repo, r["event"], r["migration_commit"], r["repo"].split("/")[0]))
    return out


def main(clones, scan, out_path, frame=None):
    rows = [r for r in csv.DictReader(open(scan), delimiter="\t")
            if r["event"] in T_WARN and r["exposed_at_warning"] not in ("0", "")]
    meta = {}
    if frame:
        for m in csv.DictReader(open(frame), delimiter="\t"):
            meta[m["repo"].lower()] = m
    with ProcessPoolExecutor(max_workers=12) as ex:
        res = list(ex.map(work, [(clones, r) for r in rows]))
    for o in res:
        m = meta.get(o["repo"].lower())
        if m:
            created = date.fromisoformat(m["created"][:10])
            o.update({"stars": m["stars"], "contributors": m["contributors"], "commits": m["commits"],
                      "language": m["language"],
                      "age_years": f"{(T_WARN[o['event']] - created).days / 365.25:.1f}"})
    cols = ["repo", "event", "category", "days_from_warning", "occurrences", "stars", "contributors",
            "commits", "language", "age_years", "dependabot_actions", "renovate", "commits_6m",
            "authors_6m", "workflow_files", "change_commit", "is_merge", "author", "author_kind",
            "merged_by", "same_repo_branch", "bot_initiated"]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for o in sorted(res, key=lambda o: (o["repo"].lower(), o["event"])):
            w.writerow(o)
    print(f"{len(res)} pairs written to {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:])
