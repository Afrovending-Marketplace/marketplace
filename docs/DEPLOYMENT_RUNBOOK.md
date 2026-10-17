# AfroVending — Deployment Runbook

## Environments
| Env | Where | Notes |
|---|---|---|
| Preview | Emergent preview URL (`REACT_APP_BACKEND_URL`) | Development; `APP_ENV=development`. |
| Production | https://www.afrovending.com via Emergent deploy | **Only with explicit owner approval.** |

## Environment variables (names only — never commit values)
Backend (`backend/.env`, template `backend/.env.example`): `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `APP_ENV` (`development|staging|production`), `LOG_LEVEL`.
Frontend (`frontend/.env`, template `frontend/.env.example`): `REACT_APP_BACKEND_URL`.
Reserved for future phases (add when the phase starts): `JWT_SECRET` (01), `STORAGE_*` (03), `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` (07), `RESEND_API_KEY`, `SENDER_EMAIL` (11).

## Pre-deploy checklist
1. All phase tests green (`cd backend && pytest tests`).
2. `APP_ENV=production`, `CORS_ORIGINS` set to `https://www.afrovending.com` (no `*`).
3. Production MongoDB is a replica set (transactions) with automated backups enabled.
4. Secrets set in the platform secrets panel, not in code.
5. Confirm migrations to be applied (`schema_migrations`) and take a DB backup first.
6. Owner approval recorded in DECISION_LOG.

## Rollback
Use the platform rollback to the previous deployment; migrations are additive (indexes, `$setOnInsert` seeds) so code rollback is safe. Destructive migrations require a written recovery plan before running.

## Source control
Workspace is a git repository (platform auto-commits). Push to a private GitHub repo with the platform's **Save to GitHub** feature; keep `.env` files out of public repos.
