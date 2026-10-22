---
name: studioflow-frontend
description: Implement and review StudioFlow React TypeScript CRM interface, API states, and component tests.
---

# StudioFlow frontend

Read `AGENTS.md`, `README.md`, and `docs/REFERENCES.md`. Inspect `frontend/src/api.ts`, `CRM.tsx`, `Auth.tsx`, `WorkspaceSettings.tsx`, and neighboring tests. Preserve loading, empty, error, retry, and unsaved form states; observe role restrictions and keyboard accessibility. Keep new styling consistent with `frontend/src/styles.css` while creating StudioFlow's own interface.

From `frontend`, run `npm ci`, `npm run test`, and `npm run build`. For isolated Docker validation from repository root run `docker compose -p studioflow-crm-check -f docker-compose.test.yml run --build --rm --no-deps frontend`.
