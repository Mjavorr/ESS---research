#!/usr/bin/env python3
"""Draw a reproducible simple random sample of repositories from a SEART export.

The sampling frame is the SEART GitHub Search export (CSV, optionally gzipped).
Archived repositories are dropped (they can no longer migrate). The remaining
frame is shuffled with a fixed seed and written out in that order, so taking
the first N lines is a simple random sample of size N, and a later, larger
batch extends the earlier one instead of replacing it.

Usage:
  python3 scripts/sample_repos.py <seart_export.csv[.gz]> <out_frame.tsv> [seed]

Output columns: order, repo, stars, contributors, commits, language, created, last_commit
"""
import csv
import gzip
import random
import sys

KEEP = [("name", "repo"), ("stargazers", "stars"), ("contributors", "contributors"),
        ("commits", "commits"), ("mainLanguage", "language"), ("createdAt", "created"),
        ("lastCommit", "last_commit")]


def main(src, out, seed=20261028):
    opener = gzip.open if src.endswith(".gz") else open
    with opener(src, "rt", encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["isArchived"] != "true"]
    rows.sort(key=lambda r: r["name"].lower())  # independent of export order
    random.Random(seed).shuffle(rows)
    with open(out, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["order"] + [new for _, new in KEEP])
        for i, r in enumerate(rows, 1):
            w.writerow([i] + [r[old] for old, _ in KEEP])
    print(f"{len(rows)} repositories in frame (archived excluded), seed {seed}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(int(a) for a in sys.argv[3:4]))
