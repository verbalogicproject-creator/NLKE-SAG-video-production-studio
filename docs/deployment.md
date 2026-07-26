# GCP beta deployment

Production is confined to one GCP project and one region. Terraform provisions
Cloud Run services and jobs, a private Cloud SQL PostgreSQL instance, a regional
GCS bucket, Cloud Tasks, Cloud Scheduler, KMS, Secret Manager, Artifact Registry,
logging metrics, and separate service accounts.

## Bootstrap

```sh
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud artifacts repositories describe sag-staging-images --location "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create sag-staging-images --location "$GCP_REGION" \
    --repository-format docker
gcloud builds submit --config cloudbuild.yaml \
  --substitutions _REGION="$GCP_REGION",_REPOSITORY="sag-staging-images"

terraform -chdir=deploy/terraform init
# Adopt the bootstrapped registry so Terraform owns it from this point onward.
terraform -chdir=deploy/terraform import \
  -var project_id="$GOOGLE_CLOUD_PROJECT" -var region="$GCP_REGION" \
  -var web_image="$WEB_IMAGE" -var engine_image="$ENGINE_IMAGE" -var jobs_image="$JOBS_IMAGE" \
  google_artifact_registry_repository.images \
  "projects/$GOOGLE_CLOUD_PROJECT/locations/$GCP_REGION/repositories/sag-staging-images"
terraform -chdir=deploy/terraform plan \
  -var project_id="$GOOGLE_CLOUD_PROJECT" \
  -var region="$GCP_REGION" \
  -var web_image="$WEB_IMAGE" \
  -var engine_image="$ENGINE_IMAGE" \
  -var jobs_image="$JOBS_IMAGE"
terraform -chdir=deploy/terraform apply
```

Keep `enable_cloud_execution=false` and `external_beta_enabled=false` for the
initial apply. Use a dedicated staging project: the currently selected local
`gcloud` project must never be assumed to be the intended target.

Terraform creates secret containers without secret versions so secret values do
not enter Terraform state. Operators add versions separately:

```sh
printf '%s' "$DATABASE_URL" | gcloud secrets versions add sag-staging-database-url --data-file=-
printf '%s' "$NEXTAUTH_SECRET" | gcloud secrets versions add sag-staging-nextauth-secret --data-file=-
printf '%s' "$GOOGLE_CLIENT_ID" | gcloud secrets versions add sag-staging-google-client-id --data-file=-
printf '%s' "$GOOGLE_CLIENT_SECRET" | gcloud secrets versions add sag-staging-google-client-secret --data-file=-
printf '%s' "$SAG_VIDEO_TRANSCRIPTION_API_KEY" | gcloud secrets versions add sag-staging-transcription-api-key --data-file=-
```

Apply the Prisma-owned control/queue baseline. The Python engine creates and
checksum-verifies its own `sag` migrations during startup:

```sh
pnpm db:deploy
```

Before switching a deployment that already contains Prisma-owned Studio
delivery rows to the engine-owned release endpoints, stop release writers,
back up PostgreSQL, and preview the idempotent transfer:

```sh
SAG_ENGINE_URL="$ENGINE_URL" \
SAG_VIDEO_SERVICE_TOKEN="$ENGINE_SERVICE_TOKEN" \
pnpm migrate:delivery

SAG_ENGINE_URL="$ENGINE_URL" \
SAG_VIDEO_SERVICE_TOKEN="$ENGINE_SERVICE_TOKEN" \
pnpm migrate:delivery -- --apply
```

Use `--project=CONTROL_PROJECT_ID` (or a sequence/engine project ID) for a
bounded rehearsal. Re-run the dry report after apply and compare profile,
approval, and attempt counts before disabling legacy writes. The import endpoint
is service-only and idempotent by profile destination, approval bundle hash,
and approval/destination attempt identity.

For a pre-migration development database that was created with `prisma db
push`, first compare it to the checked-in schema, back it up, mark only
`202607230001_canonical_cloud_jobs` as the adopted baseline with `prisma migrate
resolve --applied`, and then run `pnpm db:deploy` to apply the canonical-job
execution migration. Never mark the second migration applied without running
its DDL.

The build pipeline starts an ephemeral PostgreSQL 16 container, deploys the
Prisma migration, runs the full Python suite (including PostgreSQL parity and
Python SAG migrations), validates Terraform, and builds all production images.

The engine defaults new causal journal streams to unkeyed SHA-256, which proves
internal consistency when the head hash is checkpointed out of band. For an
adversarial multi-writer deployment, store `SAG_JOURNAL_HMAC_KEY` in Secret
Manager and request `hmac-sha256` when creating the first entry in a namespace.
Never place that key in the database, runtime events, spatial metadata, or
receipts. A namespace cannot change hash algorithms after its first entry.

## Import existing local state

