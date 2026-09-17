#!/usr/bin/env bash
#
# Set up Workload Identity Federation so GitHub Actions can write to BigQuery
# without a service-account key.
#
# Idempotent: every step tolerates already existing, so re-running after a
# partial failure is safe.
#
# Requires: gcloud, authenticated as someone with Project IAM Admin on the
# project (creating pools and setting IAM policy both need it).
#
#   ./scripts/setup_wif.sh
#
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-ff-python-api}"
GITHUB_REPO="${GITHUB_REPO:-nashstallings/fantasy_football}"
POOL_ID="${POOL_ID:-github-actions}"
PROVIDER_ID="${PROVIDER_ID:-github}"
SA_NAME="${SA_NAME:-gh-actions-pbp}"
DATASETS=(pbp_bronze pbp_silver pbp_gold)

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "project : ${PROJECT_ID}"
echo "repo    : ${GITHUB_REPO}"
echo "sa      : ${SA_EMAIL}"
echo

# ---------------------------------------------------------------------------
echo "==> Enabling APIs"
gcloud services enable \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  bigquery.googleapis.com \
  --project "${PROJECT_ID}"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
echo "    project number: ${PROJECT_NUMBER}"

# ---------------------------------------------------------------------------
echo "==> Service account"
if gcloud iam service-accounts describe "${SA_EMAIL}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  echo "    exists"
else
  gcloud iam service-accounts create "${SA_NAME}" \
    --project "${PROJECT_ID}" \
    --display-name "GitHub Actions - pbp pipeline"
fi

# ---------------------------------------------------------------------------
echo "==> Workload identity pool"
if gcloud iam workload-identity-pools describe "${POOL_ID}" \
     --project "${PROJECT_ID}" --location global >/dev/null 2>&1; then
  echo "    exists"
else
  gcloud iam workload-identity-pools create "${POOL_ID}" \
    --project "${PROJECT_ID}" --location global \
    --display-name "GitHub Actions"
fi

# ---------------------------------------------------------------------------
# The attribute-condition is the security boundary. Without it ANY repository
# on GitHub can mint a token for this provider and impersonate the service
# account -- the issuer is shared by all of GitHub, so the pool alone restricts
# nothing. Pinning assertion.repository is what limits it to this repo.
echo "==> OIDC provider (restricted to ${GITHUB_REPO})"
if gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}" \
     --project "${PROJECT_ID}" --location global --workload-identity-pool "${POOL_ID}" \
     >/dev/null 2>&1; then
  echo "    exists - updating condition"
  gcloud iam workload-identity-pools providers update-oidc "${PROVIDER_ID}" \
    --project "${PROJECT_ID}" --location global --workload-identity-pool "${POOL_ID}" \
    --attribute-condition="assertion.repository == '${GITHUB_REPO}'"
else
  gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
    --project "${PROJECT_ID}" --location global --workload-identity-pool "${POOL_ID}" \
    --display-name "GitHub OIDC" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
    --attribute-condition="assertion.repository == '${GITHUB_REPO}'"
fi

# ---------------------------------------------------------------------------
echo "==> Allowing the repo to impersonate the service account"
PRINCIPAL="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPO}"
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --project "${PROJECT_ID}" \
  --role roles/iam.workloadIdentityUser \
  --member "${PRINCIPAL}" >/dev/null
echo "    bound ${PRINCIPAL}"

# ---------------------------------------------------------------------------
# jobUser is project-level and unavoidable: running any query or load job needs
# permission to create jobs, and that is not a dataset-scoped concept. It is the
# minimal such role -- it permits running jobs, not reading data. Data access
# stays scoped to the three datasets below.
echo "==> Granting bigquery.jobUser (project-level, minimal)"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${SA_EMAIL}" \
  --role roles/bigquery.jobUser \
  --condition=None >/dev/null
echo "    granted"

# ---------------------------------------------------------------------------
# Datasets must exist before they can be granted on. The pipeline creates them
# too, but the grant has to come first or the first run cannot write.
echo "==> Datasets + dataset-scoped dataEditor"
for ds in "${DATASETS[@]}"; do
  if bq --project_id="${PROJECT_ID}" show --dataset "${PROJECT_ID}:${ds}" >/dev/null 2>&1; then
    echo "    ${ds} exists"
  else
    bq --project_id="${PROJECT_ID}" mk --dataset --location=US "${PROJECT_ID}:${ds}"
  fi

  # Scoped to this dataset only -- deliberately NOT project-wide dataEditor,
  # so a compromised workflow token cannot touch the `nflreadpy` dataset that
  # the other pipeline owns.
  bq --project_id="${PROJECT_ID}" query --use_legacy_sql=false \
    "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`${PROJECT_ID}.${ds}\`
     TO \"serviceAccount:${SA_EMAIL}\"" >/dev/null
  echo "    ${ds}: dataEditor granted to ${SA_NAME}"
done

# ---------------------------------------------------------------------------
PROVIDER_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

cat <<EOF

=============================================================================
Done. Add these three repository secrets:

  GCP_PROJECT_ID       ${PROJECT_ID}
  GCP_WIF_PROVIDER     ${PROVIDER_RESOURCE}
  GCP_SERVICE_ACCOUNT  ${SA_EMAIL}

With the gh CLI:

  gh secret set GCP_PROJECT_ID      --repo ${GITHUB_REPO} --body "${PROJECT_ID}"
  gh secret set GCP_WIF_PROVIDER    --repo ${GITHUB_REPO} --body "${PROVIDER_RESOURCE}"
  gh secret set GCP_SERVICE_ACCOUNT --repo ${GITHUB_REPO} --body "${SA_EMAIL}"

Then verify end to end BEFORE trusting the schedule:

  gh workflow run "PBP Backfill" --repo ${GITHUB_REPO} \\
     -f start_season=2024 -f end_season=2024

A single season proves auth, dataset creation and MERGE in a few minutes. The
jobs are idempotent, so widening the range afterwards costs nothing.
=============================================================================
EOF
