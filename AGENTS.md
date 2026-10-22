# Codex guidance for StudioFlow

Read `README.md` and `docs/REFERENCES.md` before planning changes. The reference matrix is a research guide; verify product behavior before implementing it. Follow the P0–P3 order and the acceptance criteria in `docs/REFERENCES.md`.

Keep changes scoped to one scenario per PR. Preserve existing data, access rules, and secrets. Do not alter production, deploy, or merge without the user's confirmation. For a new entity, include an Alembic migration, workspace scoped API and authorization, UI error handling, and relevant tests.

Backend lives in `backend/app`, migrations in `backend/alembic/versions`, tests in `backend/tests`. Frontend lives in `frontend/src`, tests alongside components. Run isolated checks from the repository root:

```powershell
docker compose -p studioflow-crm-check -f docker-compose.test.yml run --build --rm backend
docker compose -p studioflow-crm-check -f docker-compose.test.yml run --build --rm --no-deps frontend
docker compose -p studioflow-crm-check -f docker-compose.test.yml down
```

If Docker is unavailable, run `npm ci`, `npm run test`, and `npm run build` in `frontend`; report backend integration tests as unverified. Never run these checks against production data or volumes.
