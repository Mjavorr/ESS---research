# Deprecation events

Platform-enforced deprecations studied so far. Dates come from the official GitHub changelog.

| Event | Regime | First warning (T_warn) | Enforcement (T_enforce) | Detection in workflow files |
| --- | --- | --- | --- | --- |
| Artifact actions v3 | hard cutoff | 2024-04-16 | 2025-01-30 | `uses: actions/upload-artifact@v3`, `actions/download-artifact@v3` |
| Artifact actions v1, v2 | hard cutoff | 2024-04-16 | 2024-06-30 | same, with `@v1` / `@v2` |
| `set-output` / `save-state` workflow commands | announced cutoff, later withdrawn | 2022-10-11 | announced for 2023-05-31; postponed indefinitely on 2023-07-24 | `::set-output` / `::save-state` in `run:` steps |

Sources:

- [Deprecation notice: v3 of the artifact actions](https://github.blog/changelog/2024-04-16-deprecation-notice-v3-of-the-artifact-actions/) (2024-04-16): "Starting January 30th, 2025, GitHub Actions customers will no longer be able to use v3"; v1 and v2 deprecation "scheduled to take place on June 30, 2024".
- [GitHub Actions: Deprecating save-state and set-output commands](https://github.blog/changelog/2022-10-11-github-actions-deprecating-save-state-and-set-output-commands/) (2022-10-11): planned to "fully disable them on 31st May 2023"; update of 2023-07-24: "Our telemetry shows significant usage of these commands so we have decided to postpone the removal."

## Detection rules

- Commented-out lines (`#` before the match) are ignored.
- Artifact actions: only the official `actions/` owner counts (e.g. `dawidd6/action-download-artifact` does not).
- A repository is **exposed** if the default branch had at least one active occurrence at T_warn.
- The default branch at T_warn is the first-parent ancestor of today's `HEAD` with commit date before T_warn.
- **Migration** = the earliest first-parent commit on the default branch after which no occurrence remains.
- Artifact actions are split into version groups with their own cutoff (v1/v2: 2024-06-30, v3: 2025-01-30).
  A migration counts as **after enforcement** if any group present at T_warn disappeared only after its group's cutoff.

## Observations

- Some commits quote the v3 failure message before the 30 January 2025 cutoff (microsoft/vcpkg-tool on
  2025-01-17, bazelbuild/rules_pkg reports failures "as of January 22, 2025"). This suggests brownouts
  (temporary planned failures) before the final cutoff, although the changelog does not mention them.
  To be verified before the analysis treats 2025-01-30 as the moment of breakage.

## Candidate events (not yet included)

- Node.js runtime transitions for JavaScript actions (12 → 16 → 20 → 24): automatic runtime shim, no breakage.
- Runner image retirements (e.g. `ubuntu-20.04`): hard cutoff, detectable from `runs-on:`.
