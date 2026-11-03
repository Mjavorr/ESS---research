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
  analyze_timing.py     RQ1/RQ2: phases, Kaplan-Meier curves, log-rank test, figures
  extract_features.py   RQ3/RQ4: project characteristics at T_warn, author of each migration
  analyze_factors.py    RQ3/RQ4: timely vs late comparison, Cox model, authorship shares
results/                tables and figures produced by analyze_timing.py (sample_* and handpicked_*)
data/sample/            main study sample (random)
  seart_export_2026-10-28.csv.gz   SEART GitHub Search export (sampling frame, 22,608 repos)
  frame_shuffled.tsv    frame without archived repos (22,215), shuffled with seed 20261028
  batch1.txt            first 500 repos of the shuffled frame (the sample)
  unavailable.tsv       sampled repos that could not be cloned
  scan_all.tsv          scanner output for the 499 cloned repos
  exposed.tsv           the 123 repos exposed to at least one event
  validation_subsample.tsv  manual validation of 50 random exposed cases (25 per event)
  features.tsv          RQ3/RQ4 variables per exposed (repository, event) pair
data/handpicked/        hand-picked set of 90 popular repos used to develop and validate the detection rules
  repos.txt, scan_all.tsv, exposed.tsv
  validation.tsv        manual validation of every exposed case in this set (43 rows)
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

Requirements: `git` (tested with 2.43) and Python 3.10+. The collection scripts use only the
standard library; the analysis needs `pip install -r requirements.txt`.

```bash
python3 scripts/sample_repos.py data/sample/seart_export_2026-10-28.csv.gz frame.tsv   # = data/sample/frame_shuffled.tsv
tail -n +2 frame.tsv | head -500 | cut -f2 > batch1.txt                                # = data/sample/batch1.txt
scripts/clone_repos.sh batch1.txt clones 12
python3 scripts/scan_migrations.py clones scan.tsv
python3 scripts/collect_evidence.py clones data/sample/exposed.tsv > evidence.txt
python3 scripts/analyze_timing.py data/sample/scan_all.tsv results sample 2026-10-28
python3 scripts/extract_features.py clones data/sample/scan_all.tsv features.tsv data/sample/frame_shuffled.tsv
python3 scripts/analyze_factors.py data/sample/scan_all.tsv data/sample/features.tsv results sample 2026-10-28
```

Results depend on the state of the repositories at collection time: the sample was cloned and
scanned on 2026-10-28. The scanner only reads history up to each clone's `HEAD`, so re-running on
fresh clones may add later migrations. Two consecutive scans of the same clones gave identical output.

## Status (2026-11-02)

Random sample, 499 repositories, 123 exposed to at least one event (18 to both). Time is measured
from each deprecation notice; repositories that never migrated are censored at their last commit
or at data collection, whichever is earlier.

**RQ1, phases** (`results/sample_phases.tsv`):

| Artifact actions v1–v3 (n = 84) | | `set-output` (n = 57) | |
| --- | --- | --- | --- |
| before any breakage | 26 (31%) | before the announced cutoff | 25 (44%) |
| during the v3 brownouts | 4 (5%) | between cutoff date and postponement | 1 (2%) |
| after the cutoff (CI broken) | 49 (58%) | after the postponement | 22 (39%) |
| not migrated | 5 (6%) | not migrated | 9 (16%) |

**RQ2, survival** (`results/sample_survival.tsv`, `results/sample_km.pdf`):

- Kaplan-Meier median time to migration: 224 days (artifact) vs 384 days (`set-output`).
- Migrated within one year: 85% (artifact) vs 49% (`set-output`); log-rank χ² = 12.2, p < 0.001.
- `set-output` migrates faster at first (19% within 30 days vs 8%), then flattens after the cutoff is
  postponed; artifact migrations pile up around the brownouts and the cutoff (`results/sample_weekly.pdf`).
- The 13 repositories that migrated away from both took less time for the artifact actions
  (Wilcoxon signed-rank p = 0.011).

Manual validation of 50 random exposed cases: detection correct in all 50. Two of them revealed that
repositories mixing v2 and v3 were judged by the v3 cutoff only; the scanner now applies each version
group's own cutoff (3 repositories changed category).

**RQ3, which projects migrate in time** (`results/sample_rq3_*.tsv`; "in time" = before anything broke):

- Artifact actions: projects that migrated in time were more active before the warning (median 126 vs
  62 commits in the preceding 6 months, Mann-Whitney p = 0.013); in the Cox model each e-fold increase
  in prior activity raises the migration rate by 18% (HR 1.18, 95% CI 1.04–1.34).
- `set-output`: projects with Dependabot or Renovate configured migrated faster (HR 2.39, 95% CI
  1.21–4.72), although no `set-output` migration was made by a bot: the tools seem to mark projects
  that maintain their CI, not to do the work.
- Stars, contributors, age and the number of occurrences show no clear effect. With 18 descriptive
  tests, single p-values around 0.01 must be read with care.
- Only 5 of the 84 artifact-exposed repositories had Dependabot for Actions at the warning: projects
  with it had mostly moved to v4 before the deprecation and were never exposed.

**RQ4, who migrates** (`results/sample_rq4_authors.tsv`):

| | bot | core maintainer | external contributor |
| --- | --- | --- | --- |
| Artifact actions (79 migrations) | 4 (5%) | 57 (72%) | 18 (23%) |
| … before any breakage (26) | 3 | 15 | 8 |
| … after the cutoff (49) | 1 | 39 | 9 |
| `set-output` (48 migrations) | 0 | 45 (94%) | 3 (6%) |

Authors are classified from the default-branch history of the year before the migration: core if they
authored ≥ 10 commits, ≥ 10% of all commits (and ≥ 3), or a merge commit, or if the change was merged
from a branch of the repository itself; bots by name. For merge commits the author of the inner commit
that changed the deprecated lines is used.

The hand-picked set of 90 popular repositories behaves differently: 63% of its artifact migrations
happened before any breakage and the `set-output` median is 51 days (`results/handpicked_*`).

## Known limitations

- The frame (≥ 500 stars, ≥ 10 contributors, ≥ 500 commits) covers established, collaborative
  projects only; results may not hold for small or personal repositories.
- "Default branch" is approximated by the first-parent history of today's `HEAD`. When a project
  later switched its default branch (e.g. expressjs/express from 4.x to 5.x), the migration date
  can be too late; in the hand-picked set such cases are corrected manually in `data/handpicked/validation.tsv`.
- A fix authored on a development or maintenance branch counts only once it reaches the default branch.
- Author roles are inferred from git history, not from GitHub's author association (the API is not
  available to us): a core developer working from a fork with few commits may be labelled external.
  A branch inside the repository proves write access, a fork does not prove its absence.
- The Cox models' proportional-hazards assumption has not been tested yet.
- `set-output` is only detected when used directly in workflow files, not inside third-party actions.
- Repositories that never migrated are censored at collection time, not treated as non-migrants.
- The v3 brownouts lasted 1 to 8 hours each; a migration on a brownout day may still predate the failure.
