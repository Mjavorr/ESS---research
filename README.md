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
  clone_repos.sh        blobless full-history clones of the repositories in a list
  scan_migrations.py    exposure at T_warn and migration commit per repository and event
  collect_evidence.py   diff + commit message of each migration, for manual validation
data/pilot/
  repos.txt             90 hand-picked popular repositories (pilot only, not a random sample)
  scan_all.tsv          scanner output for all 90 repositories
  exposed.tsv           the 36 repositories exposed to at least one event
  validation.tsv        manual validation of every exposed case (43 rows)
docs/
  events.md             event catalogue with changelog sources
paper/                  the paper (to come)
```

## Reproducing the pilot

Requirements: `git` (tested with 2.43) and Python 3.10+ (standard library only).

```bash
scripts/clone_repos.sh data/pilot/repos.txt clones 8
python3 scripts/scan_migrations.py clones scan.tsv
python3 scripts/collect_evidence.py clones data/pilot/exposed.tsv > evidence.txt
```

Results depend on the state of the repositories at collection time. The pilot data was
collected on 2026-10-13 (clones) and re-scanned on full history on 2026-10-19. The scanner only reads history up
to each clone's `HEAD`, so re-running on fresh clones may add later migrations.

## Pilot status (2026-10-19)

- 90 repositories scanned, 36 exposed to at least one event (7 to both).
- Every exposed case was validated manually against its diff and commit message
  (`data/pilot/validation.tsv`); the detection was correct in all 43 cases.
- Median time from first warning to migration: 184 days for artifact actions v1–v3
  (5 of 15 migrations after enforcement), 31 days for `set-output` (22 of 25 before the announced cutoff).

## Known limitations

- The pilot sample is hand-picked and biased towards large, active projects.
- "Default branch" is approximated by the first-parent history of today's `HEAD`. When a project
  later switched its default branch (e.g. expressjs/express from 4.x to 5.x), the migration date
  can be too late; such cases are corrected manually in `validation.tsv`.
- For merge commits, the commit author is the person who merged; real authors are recovered in
  `validation.tsv` (and later via the GitHub API).
- `set-output` is only detected when used directly in workflow files, not inside third-party actions.
- Inactive repositories that never migrated must be treated as censored, not as non-migrants.
