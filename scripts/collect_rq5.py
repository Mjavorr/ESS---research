#!/usr/bin/env python3
"""RQ5: collect the material for coding migration problems.

For every exposed (repository, event) pair in features.tsv this writes a readable
evidence block and a row of automatic flags that help (but do not replace) the
manual coding:

  migrated pairs
    - the commit message of the change and of the merge that brought it in
    - the workflow diff of the migration (deprecated lines removed, lines added)
    - adaptation flags: added lines beyond a plain version bump, e.g.
        artifact actions: merge-multiple, overwrite, upload-artifact/merge, pattern,
                          artifact names made unique (name: ...${{ ... }})
        set-output:       multi-line heredoc into $GITHUB_OUTPUT, PowerShell syntax,
                          @actions/core setOutput, $GITHUB_STATE
    - follow-up commits within 30 days that touched the same workflow files and
      mention artifacts/outputs (possible repairs of the migration)
  pairs that never migrated
    - the remaining occurrences with two lines of context (comments such as
      "TODO" or "cannot upgrade" explain deliberate deferrals)

Usage:
  python3 scripts/collect_rq5.py <clones_dir> <scan.tsv> <features.tsv> <out_evidence.txt> <out_flags.tsv>
"""
import csv
import os
import re
import subprocess
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patterns import DEPRECATED_PY, LOOSE  # noqa: E402

WF = ".github/workflows"
DEPRECATED = DEPRECATED_PY
ADAPT = {
    "artifact_v3": [
        ("merge_multiple", re.compile(r"merge-multiple\s*:")),
        ("overwrite", re.compile(r"overwrite\s*:")),
        ("merge_action", re.compile(r"upload-artifact/merge@")),
        ("pattern", re.compile(r"^\s*pattern\s*:")),
        ("hidden_files", re.compile(r"include-hidden-files\s*:")),
        ("unique_name", re.compile(r"^\s*name\s*:.*\$\{\{")),
    ],
    "set_output": [
        ("heredoc", re.compile(r"<<\s*['\"]?\w*EOF|<<.*GITHUB_OUTPUT|EOF.*>>\s*\"?\$GITHUB_OUTPUT")),
        ("powershell", re.compile(r"\$env:GITHUB_OUTPUT|Out-File|Add-Content", re.I)),
        ("js_core", re.compile(r"core\.setOutput|GITHUB_OUTPUT.*appendFileSync|appendFileSync.*GITHUB_OUTPUT")),
        ("state", re.compile(r"GITHUB_STATE")),
    ],
}
FOLLOWUP = {"artifact_v3": r"[Aa]rtifact|ARTIFACT", "set_output": r"[Oo]utput|OUTPUT"}


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {r.stderr.strip()[:300]}")
    return r.stdout


def migrated_block(repo, event, scan_row, feat):
    mig = git(repo, "rev-parse", scan_row["migration_commit"]).strip()
    change = git(repo, "rev-parse", feat["change_commit"]).strip()
    diff = git(repo, "diff", "--unified=1", f"{mig}^1", mig, "--", WF)
    removed = [l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
    added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    dep_removed = [l for l in removed if DEPRECATED[event].search(l)]
    flags = sorted({name for name, rx in ADAPT[event] for l in added if rx.search(l)})
    files = [f for f in git(repo, "diff", "--name-only", f"{mig}^1", mig, "--", WF).split() if f]
    deleted = [f for f in git(repo, "diff", "--name-only", "--diff-filter=D", f"{mig}^1", mig, "--", WF).split() if f]
    day = date.fromisoformat(scan_row["migration_date"])
    follow = ""
    if files:
        follow = git(repo, "log", "--first-parent", "--format=%h %cs %an | %s", "-G", FOLLOWUP[event],
                     f"--since={(day + timedelta(days=1)).isoformat()}",
                     f"--until={(day + timedelta(days=30)).isoformat()}", "HEAD", "--", *files).strip()
    msg = git(repo, "log", "-1", "--format=%B", change).strip()
    merge_msg = git(repo, "log", "-1", "--format=%s", mig).strip() if change != mig else ""
    text = [f"author: {feat['author']} ({feat['author_kind']})  phase/category: {scan_row['category']}",
            f"files changed: {len(files)}  deleted: {deleted or '-'}  flags: {flags or '-'}",
            "MESSAGE:", *("   " + l for l in msg.splitlines()[:12])]
    if merge_msg:
        text.append(f"MERGED BY: {merge_msg}")
    text.append(f"REMOVED deprecated ({len(dep_removed)}):")
    text += ["   - " + l.strip()[:150] for l in dep_removed[:6]]
    text.append(f"ADDED ({len(added)} lines, first 20 non-empty):")
    text += ["   + " + l.strip()[:150] for l in [a for a in added if a.strip()][:20]]
    text.append("FOLLOW-UPS within 30 days on the same files:")
    text += ["   " + l for l in (follow.splitlines()[:6] or ["-"])]
    return text, {"adaptation_flags": ",".join(flags), "files_changed": len(files),
                  "files_deleted": len(deleted), "deprecated_removed": len(dep_removed),
                  "lines_added": len(added), "followups_30d": len(follow.splitlines()) if follow else 0}


def never_block(repo, event):
    out = git(repo, "grep", "-n", "-E", "-B2", "-A1", LOOSE[event], "HEAD", "--", WF)
    lines = [l.replace("HEAD:", "", 1) for l in out.splitlines()][:24]
    return ["REMAINING at HEAD (with context):"] + ["   " + l[:170] for l in lines], {}


def main(clones, scan, features, out_txt, out_tsv):
    scan_rows = {(r["repo"], r["event"]): r for r in csv.DictReader(open(scan), delimiter="\t")}
    feats = list(csv.DictReader(open(features), delimiter="\t"))
    blocks, rows = [], []
    for i, f in enumerate(feats, 1):
        key = (f["repo"], f["event"])
        repo = os.path.join(clones, f["repo"].replace("/", "__", 1))
        s = scan_rows[key]
        if s["migration_commit"]:
            text, flags = migrated_block(repo, f["event"], s, f)
        else:
            text, flags = never_block(repo, f["event"])
        case = f"C{i:03d}"
        blocks.append("=" * 100)
        blocks.append(f"{case} | {f['repo']} | {f['event']} | {s['migration_date'] or 'never'} | "
                      f"https://github.com/{f['repo']}/commit/{s['migration_commit']}" if s["migration_commit"]
                      else f"{case} | {f['repo']} | {f['event']} | never | https://github.com/{f['repo']}/tree/HEAD/{WF}")
        blocks += text
        rows.append({"case": case, "repo": f["repo"], "event": f["event"],
                     "migrated": int(bool(s["migration_commit"])), **flags})
    with open(out_txt, "w") as fh:
        fh.write("\n".join(blocks) + "\n")
    cols = ["case", "repo", "event", "migrated", "adaptation_flags", "files_changed", "files_deleted",
            "deprecated_removed", "lines_added", "followups_30d"]
    with open(out_tsv, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, delimiter="\t", restval="")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} cases -> {out_txt}, {out_tsv}")


if __name__ == "__main__":
    main(*sys.argv[1:])
