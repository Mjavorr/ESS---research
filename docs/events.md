# Deprecation events

Platform-enforced deprecations studied so far. Dates come from the official GitHub changelog.

| Event | Regime | First warning (T_warn) | Enforcement (T_enforce) | Detection in workflow files |
| --- | --- | --- | --- | --- |
| Artifact actions v3 | hard cutoff | 2024-04-16 | announced for 2024-11-30, moved in October 2024 to 2025-01-30 (brownouts 2025-01-09/16/23) | `uses: actions/upload-artifact@v3`, `actions/download-artifact@v3` |
| Artifact actions v1, v2 | hard cutoff | 2024-02-13 (own notice); 2024-04-16 used as T_warn | announced for 2024-06-30; jobs actually fail from early September 2024 (first public reports 2024-09-06) | same, with `@v1` / `@v2` |
| `set-output` / `save-state` workflow commands | announced cutoff, later withdrawn | 2022-10-11 | announced for 2023-05-31; postponed indefinitely on 2023-07-24 | `::set-output` / `::save-state` in `run:` steps |

Sources:

- [Deprecation notice: v1 and v2 of the artifact actions](https://github.blog/changelog/2024-02-13-deprecation-notice-v1-and-v2-of-the-artifact-actions/) (2024-02-13): "we will be deprecating v1 and v2 of actions/upload-artifact, actions/download-artifact, and related npm packages on June 30, 2024".
- [Deprecation notice: v3 of the artifact actions](https://github.blog/changelog/2024-04-16-deprecation-notice-v3-of-the-artifact-actions/) (2024-04-16): the page now reads "Starting January 30th, 2025, GitHub Actions customers will no longer be able to use v3"; v1 and v2 deprecation "scheduled to take place on June 30, 2024". The original date for v3 was November 30, 2024: the README notice added to actions/upload-artifact on 2024-04-16 says "actions/upload-artifact@v3 is scheduled for deprecation on **November 30, 2024**", and projects quoted that date until early October 2024 (e.g. github/codeql-action, 2024-10-02). By 2024-10-25 (community discussion #142581) and in the changelog of 2024-11-05 the date is January 30, 2025.
- [Notice of breaking changes for GitHub Actions](https://github.blog/changelog/2024-11-05-notice-of-breaking-changes-for-github-actions/) (2024-11-05): "Artifact actions v3 will be closing down by January 30, 2025", with the brownout schedule.
- v1/v2 enforcement: no announcement of a delay was found, but runs kept working after 2024-06-30. The earliest public failure reports with GitHub's error ("This request has been automatically failed because it uses a deprecated version of `actions/upload-artifact: v2`") are [Evergreen Launchpad bug #2079835](https://bugs.launchpad.net/evergreen/+bug/2079835) (2024-09-06) and [reactjs/react.dev#7148](https://github.com/reactjs/react.dev/issues/7148) (2024-09-09); more followed in the next days (e.g. codecov/codecov-action#1570, 2024-09-16). Our sample agrees: 11 of 35 v1/v2 groups disappeared within 14 days after 2024-09-06, only 4 in the ten weeks between 2024-06-30 and then.
- [GitHub Actions: Deprecating save-state and set-output commands](https://github.blog/changelog/2022-10-11-github-actions-deprecating-save-state-and-set-output-commands/) (2022-10-11): planned to "fully disable them on 31st May 2023"; update of 2023-07-24: "Our telemetry shows significant usage of these commands so we have decided to postpone the removal."

## Detection rules

- Commented-out lines (`#` before the match) are ignored.
- Artifact actions: only the official `actions/` owner counts (e.g. `dawidd6/action-download-artifact` does not).
- A repository is **exposed** if the default branch had at least one active occurrence at T_warn.
- The default branch at T_warn is the first-parent ancestor of today's `HEAD` with commit date before T_warn.
- **Migration** = the earliest first-parent commit on the default branch after which no occurrence remains.
- T_warn for the artifact actions is 2024-04-16, the day from which all three versions were deprecated
  (the v1/v2 notice of 2024-02-13 is earlier; repositories that dropped all deprecated versions between
  the two notices are not counted as exposed).
- Artifact actions are split into version groups (v1/v2, v3); the scanner records when each group disappeared
  (`group_migrations`, keyed by the *announced* cutoff of the group: 2024-06-30 for v1/v2, 2025-01-30 for v3).
  The scanner's `category` = `after_enforcement` compares with these announced dates.
- RQ1 phases (`analyze_timing.py`) use the dates on which workflows actually broke instead:
  a migration is **after the cutoff** if some group disappeared on or after its breakage date
  (v1/v2: 2024-09-06, v3: 2025-01-30), **during brownouts** if the v3 group disappeared from 2025-01-09 on,
  and **before any breakage** otherwise.

## Brownouts (artifact actions v3)

Before the final cutoff GitHub ran three announced brownouts, during which v3 workflows failed
([community discussion #142581](https://github.com/orgs/community/discussions/142581), post of 2024-10-25, updated 2024-11-22):

| Date | Window (EST) |
| --- | --- |
| 2025-01-09 | 12:00–13:00 |
| 2025-01-16 | 10:00–14:00 |
| 2025-01-23 | 09:00–17:00 |

The data agrees: microsoft/vcpkg-tool migrated on 2025-01-17 quoting the failure message, the day
after the second brownout. For the analysis, the first brownout (2025-01-09) is the first moment a
v3 workflow could break; 2025-01-30 remains the final cutoff. No brownouts were found for v1/v2; they failed without warning about two months after the announced date.

## Candidate events (not yet included)

- Node.js runtime transitions for JavaScript actions (12 → 16 → 20 → 24): automatic runtime shim, no breakage.
- Runner image retirements (e.g. `ubuntu-20.04`): hard cutoff, detectable from `runs-on:`.
