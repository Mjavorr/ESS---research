#!/usr/bin/env bash
# Clone (or update) every repository listed in a file as a blobless partial clone.
#
# Full commit history is required: shallow clones (--depth / --shallow-since) can
# cut the first-parent history of the default branch, which makes the scanner
# miss exposures. --filter=blob:none keeps clones small; file contents are
# fetched lazily when the scanner reads them.
#
# Usage: scripts/clone_repos.sh <repos.txt> <clones_dir> [parallel_jobs]
#   repos.txt: one "owner/name" per line
set -euo pipefail

list=$1
dest=$2
jobs=${3:-8}
mkdir -p "$dest"

clone_one() {
  repo=$1; dest=$2
  dir="$dest/${repo/\//__}"
  if [ -d "$dir/.git" ]; then
    if [ -f "$dir/.git/shallow" ]; then
      git -C "$dir" fetch -q --unshallow --filter=blob:none origin
    fi
    echo "ok   $repo (existing)"
  elif git clone -q --filter=blob:none --no-checkout "https://github.com/$repo.git" "$dir"; then
    echo "ok   $repo"
  else
    echo "FAIL $repo"
  fi
}
export -f clone_one

grep -v '^\s*$' "$list" | xargs -P "$jobs" -I{} bash -c 'clone_one "$@"' _ {} "$dest"
