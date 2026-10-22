---
name: studioflow-qa
description: Validate StudioFlow migrations, API isolation, React behavior, and P0 end-to-end acceptance.
---

# StudioFlow QA

Read `AGENTS.md` and P0 acceptance criteria in `docs/REFERENCES.md`. Inspect `backend/tests`, `frontend/src/*.test.tsx`, and `docker-compose.test.yml`. Cover registration, workspace creation, client and deal creation, stage movement, follow-up persistence after reload, role denial, cross-workspace denial, API errors, and timezone behavior. Do not claim browser E2E passes until a runner and tests exist and execute successfully.

From repository root run the backend and frontend Docker checks in `AGENTS.md`, then `docker compose -p studioflow-crm-check -f docker-compose.test.yml down`. Record commands and outcomes. Keep test data isolated from production volumes.

For browser coverage, run the E2E Docker commands in `AGENTS.md`; test code is in `frontend/e2e`, with configuration in `frontend/playwright.config.ts`. Always stop the E2E stack after the run.
