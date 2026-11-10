# RQ5 codebook: how projects migrate and what goes wrong

Unit of analysis: one exposed (repository, event) pair of the random sample (148 pairs).
Material per pair (`scripts/collect_rq5.py`): the commit message of the change and of the merge
that brought it in, the workflow diff of the migration, follow-up commits within 30 days that touched
the same workflow files and mention artifacts/outputs, and, for pairs that never migrated, the
remaining occurrences with their context. Codes are in `data/sample/rq5_coding.tsv`.

The codes were derived inductively while reading the material of the hand-picked set and of a first
random subsample, then applied to all 148 pairs. Each pair gets one change type, one trigger and one
or more problem codes.

## Change type (one per pair)

| Code | Definition | Example |
| --- | --- | --- |
| `bump` | The deprecated reference or command is replaced one to one (new version, or `>> $GITHUB_OUTPUT`); nothing else in the workflow had to change for it. | `upload-artifact@v3` → `@v4` |
| `adapt` | Replaced, plus changes the new behaviour required: unique artifact names, a merge job or `merge-multiple`, `include-hidden-files`, `overwrite`, or restructuring to work around the environment. | qiskit-aer: per-matrix names + `merge-multiple` |
| `remove` | The step or workflow using the deprecated component is deleted, not replaced. | zenorogue/hyperrogue: "removed Android CI for now" |
| `replace` | A different mechanism takes over (built-in cache of `setup-*`, another action, a rewritten pipeline). | actions/cache: `setup-node` cache instead of `set-output` |
| `none` | Not migrated by the data-collection date. | |

## Trigger (one per migrated pair; from the commit and PR messages)

Checked in this order; the first that applies is used.

| Code | Definition |
| --- | --- |
| `bot` | Authored or initiated by a dependency bot (Dependabot, Renovate). |
| `breakage` | The message reports a failing build or quotes the failure ("fix build", "fix CI", error text). |
| `deprecation` | The message names the deprecation, its warning, its end of life or the changelog. |
| `targeted` | A change aimed at the deprecated component ("update upload-artifact to v4") without a stated reason. |
| `routine` | A general update of actions or dependencies ("bump actions", "update ci", periodic upkeep). |
| `incidental` | The migration happens inside unrelated work (feature, refactoring, rewrite, removal). |

## Problems (one or more per pair)

| Code | Definition | Example |
| --- | --- | --- |
| `incompatibility` | The new version behaves differently and forced extra changes or a follow-up repair. | panda-re/panda: rollback, then "unable to upload same file name twice" |
| `environment` | The runner, container or OS could not run the new version (e.g. node20 needs a newer glibc). | draios/sysdig-inspect: build moved to `docker run` |
| `regression` | The migration introduced an error that a later commit fixed. | lightspark: unclosed `${...}`, fixed 81 days later |
| `multiline` | Multi-line values: `set-output` accepted them URL-encoded, `$GITHUB_OUTPUT` needs a delimiter. | lucide: "Try fix changelog output" |
| `deferral` | An explicit decision to keep the deprecated version (comment, pin, rollback). | mcneel/rhino3dm: "needs to stay this version until we upgrade this os" |
| `none` | No problem visible in the material. | |

## Reliability

All pairs were coded by one coder. A second coder independently codes a stratified random subset
(`data/sample/rq5_second_coder.tsv`, codes hidden); agreement is reported as Cohen's kappa per
dimension.
