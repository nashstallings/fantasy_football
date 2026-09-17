# Workload Identity Federation setup

How GitHub Actions authenticates to BigQuery for the `nfl_pbp` pipeline, and how
to set it up step by step. There is deliberately **no service-account key** —
Actions exchanges a short-lived GitHub OIDC token for GCP credentials.

[`scripts/setup_wif.sh`](../scripts/setup_wif.sh) does all of this in one
command. This page is the manual walkthrough: run it if you want to understand
each step, if the script fails partway, or if you'd rather use the console.

---

## 0. Before you start

### Install and authenticate

```bash
# https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud config set project ff-python-api
```

`bq` ships with the gcloud SDK, so you get both.

### Confirm you have the right permissions

You need to create IAM resources and set policy. In practice that means Owner,
or this set: `roles/iam.workloadIdentityPoolAdmin`,
`roles/iam.serviceAccountAdmin`, `roles/resourcemanager.projectIamAdmin`.

Check what you currently hold:

```bash
gcloud projects get-iam-policy ff-python-api \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:$(gcloud config get-value account)" \
  --format="value(bindings.role)"
```

If that prints `roles/owner`, you're set. If it prints nothing, you're looking
at the wrong project or the wrong account.

### Values used throughout

| Name | Value |
|---|---|
| Project ID | `ff-python-api` |
| Repository | `nashstallings/fantasy_football` |
| Pool ID | `github-actions` |
| Provider ID | `github` |
| Service account | `gh-actions-pbp@ff-python-api.iam.gserviceaccount.com` |
| Datasets | `pbp_bronze`, `pbp_silver`, `pbp_gold` |

---

## 1. Enable the APIs

```bash
gcloud services enable \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  bigquery.googleapis.com \
  --project ff-python-api
```

Takes about 30 seconds. `sts` performs the token exchange and `iamcredentials`
issues the impersonated token — without both, auth fails at the exchange step
with a message that doesn't name the missing API.

Verify:

```bash
gcloud services list --enabled --project ff-python-api \
  | grep -E "iamcredentials|sts\.|bigquery"
```

---

## 2. Get the project number

```bash
gcloud projects describe ff-python-api --format='value(projectNumber)'
```

