# Deploy StatsFinder to Cloud Run

This guide deploys the FastAPI app to Google Cloud Run, connects it to Cloud SQL
for PostgreSQL through the Cloud SQL Unix socket at
`/cloudsql/<INSTANCE_CONNECTION_NAME>`, and leaves Cloudflare Access in front of
the service for user access control.

Use placeholders for every environment-specific value:

```bash
PROJECT_ID="PROJECT_ID"
REGION="REGION"
SERVICE_NAME="SERVICE_NAME"
DB_INSTANCE="DB_INSTANCE"
DB_NAME="DB_NAME"
DB_USER="DB_USER"
```

Do not commit secrets. Store the database password in Secret Manager and grant
the Cloud Run service account access to that secret.

## 1. Configure gcloud

```bash
gcloud config set project "${PROJECT_ID}"
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com
```

## 2. Create or confirm Cloud SQL PostgreSQL

If the Cloud SQL instance already exists, skip creation and verify its instance
connection name:

```bash
gcloud sql instances describe "${DB_INSTANCE}" \
  --format='value(connectionName)'
```

Create the database and user if needed:

```bash
gcloud sql databases create "${DB_NAME}" --instance "${DB_INSTANCE}"
gcloud sql users create "${DB_USER}" \
  --instance "${DB_INSTANCE}" \
  --password "REPLACE_WITH_A_GENERATED_PASSWORD"
```

Save the password in Secret Manager instead of putting it in source control:

```bash
printf '%s' 'REPLACE_WITH_THE_DATABASE_PASSWORD' | \
  gcloud secrets create statsfinder-db-password --data-file=-
```

## 3. Build and deploy the container

Cloud Run provides the `PORT` environment variable. The Dockerfile starts Uvicorn
with `${PORT:-8000}`, so no hard-coded production port is required.

```bash
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/statsfinder/${SERVICE_NAME}:$(git rev-parse --short HEAD)"
CONNECTION_NAME="${PROJECT_ID}:${REGION}:${DB_INSTANCE}"

gcloud artifacts repositories create statsfinder \
  --repository-format=docker \
  --location "${REGION}" \
  --description "StatsFinder containers" || true

gcloud builds submit --tag "${IMAGE}" .

gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --add-cloudsql-instances "${CONNECTION_NAME}" \
  --set-env-vars "CLOUD_SQL_INSTANCE_CONNECTION_NAME=${CONNECTION_NAME},DB_NAME=${DB_NAME},DB_USER=${DB_USER}" \
  --set-secrets "DB_PASSWORD=statsfinder-db-password:latest" \
  --no-allow-unauthenticated
```

The app is read-only at runtime: it serves pages and API responses from the
configured Postgres database. Data loading and embedding jobs should be run as
separate administrative tasks, not through the public Cloud Run service.

## 4. Put Cloudflare Access in front

Keep Cloud Run private (`--no-allow-unauthenticated`) unless your Cloudflare
setup requires a public origin. Configure Cloudflare Access for the user-facing
hostname, then route traffic to the Cloud Run service URL or a Google external
HTTPS load balancer in front of Cloud Run.

## 5. Deployment smoke test

After deployment, get the service URL and run the smoke tests:

```bash
SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format='value(status.url)')"
python3 -m scripts.smoke.smoke_test_local --base-url "${SERVICE_URL}"
```

The smoke test checks:

- `/health`
- `/health/db`
- `/search`
- `/v1/datasets`
- representative read-only dataset, series, search, observation, CSV, and 404 paths

If Cloud Run remains private, run smoke tests from an authenticated environment
or through the Cloudflare Access-protected hostname with the required Access
headers.

## Deployment assumptions

- Cloud SQL contains the schema and loaded datasets before the Cloud Run smoke
  test runs.
- Runtime database access uses either `ONS_SDMX_DB_DSN` or the Cloud SQL socket
  environment variables shown above.
- Gemini configuration is only required for semantic search and chat endpoints;
  `/health`, `/health/db`, `/search`, and `/v1/datasets` do not call Gemini.
- No MCP integration is required for this deployment.
