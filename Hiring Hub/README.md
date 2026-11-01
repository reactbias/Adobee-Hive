# Adobee Hive Recruitment Portal

Dockerized recruitment portal with a React frontend, FastAPI CV analysis backend, PostgreSQL
persistence, asynchronous CV processing, natural-language candidate filtering, and PostgreSQL-backed
recruiter chat sessions.

## Requirements

- Docker Desktop or Docker Engine with the Compose plugin
- An OpenAI-compatible API key for CV extraction and recruiter filtering

Docker users do not need to install Node.js or Python.

## First-time setup

```bash
git clone <repository-url>
cd adobee-hiver
cp .env.example .env
cp backend/.env.example backend/.env
```

Set the database values in the root `.env` and the provider/admin values in `backend/.env`.
Do not commit either `.env` file. Use a new database password and rotate any provider key that
has been exposed.

Start the complete stack:

```bash
docker compose up --build -d
docker compose ps
```

Open:

- Frontend: <http://localhost:3000>
- Backend API docs: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5432` (normally only needed by database tools)

The browser calls `/api/...`; Nginx forwards those requests to the backend container.

## Verify the deployment

```bash
curl http://localhost:8000/health
curl http://localhost:3000/api/health
docker compose logs --tail=100 backend
```

Then use the UI to confirm job postings, upload a CV, wait for processing, run a candidate
filter, and reopen the Chat Sessions page to confirm the conversation is restored.

New installations start without job postings. Use **Add Job Posting** in the UI and paste the
title and description before uploading CVs. The repository's `backend/job_postings/` files are
optional sample data for the legacy import/CLI workflow; the web product does not depend on them.

## Data and operations

PostgreSQL data is stored in the named Docker volume `pgdata`. Stopping containers does not
delete data:

```bash
docker compose down
docker compose up -d
```

To delete all local database data, including candidates and chat sessions:

```bash
docker compose down -v
```

For production, put the frontend/backend behind HTTPS, keep PostgreSQL private, use managed
PostgreSQL or scheduled backups, and store secrets in the deployment platform's secret manager.

## Updating an installation

```bash
git pull
docker compose up --build -d
docker compose ps
```

Back up PostgreSQL before schema changes. `init.sql` is automatically applied only when a new
PostgreSQL volume is initialized; the backend creates tables defined by its SQLAlchemy models.

## Troubleshooting

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db
```

If authentication fails, remove the browser's stored `hive_api_key` and reload. If the provider
key is invalid, position listing can still work, but CV processing and natural-language filtering
will fail.
