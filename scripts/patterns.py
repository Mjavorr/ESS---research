"""Shared detection patterns for the deprecated components (one definition for all scripts).

Artifact actions v1-v3 can be referenced in three ways, all of which count:
  - a major tag:            actions/upload-artifact@v3
  - a minor/patch tag etc.: actions/upload-artifact@v3.1.3, @v2-preview, @v3-node20
  - a commit pin:           actions/upload-artifact@a8a3f3ad30e3422c9c7b888a15615d19a852ae32
    (the commits of every v1-v3 tag of the official actions, data/deprecated_action_commits.tsv)
Only the official `actions/` owner counts and commented-out lines are ignored.

Each regex is offered in two dialects: POSIX ERE for `git grep -E` (`ere`) and Python (`py`).
"""
import csv
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
COMMITS_FILE = os.path.join(_HERE, "..", "data", "deprecated_action_commits.tsv")


def _commits(group):
    with open(COMMITS_FILE) as f:
        return sorted({r["commit"] for r in csv.DictReader(f, delimiter="\t") if r["group"] in group})


def _artifact(groups):
    majors = "".join(sorted({{"v1_v2": "12", "v3": "3"}[g] for g in groups}))
    tag = rf"v[{majors}]([.-][0-9A-Za-z]+)*"
    pins = "|".join(_commits(groups))
    ref = f"({tag}|{pins})" if pins else tag
    ere = rf"^[^#]*uses:[[:space:]]*['\"]?actions/(upload|download)-artifact@{ref}([^0-9A-Za-z.-]|$)"
    return {"ere": ere, "py": ere.replace("[[:space:]]", r"\s")}


ARTIFACT_ALL = _artifact({"v1_v2", "v3"})
ARTIFACT_V12 = _artifact({"v1_v2"})
ARTIFACT_V3 = _artifact({"v3"})
SET_OUTPUT = {"ere": r"^[^#]*::(set-output|save-state)", "py": r"^[^#]*::(set-output|save-state)"}

# Loose patterns: used with `git log -G` to find candidate commits (no anchors, no comment filter).
LOOSE = {
    "artifact_v3": r"actions/(upload|download)-artifact@",
    "set_output": r"::(set-output|save-state)",
}

DEPRECATED_PY = {"artifact_v3": re.compile(ARTIFACT_ALL["py"]), "set_output": re.compile(SET_OUTPUT["py"])}
