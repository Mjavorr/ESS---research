# Warn or Break? How Open-Source Projects Respond to Platform-Enforced Deprecations in GitHub Actions

Mining software repositories study (ESS course project). GitHub periodically deprecates
platform components that workflows depend on (official action versions, workflow commands,
JavaScript runtimes, runner images), under different regimes: some deprecations end with a
hard cutoff that makes outdated workflows fail, some cutoffs are announced and then withdrawn,
and some are handled by silently forcing a newer runtime. We treat these events as natural
experiments and mine the workflow histories of public repositories to see whether projects
migrate in response to warnings or only once their CI breaks.

## Research questions

- **RQ1:** When do projects migrate away from deprecated GitHub Actions components: during the warning period, after the enforcement date, or never?
- **RQ2:** How does the deprecation regime (hard cutoff, withdrawn cutoff, automatic runtime shim) affect the speed and extent of migration?
- **RQ3:** Which project characteristics (e.g., activity, number of maintainers, use of Dependabot or Renovate) are associated with timely migration?
- **RQ4:** Who performs the migrations: dependency bots, core maintainers, or external contributors?
- **RQ5:** What problems do developers encounter when migrating?

The events studied, their dates and the detection rules are in [`docs/events.md`](docs/events.md).

## Repository layout

```
scripts/
  sample_repos.py       reproducible random order of the SEART sampling frame
  clone_repos.sh        blobless full-history clones of the repositories in a list
  scan_migrations.py    exposure at T_warn and migration commit per repository and event
  collect_evidence.py   diff + commit message of each migration, for manual validation
data/sample/            main study sample (random)
  seart_export_2026-10-28.csv.gz   SEART GitHub Search export (sampling frame, 22,608 repos)
  frame_shuffled.tsv    frame without archived repos (22,215), shuffled with seed 20261028
  batch1.txt            first 500 repos of the shuffled frame (the sample)
  unavailable.tsv       sampled repos that could not be cloned
  scan_all.tsv          scanner output for the 499 cloned repos
  exposed.tsv           the 123 repos exposed to at least one event
  validation_subsample.tsv  manual validation of 50 random exposed cases (25 per event)
data/pilot/             earlier hand-picked pilot (90 popular repos), kept for reference
  repos.txt, scan_all.tsv, exposed.tsv
  validation.tsv        manual validation of every exposed pilot case (43 rows)
docs/
  events.md             event catalogue, detection rules, changelog sources
paper/                  the paper (to come)
```

## Sample

Sampling frame: [SEART GitHub Search](https://seart-ghs.si.usi.ch), exported on 2026-10-28 with

| Filter | Value |
| --- | --- |
| Created | before 2022-01-01 (exists through every event) |
| Last commit | on or after 2025-02-01 (active after the latest cutoff) |
| Stars | ≥ 500 |
| Contributors | ≥ 10 |
| Commits | ≥ 500 |
| Forks | excluded |

The export holds 22,608 repositories; 393 archived ones are dropped. `scripts/sample_repos.py`
shuffles the rest with a fixed seed, and the sample is a prefix of that order, so a later batch
extends the sample instead of replacing it. The first 500 were cloned (1 no longer exists).

## Reproducing

Requirements: `git` (tested with 2.43) and Python 3.10+ (standard library only).

```bash
python3 scripts/sample_repos.py data/sample/seart_export_2026-10-28.csv.gz frame.tsv   # = data/sample/frame_shuffled.tsv
tail -n +2 frame.tsv | head -500 | cut -f2 > batch1.txt                                # = data/sample/batch1.txt
scripts/clone_repos.sh batch1.txt clones 12
python3 scripts/scan_migrations.py clones scan.tsv
python3 scripts/collect_evidence.py clones data/sample/exposed.tsv > evidence.txt
```

Results depend on the state of the repositories at collection time: the sample was cloned and
scanned on 2026-10-28. The scanner only reads history up to each clone's `HEAD`, so re-running on
fresh clones may add later migrations. Two consecutive scans of the same clones gave identical output.

## Status (2026-10-28)

Random sample, 499 repositories:

| | artifact actions v1–v3 | `set-output` |
| --- | --- | --- |
| Exposed at first warning | 84 | 57 |
| Migrated before enforcement / announced cutoff | 30 | 25 |
| Migrated after enforcement / announced cutoff | 49 | 23 |
| Not migrated (as of collection) | 5 | 9 |
| Median days from first warning to migration | 211 | 200 |

- 123 repositories exposed to at least one event, 18 to both.
- Manual validation of 50 random exposed cases: detection correct in all 50. Two of them revealed
  that repositories mixing v2 and v3 were judged by the v3 cutoff only; the scanner now applies
  each version group's own cutoff (3 repositories in the sample changed category).
- The hand-picked pilot (90 popular repositories) looked very different: only 5 of 15 artifact
  migrations happened after enforcement, against 49 of 79 in the random sample.

## Known limitations

- The frame (≥ 500 stars, ≥ 10 contributors, ≥ 500 commits) covers established, collaborative
  projects only; results may not hold for small or personal repositories.
- "Default branch" is approximated by the first-parent history of today's `HEAD`. When a project
  later switched its default branch (e.g. expressjs/express from 4.x to 5.x), the migration date
  can be too late; in the pilot such cases are corrected manually in `validation.tsv`.
- A fix authored on a development or maintenance branch counts only once it reaches the default branch.
- For merge commits, the commit author is the person who merged, which hides bots (e.g. a merged
  Dependabot PR); real authors will be recovered via the GitHub API.
- `set-output` is only detected when used directly in workflow files, not inside third-party actions.
- Repositories that never migrated are censored at collection time, not treated as non-migrants.
- Failures quoted before the v3 cutoff suggest brownouts; see `docs/events.md`.
