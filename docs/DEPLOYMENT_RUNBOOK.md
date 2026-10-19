# AfroVending — Deployment Runbook

## Environments
| Env | Where | Notes |
|---|---|---|
| Preview | Emergent preview URL (`REACT_APP_BACKEND_URL`) | Development; `APP_ENV=development`. |
| Production | https://www.afrovending.com via Emergent deploy | **Only with explicit owner approval.** |

## Environment variables (names only — never commit values)
Backend (`backend/.env`, template `backend/.env.example`): `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `APP_ENV` (`development|staging|production`), `LOG_LEVEL`, `FRONTEND_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME`, `EMAIL_REPLY_TO`, `CONTACT_INBOX`.
Before production: set a NEW `JWT_SECRET` and a NEW strong `ADMIN_PASSWORD` (14+ chars, upper/lower/number/symbol — boot fails otherwise), and set `FRONTEND_URL` to `https://www.afrovending.com`.
DNS: fix afrovending.com nameserver delegation and add MX records so info@afrovending.com can receive mail (contact form depends on it).
Frontend (`frontend/.env`, template `frontend/.env.example`): `REACT_APP_BACKEND_URL`.
Reserved for future phases (add when the phase starts): `JWT_SECRET` (01), `STORAGE_*` (03), `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` (07), `RESEND_API_KEY`, `SENDER_EMAIL` (11).

## Pre-deploy checklist
1. All phase tests green (`cd backend && pytest tests`).
2. `APP_ENV=production`, `CORS_ORIGINS` set to `https://www.afrovending.com` (no `*`).
3. Production MongoDB is a replica set (transactions) with automated backups enabled.
4. Secrets set in the platform secrets panel, not in code.
5. Confirm migrations to be applied (`schema_migrations`) and take a DB backup first.
6. Owner approval recorded in DECISION_LOG.
7. Branded email (D-029) — switch from Emergent Managed Email to sending as `info@afrovending.com`:
   - Owner creates an account with an email provider that supports custom domains (e.g. Resend) and adds `afrovending.com` as a sending domain.
   - Owner adds the provider's DNS records at the afrovending.com DNS host: SPF (TXT), DKIM (TXT/CNAME), a DMARC TXT (start with `p=none`), plus MX for the `info@` inbox. As of 2026-10-17 the afrovending.com DNS refused queries, so this must be fixed first.
   - Wait until the provider shows the domain as **Verified**, then give the builder the sending API key (stored only in the secrets panel).
   - Builder switches the email sender by config, keeps every existing template and safety check, sends test emails (verification, password reset, vendor notice, low-stock digest, contact form), and checks SPF/DKIM pass in the received headers.
   - Until then: managed sender with display name "AfroVending" and Reply-To `info@afrovending.com` (current setup).

## Rollback
Use the platform rollback to the previous deployment; migrations are additive (indexes, `$setOnInsert` seeds) so code rollback is safe. Destructive migrations require a written recovery plan before running.

## Source control
Workspace is a git repository (platform auto-commits). Push to a private GitHub repo with the platform's **Save to GitHub** feature; keep `.env` files out of public repos.