Save it. Every reference below that says `PROJECT_NUMBER` means this value, and
**it is not the project ID**. This is the single most common setup mistake — see
[Troubleshooting](#troubleshooting).

```bash
export PROJECT_NUMBER="$(gcloud projects describe ff-python-api --format='value(projectNumber)')"
```

---

## 3. Create the service account

This is the identity the workflow acts as. It never gets a key.

```bash
gcloud iam service-accounts create gh-actions-pbp \
  --project ff-python-api \
  --display-name "GitHub Actions - pbp pipeline"
```

Verify:

```bash
gcloud iam service-accounts describe \
  gh-actions-pbp@ff-python-api.iam.gserviceaccount.com --project ff-python-api
```

---

## 4. Create the identity pool

```bash
gcloud iam workload-identity-pools create github-actions \
  --project ff-python-api \
  --location global \
  --display-name "GitHub Actions"
```

---

## 5. Create the OIDC provider — the important one

```bash
gcloud iam workload-identity-pools providers create-oidc github \
  --project ff-python-api \
  --location global \
  --workload-identity-pool github-actions \
  --display-name "GitHub OIDC" \
  --issuer-uri "https://token.actions.githubusercontent.com" \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition "assertion.repository == 'nashstallings/fantasy_football'"
```

**Read this before running it.** The `--attribute-condition` is the entire
security boundary. GitHub's OIDC issuer is shared by every repository on GitHub,
so the pool restricts nothing by itself. Without that condition, any repository
on the internet can mint a token for this provider and impersonate the service
account. Nothing warns you afterward — it simply works, for everyone.

The mapping and the condition are coupled: the condition can only reference
attributes the mapping defines. That's why `attribute.repository` appears in
both. Dropping it from the mapping makes the condition fail to validate.

Verify both landed:

```bash
gcloud iam workload-identity-pools providers describe github \
  --project ff-python-api --location global \
  --workload-identity-pool github-actions \
  --format="yaml(attributeCondition, attributeMapping, oidc.issuerUri, state)"
```

`state` should read `ACTIVE`, and `attributeCondition` should show your repo.

---

## 6. Let the repository impersonate the service account

```bash
gcloud iam service-accounts add-iam-policy-binding \
  gh-actions-pbp@ff-python-api.iam.gserviceaccount.com \
  --project ff-python-api \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-actions/attribute.repository/nashstallings/fantasy_football"
```

The `principalSet://` string has an exact shape and no forgiving errors. Note it
ends in `attribute.repository/<owner>/<repo>` — the attribute you mapped in
step 5, then its value.

Verify:

```bash
gcloud iam service-accounts get-iam-policy \
  gh-actions-pbp@ff-python-api.iam.gserviceaccount.com --project ff-python-api
```

---

## 7. Grant BigQuery access

Two grants, deliberately different in scope.

**Job creation, project level.** Running any query or load job requires
permission to create jobs, and that isn't a dataset-scoped concept in BigQuery.
`jobUser` is the minimal form — it permits running jobs, not reading data.

```bash
gcloud projects add-iam-policy-binding ff-python-api \
  --member "serviceAccount:gh-actions-pbp@ff-python-api.iam.gserviceaccount.com" \
  --role roles/bigquery.jobUser \
  --condition=None
```

**Data access, per dataset.** Scoped to the three `pbp_*` datasets so a leaked
workflow token cannot read or modify the `nflreadpy` dataset the other pipeline
owns.

The datasets have to exist before you can grant on them:

```bash
for ds in pbp_bronze pbp_silver pbp_gold; do
  bq --project_id=ff-python-api mk --dataset --location=US "ff-python-api:${ds}" || true
  bq --project_id=ff-python-api query --use_legacy_sql=false \
    "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`ff-python-api.${ds}\`
     TO \"serviceAccount:gh-actions-pbp@ff-python-api.iam.gserviceaccount.com\""
done
```

Verify one:

```bash
bq --project_id=ff-python-api show --format=prettyjson ff-python-api:pbp_bronze \
  | grep -A2 gh-actions-pbp
```

---

## 8. Add the repository secrets

```bash
gh secret set GCP_PROJECT_ID --repo nashstallings/fantasy_football \
  --body "ff-python-api"

gh secret set GCP_WIF_PROVIDER --repo nashstallings/fantasy_football \
  --body "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-actions/providers/github"

gh secret set GCP_SERVICE_ACCOUNT --repo nashstallings/fantasy_football \
  --body "gh-actions-pbp@ff-python-api.iam.gserviceaccount.com"
```

Or in the browser: **Settings → Secrets and variables → Actions → New repository
secret**. They must be *repository* secrets, not environment secrets — the
workflows don't declare an `environment:`, so environment secrets won't resolve.

Confirm the names exist (values are write-only):

```bash
gh secret list --repo nashstallings/fantasy_football
```

---

## 9. Verify end to end

Prove it on one season before trusting the schedule:

```bash
gh workflow run "PBP Backfill" --repo nashstallings/fantasy_football \
   -f start_season=2024 -f end_season=2024

gh run watch --repo nashstallings/fantasy_football
```

One season exercises auth, dataset creation, and MERGE in a few minutes. Because
every write is keyed on `game_id + play_id`, widening the range afterward is safe
and re-running changes nothing.

Then check the output:

```sql
-- roughly 49,500 plays for a full 2024
SELECT season, COUNT(*) AS plays, COUNT(DISTINCT game_id) AS games
FROM `ff-python-api.pbp_bronze.plays` GROUP BY season;

-- the enrichment columns are populated
SELECT true_pressure_method, COUNT(*) AS n, AVG(CAST(true_pressure AS INT64)) AS rate
FROM `ff-python-api.pbp_silver.plays_enriched`
WHERE true_pressure IS NOT NULL GROUP BY 1;

-- offense/defense rows must mirror: a defense allowed what the offense produced
SELECT team, opponent, side, plays, ROUND(epa_per_play, 4) AS epa
FROM `ff-python-api.pbp_gold.team_unit_weekly`
WHERE season = 2024 AND week = 1 ORDER BY plays DESC, side;
```

In that last result each game appears twice — once as the offense's row and once
as the opponent's defense row — with identical numbers. If they differ, the
rollup is wrong.

Once that passes, the Tuesday cron will start doing real work on its own.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Invalid value for "audience"` / `Workload Identity Pool does not exist` | `GCP_WIF_PROVIDER` used the project **ID** instead of the project **number** | Re-set the secret using step 2's number |
| `Unable to acquire impersonated credentials` | The `workloadIdentityUser` binding is missing or the `principalSet://` string is malformed | Redo step 6; compare the string character by character |
| `Permission 'iam.serviceAccounts.getAccessToken' denied` | Same as above — the repo isn't bound to the SA | Redo step 6 |
| `The given credential is rejected by the attribute condition` | The running repo doesn't match the condition (renamed repo, fork, or a typo) | Check step 5's `attributeCondition` against the actual repo |
| `The attribute condition must reference one of the provider's claims` | `attribute.repository` is missing from `--attribute-mapping` | Recreate the provider with both flags as in step 5 |
| `Access Denied: Project ff-python-api: User does not have bigquery.jobs.create` | `jobUser` not granted | Step 7, first command |
| `Access Denied: Dataset ff-python-api:pbp_bronze` | `dataEditor` not granted on that dataset | Step 7, second block |
| `id-token: write` / `Missing OIDC token` | The workflow lacks the permission block | Already set in the workflows; only an issue if you add a new one |
| Provider or pool `already exists` after you deleted it | Deleted pools and providers are soft-deleted for 30 days and the ID stays reserved | `gcloud iam workload-identity-pools providers undelete`, or use a new ID |

To see what GitHub is actually asserting, add a debug step to the workflow
temporarily — the `sub` and `repository` claims are what the condition tests
against.

---

## Rotation and revocation

There is no key to rotate. To revoke access immediately:

```bash
# remove just this repo's ability to impersonate
gcloud iam service-accounts remove-iam-policy-binding \
  gh-actions-pbp@ff-python-api.iam.gserviceaccount.com \
  --project ff-python-api \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-actions/attribute.repository/nashstallings/fantasy_football"

# or kill the provider entirely
gcloud iam workload-identity-pools providers delete github \
  --project ff-python-api --location global --workload-identity-pool github-actions
```

Both take effect on the next token exchange, with no secret to hunt down and no
key that might already have been copied somewhere.
