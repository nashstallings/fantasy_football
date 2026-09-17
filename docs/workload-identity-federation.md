# Workload Identity Federation setup

How GitHub Actions authenticates to BigQuery for the `nfl_pbp` pipeline, and
how to set it up. There is deliberately **no service-account key** anywhere —
Actions exchanges a short-lived GitHub OIDC token for GCP credentials.

Run [`scripts/setup_wif.sh`](../scripts/setup_wif.sh) to do all of it. The rest
of this page is what the script does and why, for when it needs changing.

## Prerequisites

- `gcloud` and `bq` installed and authenticated
- Project IAM Admin on `ff-python-api` (creating pools and setting IAM policy
  both require it)

## What gets created

| Thing | Value |
|---|---|
| Service account | `gh-actions-pbp@ff-python-api.iam.gserviceaccount.com` |
| Identity pool | `github-actions` |
| OIDC provider | `github`, issuer `https://token.actions.githubusercontent.com` |
| Repo binding | `roles/iam.workloadIdentityUser` for `nashstallings/fantasy_football` |
| Data access | `roles/bigquery.dataEditor` on `pbp_bronze`, `pbp_silver`, `pbp_gold` |
| Job access | `roles/bigquery.jobUser` (project level) |

## The two things that are easy to get wrong

**The attribute condition is the whole security boundary.** GitHub's OIDC
issuer is shared by every repository on GitHub, so the pool by itself restricts
nothing — without a condition, *any* repo on the internet can mint a token for
your provider and impersonate the service account. The script pins:

```
assertion.repository == 'nashstallings/fantasy_football'
```

If you ever recreate the provider by hand, this is the line that matters.

**`bigquery.jobUser` has to be project-level, and that's fine.** Running any
query or load job requires permission to create jobs, which is not a
dataset-scoped concept in BigQuery. `jobUser` is the minimal form of it: it
permits running jobs, not reading data. Actual data access stays scoped to the
three `pbp_*` datasets, so a leaked workflow token cannot read or modify the
`nflreadpy` dataset the other pipeline owns.

## Repository secrets

The script prints these at the end:

| Secret | Value |
|---|---|
| `GCP_PROJECT_ID` | `ff-python-api` |
| `GCP_WIF_PROVIDER` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github-actions/providers/github` |
| `GCP_SERVICE_ACCOUNT` | `gh-actions-pbp@ff-python-api.iam.gserviceaccount.com` |

`GCP_WIF_PROVIDER` uses the **project number**, not the project ID. Using the ID
produces an authentication error that doesn't say so.

Until these exist, `PBP Weekly Update` skips with a notice rather than failing,
so the schedule can stay enabled during setup.

## Verifying

Prove it works on one season before trusting the schedule:

```bash
gh workflow run "PBP Backfill" --repo nashstallings/fantasy_football \
   -f start_season=2024 -f end_season=2024
```

That exercises auth, dataset creation, and MERGE in a few minutes. Because every
write is keyed on `game_id + play_id`, widening the range afterwards is safe and
re-running changes nothing.

Then confirm the output:

```sql
SELECT season, COUNT(*) AS plays, COUNT(DISTINCT game_id) AS games
FROM `ff-python-api.pbp_bronze.plays` GROUP BY season;

-- offense/defense rows must mirror: a defense allowed what the offense produced
SELECT * FROM `ff-python-api.pbp_gold.team_unit_weekly`
WHERE season = 2024 AND week = 1 ORDER BY team, side;
```

## Rotation and revocation

There is no key to rotate. To revoke access, remove the
`roles/iam.workloadIdentityUser` binding on the service account, or delete the
provider — both take effect immediately, with no secret to hunt down:

```bash
gcloud iam workload-identity-pools providers delete github \
  --project ff-python-api --location global --workload-identity-pool github-actions
```