Stop local writers and make a consistent copy of the SQLite database first. A
database with live WAL files is rejected. Map every source workspace to an
existing control-plane workspace ID when the identities differ.

```sh
sag-video-import plan \
  --sqlite .sag-video/sag-video.db.backup \
  --media-root .sag-video/media \
  --proxy-root .sag-video/proxies \
  --artifact-root .sag-video/artifacts \
  --workspace-map workspace-map.json

sag-video-import run \
  --sqlite .sag-video/sag-video.db.backup \
  --media-root .sag-video/media \
  --proxy-root .sag-video/proxies \
  --artifact-root .sag-video/artifacts \
  --database-url "$DATABASE_URL" \
  --bucket "$GCS_MEDIA_BUCKET" \
  --workspace-map workspace-map.json \
  --report-file import-report.json

sag-video-import verify \
  --sqlite .sag-video/sag-video.db.backup \
  --media-root .sag-video/media \
  --proxy-root .sag-video/proxies \
  --artifact-root .sag-video/artifacts \
  --database-url "$DATABASE_URL" \
  --bucket "$GCS_MEDIA_BUCKET" \
  --workspace-map workspace-map.json
```

The import uses a maintenance advisory lock, `ON CONFLICT` row replay,
per-object checkpoints, immutable GCS promotion, and SHA-256 verification. A
failed run can be invoked again with the same source fingerprint. Local Codex
pairings and bearer tokens are deliberately excluded; provision new scoped,
hashed API keys after import.

## Staging acceptance

After the import verifies, apply with `enable_cloud_execution=true` while
leaving public admission off. Grant a test operator IAM invocation access and
create API keys with the MCP scopes needed by the harness; the first load-test
key also needs `operations:read`. Set Terraform's `transcription_base_url` and
`transcription_model` for a Whisper-compatible provider; the API key is exposed
only to the analysis service account.

```sh
SAG_ACCEPTANCE_COOKIE="$AUTH_COOKIE" \
SAG_ACCEPTANCE_API_KEY="$SCOPED_API_KEY" \
pnpm test:cloud:acceptance -- acceptance.json

pnpm test:cloud:load -- load-test.json
```

`acceptance.json` supplies `baseUrl`, English and Hebrew fixtures (`path`,
`contentType`, `language`, `hookTitle`), and an optional `reportFile`.
`load-test.json` supplies `baseUrl` and exactly ten prepared workspace entries
with `name`, `apiKey`, `runId`, `variant`, and `projectRevision`.

The creator-loop gate uploads through a resumable GCS session, waits for
independent intake, verifies three distinct platform suggestions, applies a
semantic MCP edit, renders, waits for the separately dispatched observer, then
downloads and re-hashes the result. The load gate proves cross-workspace denial
and observes no more than two active heavy jobs. Retain both JSON reports with
the deployed image digests and migration revision.

## Operator workflows

```sh
# Build an immutable revision
gcloud builds submit --config cloudbuild.yaml \
  --substitutions _REGION="$GCP_REGION",_REPOSITORY="sag-staging-images"

# Inspect executions and queue pressure
gcloud run jobs executions list --region "$GCP_REGION"
gcloud tasks queues describe sag-staging-dispatch --location "$GCP_REGION"

# Run reconciliation manually
gcloud scheduler jobs run sag-staging-reconcile --location "$GCP_REGION"

# Roll back a service to a known revision
gcloud run services update-traffic sag-staging-web --region "$GCP_REGION" \
  --to-revisions "KNOWN_GOOD_REVISION=100"

# Verify and restore backups before external beta admission
gcloud sql backups list --instance sag-staging-postgres
gcloud sql backups restore BACKUP_ID --restore-instance sag-staging-postgres
```

Use zonal Cloud SQL only for development and staging. Cloud execution and
public admission default off. Enable `enable_cloud_execution=true` only in the
acceptance environment after PostgreSQL/GCS gates pass; set
`cloud_sql_ha=true` and `external_beta_enabled=true` only after the complete
admission checklist passes. Terraform enforces that relationship. Engine and
dispatcher remain IAM private. Cloud Tasks sends OIDC tokens and job containers
receive only `SAG_CANONICAL_JOB_ID`; the job kind is fixed by Terraform.

Before external admission, also restore a backup into a separate instance,
compare row counts and artifact hashes, restart every service between render and
readback, simulate an ambiguous YouTube upload timeout, and prove that the same
approval/artifact/channel tuple resolves to exactly one private video. Begin
with three internal workspaces; expand to ten only after monitoring, failure,
queue, quota, storage, and budget signals have been reviewed.

## Local Termux

Termux uses local PostgreSQL for the control plane and filesystem-backed SAG
media. Run `sh scripts/dev-termux.sh`. Local Google OAuth and YouTube publishing
are optional; the editor, analysis, render, observer, and receipt workflow do
not require them.
