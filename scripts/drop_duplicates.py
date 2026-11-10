#!/usr/bin/env python3
"""Remove repositories listed in data/sample/duplicates.tsv from TSV files (in place).

The SEART export can list a renamed repository under its old and its new name; after
cloning, both names point to the same repository (identical HEAD). Only the current
name is kept, so the repository is counted once.

Lines are filtered as plain text (split on tabs), so everything else in the files,
including quotes and line endings, stays byte-for-byte the same.

Usage: python3 scripts/drop_duplicates.py <duplicates.tsv> <file.tsv> [<file.tsv> ...]
"""
import sys

with open(sys.argv[1]) as f:
    lines = f.read().splitlines()
col = lines[0].split("\t").index("repo")
dups = {l.split("\t")[col].lower() for l in lines[1:] if l}

for path in sys.argv[2:]:
    with open(path, newline="") as f:
        rows = f.read().splitlines(keepends=True)
    col = rows[0].rstrip("\r\n").split("\t").index("repo")
    kept = rows[:1] + [r for r in rows[1:] if r.split("\t")[col].lower() not in dups]
    with open(path, "w", newline="") as f:
        f.writelines(kept)
    print(f"{path}: removed {len(rows) - len(kept)} rows")
