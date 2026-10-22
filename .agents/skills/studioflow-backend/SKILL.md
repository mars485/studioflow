---
name: studioflow-backend
description: Implement and review StudioFlow FastAPI, PostgreSQL, migrations, workspace access, and backend tests.
---

# StudioFlow backend

Read `AGENTS.md`, `README.md`, and `docs/REFERENCES.md`. Inspect `backend/app/api/v1`, `backend/app/api/dependencies.py`, `backend/app/models/entities.py`, and `backend/alembic/versions` before editing. Keep queries scoped to `workspace_id`; check membership and role on every route. Maintain schema validation and existing 404 behavior for inaccessible resources.

Add migration and tests in `backend/tests` for data changes. From repository root run `docker compose -p studioflow-crm-check -f docker-compose.test.yml run --build --rm backend`, then `docker compose -p studioflow-crm-check -f docker-compose.test.yml down`. Use only isolated test PostgreSQL.
