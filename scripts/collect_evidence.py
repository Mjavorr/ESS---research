#!/usr/bin/env python3
"""Collect evidence for manual validation of each detected migration.

For every (repo, event) row of exposed_repos.tsv with a migration commit, prints:
  - whether the commit is a merge, and if so the non-merge commits it brought in
    that touched matching lines (real authors),
  - removed lines matching the deprecated pattern, the corresponding added lines,
  - workflow files deleted in the commit,
  - the commit message.
For rows with no migration, prints the remaining occurrences at HEAD.

Usage: python3 scripts/collect_evidence.py <clones_dir> <exposed.tsv> > evidence.txt
"""
import csv
import re
import subprocess
import sys

PAT = {
    "artifact_v3": re.compile(r"^[^#]*uses:\s*['\"]?actions/(upload|download)-artifact@v[123]([^0-9.]|$)"),
    "set_output": re.compile(r"^[^#]*::(set-output|save-state)"),
}
LOOSE = {"artifact_v3": r"actions/(upload|download)-artifact@v[123]",
         "set_output": r"::(set-output|save-state)"}
ADDED_HINT = {"artifact_v3": re.compile(r"(upload|download)-artifact|actions/cache|uses:"),
              "set_output": re.compile(r"GITHUB_OUTPUT|GITHUB_STATE|setOutput|set-output")}
WF = ".github/workflows"


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


def main(clones, tsv):
    for r in csv.DictReader(open(tsv), delimiter="\t"):
        if r["exposed_at_warning"] == "0":
            continue
        repo_dir = f"{clones}/{r['repo'].replace('/', '__', 1)}"
        ev = r["event"]
        print("=" * 100)
        print(f"{r['repo']} | {ev} | {r['category']} | {r['days_from_warning']} d | {r['migration_date']}")
        sha = r["migration_commit"]
        if not sha:
            print("REMAINING AT HEAD:")
            print(git(repo_dir, "grep", "-nE", LOOSE[ev], "HEAD", "--", WF)[:1500])
            continue
        parents = git(repo_dir, "rev-list", "--parents", "-n1", sha).split()[1:]
        print(f"commit {sha}  parents={len(parents)}")
        if len(parents) > 1:
            inner = git(repo_dir, "log", "--no-merges", "--format=  %h %cs %an | %s",
                        "-G", LOOSE[ev], f"{parents[0]}..{sha}", "--", WF)
            print("INNER COMMITS touching pattern:\n" + inner.strip()[:1500])
        diff = git(repo_dir, "diff", "--unified=0", f"{sha}^1", sha, "--", WF)
        removed = [l[1:].strip() for l in diff.splitlines()
                   if l.startswith("-") and not l.startswith("---") and PAT[ev].search(l[1:])]
        added = [l[1:].strip() for l in diff.splitlines()
                 if l.startswith("+") and not l.startswith("+++") and ADDED_HINT[ev].search(l[1:])]
        deleted = git(repo_dir, "diff", "--name-only", "--diff-filter=D", f"{sha}^1", sha, "--", WF).split()
        print(f"REMOVED ({len(removed)}):")
        for l in removed[:8]:
            print("   -", l[:150])
        print(f"ADDED related ({len(added)}):")
        for l in added[:8]:
            print("   +", l[:150])
        if deleted:
            print("DELETED FILES:", deleted)
        msg = git(repo_dir, "log", "-1", "--format=%an <%ae>%n%B", sha).strip()
        print("MESSAGE:\n   " + "\n   ".join(msg.splitlines()[:14]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
