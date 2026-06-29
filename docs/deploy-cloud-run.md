# Deploy StatsFinder to Cloud Run

This guide deploys the FastAPI app to Google Cloud Run, connects it to Cloud SQL
for PostgreSQL through the Cloud SQL Unix socket at
`/cloudsql/<INSTANCE_CONNECTION_NAME>`, and puts Cloudflare Access in front of
`www.statsfinder.uk` for the first pilot.

For the pilot path below, Cloud Run is deployed with `--allow-unauthenticated` so
Cloudflare can proxy to the service without presenting a Google-signed ID token.
That means the raw `run.app` URL can bypass Cloudflare Access until later origin
validation, ingress restrictions, or an authenticated proxy is added.

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
the Cloud Run runtime service account access to that secret.

## 1. Configure gcloud

```bash
gcloud config set project "${PROJECT_ID}"
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com
```

## 2. Create the runtime service account

Create a dedicated service account for the Cloud Run runtime:

```bash
RUN_SA="statsfinder-run@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create statsfinder-run \
  --display-name "StatsFinder Cloud Run runtime" || true
```

Grant it access to Cloud SQL:

```bash
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${RUN_SA}" \
  --role roles/cloudsql.client
```

Semantic search and chat use Gemini/Vertex AI. If those endpoints should work in
Cloud Run, also grant the runtime service account Vertex AI user permissions:

```bash
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${RUN_SA}" \
  --role roles/aiplatform.user
```

## 3. Create or confirm Cloud SQL PostgreSQL

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

Save the password in Secret Manager instead of putting it in source control, then
grant the runtime service account access to only that secret:

```bash
printf '%s' 'REPLACE_WITH_THE_DATABASE_PASSWORD' | \
  gcloud secrets create statsfinder-db-password --data-file=-

gcloud secrets add-iam-policy-binding statsfinder-db-password \
  --member "serviceAccount:${RUN_SA}" \
  --role roles/secretmanager.secretAccessor
```

## 4. Build and deploy the container

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
  --service-account "${RUN_SA}" \
  --add-cloudsql-instances "${CONNECTION_NAME}" \
  --set-env-vars "CLOUD_SQL_INSTANCE_CONNECTION_NAME=${CONNECTION_NAME},DB_NAME=${DB_NAME},DB_USER=${DB_USER}" \
  --set-secrets "DB_PASSWORD=statsfinder-db-password:latest" \
  --allow-unauthenticated
```

The app is read-only at runtime: it serves pages and API responses from the
configured Postgres database. Data loading and embedding jobs should be run as
separate administrative tasks, not through the public Cloud Run service.

## 5. Protect www.statsfinder.uk with Cloudflare Access

Configure Cloudflare DNS and Access so users visit `https://www.statsfinder.uk`
and must pass Cloudflare Access before reaching the Cloud Run-backed origin.

For this pilot, Cloud Run itself accepts unauthenticated requests. Treat the raw
Cloud Run `run.app` URL as a bypass path until a later hardening step prevents
direct origin access or validates Cloudflare identity at the origin.

## 6. Deployment smoke test

Because the pilot deployment uses `--allow-unauthenticated`, the smoke test can
call the service URL directly after deployment:

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

## Later hardening options

Before relying on Cloudflare Access as the only public control, add one of these
origin-protection patterns:

- Validate Cloudflare Access JWTs in the app or at a proxy before serving
  protected routes.
- Put a Google-authenticated proxy in front of private Cloud Run so the proxy
  presents a Google-signed ID token to the service.
- Put Cloud Run behind an external HTTPS load balancer and restrict ingress so
  only the load balancer can reach the service.

After hardening, update the smoke-test command to target the protected hostname
with the required auth headers or run it from the authenticated proxy path.

## Deployment assumptions

- Cloud SQL contains the schema and loaded datasets before the Cloud Run smoke
  test runs.
- Runtime database access uses either `ONS_SDMX_DB_DSN` or the Cloud SQL socket
  environment variables shown above.
- Gemini configuration is only required for semantic search and chat endpoints;
  `/health`, `/health/db`, `/search`, and `/v1/datasets` do not call Gemini.
- No MCP integration is required for this deployment.
