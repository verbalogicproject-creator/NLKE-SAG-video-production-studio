# GCP beta deployment

Production is confined to one GCP project and one region. Terraform provisions
Cloud Run services and jobs, a private Cloud SQL PostgreSQL instance, a regional
GCS bucket, Cloud Tasks, Cloud Scheduler, KMS, Secret Manager, Artifact Registry,
logging metrics, and separate service accounts.

## Bootstrap

```sh
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com
gcloud builds submit --config cloudbuild.yaml \
  --substitutions _REGION="$GCP_REGION",_REPOSITORY="sag-staging-images"

terraform -chdir=deploy/terraform init
terraform -chdir=deploy/terraform plan \
  -var project_id="$GOOGLE_CLOUD_PROJECT" \
  -var region="$GCP_REGION" \
  -var web_image="$WEB_IMAGE" \
  -var engine_image="$ENGINE_IMAGE" \
  -var jobs_image="$JOBS_IMAGE"
terraform -chdir=deploy/terraform apply
```

Terraform creates secret containers without secret versions so secret values do
not enter Terraform state. Operators add versions separately:

```sh
printf '%s' "$DATABASE_URL" | gcloud secrets versions add sag-staging-database-url --data-file=-
printf '%s' "$NEXTAUTH_SECRET" | gcloud secrets versions add sag-staging-nextauth-secret --data-file=-
printf '%s' "$GOOGLE_CLIENT_ID" | gcloud secrets versions add sag-staging-google-client-id --data-file=-
printf '%s' "$GOOGLE_CLIENT_SECRET" | gcloud secrets versions add sag-staging-google-client-secret --data-file=-
```

Create the database schemas before applying Prisma and Python migrations:

```sql
CREATE SCHEMA IF NOT EXISTS control;
CREATE SCHEMA IF NOT EXISTS sag;
CREATE SCHEMA IF NOT EXISTS queue;
```

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

Use zonal Cloud SQL only for development and staging. Set
`cloud_sql_ha=true` before external beta users are admitted. Keep the web
service public for Google sign-in; engine and dispatcher services remain IAM
private. Cloud Tasks sends OIDC tokens and job containers receive only
`SAG_CANONICAL_JOB_ID`.

## Local Termux

Termux uses local PostgreSQL for the control plane and filesystem-backed SAG
media. Run `sh scripts/dev-termux.sh`. Local Google OAuth and YouTube publishing
are optional; the editor, analysis, render, observer, and receipt workflow do
not require them.
