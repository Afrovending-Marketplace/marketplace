# AfroVending: GitHub export and staging deployment readiness (2026-11-22)

Status: **ready for export; NOT deployed.** We wait for the owner's approval before deploying to DigitalOcean.

## 1. GitHub export
- Target: `https://github.com/afrovending/Main-Marketplace.git` (private), branch `main`.
- Method: the Emergent **"Save to GitHub"** button in the chat input. It pushes the full reviewed source and git history. The agent can't push directly.
- Excluded by `.gitignore`: every `.env`, `memory/test_credentials.md`, `backups/`, `node_modules`, build output. `.emergent/` (the preview scheduler config) is ignored by Docker builds and isn't used on DigitalOcean.

## 2. Secret scan (tracked files + full history, 85 commits)
- Patterns searched: Stripe `sk_/rk_/whsec_`, Resend `re_`, Emergent keys, `mongodb://user:pass@`, private keys, AWS/GitHub tokens, and the actual current values of JWT_SECRET, WEBHOOK_CRON_SECRET, the storage key, the Stripe key and the Resend key. **No matches.**
- No `.env` file or `test_credentials.md` has ever been committed.
- **One finding:** the preview Super Admin password was hard-coded as a test default in `backend/tests/test_phase02_identity.py` (commit b9e3069, 2026-10-17). It is removed from the current code, but it remains in the Emergent job history. **Resolved 2026-11-22:** the account password was rotated to a random value (only the hash is stored), all admin sessions were revoked, and the action was audited. The owner sets a new password through the secure secrets card. A **sanitized single-commit export** (570 files, commit 931445b) was built and scanned: 0 real secrets, no .env or credential files. Save to GitHub pushes the **full original history** (Emergent support), so it would still carry the old, now useless, password.

## 3. Application structure exported
```
backend/            FastAPI app (server.py, afrovending/api/v1/*, core/*, migrations/, policies/*.md, scripts/, tests/), requirements.txt
frontend/           React (craco) app: src/pages, components, lib, public/brand assets, package.json + yarn.lock
deploy/             docker-compose.yml, web/backend/backup Dockerfiles, Caddyfile + Caddyfile.staging, cron/, backup/nightly.sh,
                    scripts/server_setup.sh, deploy.sh, rollback.sh, .env*.example
.github/workflows/  deploy-staging.yml (manual + approval), ci.yml (manual lint + build)
docs/               Master Plan, Decision Log, Phase Status, phase reports, runbooks, launch/staging guides, policy summaries
memory/PRD.md       Product requirements and change history
```

## 4. Deployment files
| File | Status |
|---|---|
| deploy/backend.Dockerfile, web.Dockerfile, backup.Dockerfile | Existing. The web image can now choose its Caddy config with `CADDY_CONFIG` |
| deploy/docker-compose.yml | Existing. Only ports 80/443 are published; the backend is internal; MongoDB is on Atlas (not on the Droplet) |
| deploy/Caddyfile.staging | Existing. HTTPS via Let's Encrypt with automatic renewal, basic-auth password, noindex/robots disallow, security headers |
| deploy/scripts/deploy.sh / rollback.sh | Existing. Versioned images, pre-deploy backup + restore drill, health check |
| backend/.env.example, frontend/.env.example | **Updated** (they had stale variable names) |
| deploy/.env.staging.example | **Updated**: SITE_DOMAIN=staging.afrovending.com |
| .github/workflows/deploy-staging.yml | **New**: `workflow_dispatch` only, `staging` environment (add yourself as a required reviewer), SSH key and known_hosts come from GitHub secrets |
| .github/workflows/ci.yml | **New**: manual-only lint + production build |
| Missing / owner-side | GitHub Environment `staging` with a required reviewer; secrets `STAGING_SSH_KEY`, `STAGING_KNOWN_HOSTS`; variable `STAGING_HOST`; a read-only deploy key so the Droplet can `git pull` |

Checked here: the production React build compiles with `REACT_APP_BACKEND_URL=https://staging.afrovending.com` (5.4 MB, no Emergent references), and `requirements.txt` resolves entirely from public PyPI. Docker images haven't been built yet (no Docker in this environment); the first build happens on the Droplet.

## 5. Environment variables
Server `deploy/.env.production` (template `backend/.env.example`): APP_ENV, LOG_LEVEL, MONGO_URL, DB_NAME, FRONTEND_URL, CORS_ORIGINS, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, ALLOW_ENV_ADMIN_SEED, BOOTSTRAP_RECOVERY_CODE, CONTACT_INBOX, ALERT_EMAIL, EMAIL_FROM_NAME, EMAIL_REPLY_TO, EMAIL_DOMAIN, EMAIL_SENDING_ENABLED, EMAIL_SENDER_OVERRIDE, RESEND_API_KEY, RESEND_WEBHOOK_SECRET, EMERGENT_LLM_KEY (storage), STRIPE_MODE, STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET, WEBHOOK_CRON_SECRET.
Compose `deploy/.env`: RELEASE, SITE_DOMAIN, ACME_EMAIL, CADDY_CONFIG, STAGING_AUTH_USER, STAGING_AUTH_HASH, WEBHOOK_CRON_SECRET.
Backups `deploy/.env.backup`: BACKUP_PASSPHRASE, SPACES_BUCKET, RCLONE_CONFIG_SPACES_*.
Frontend build arg: REACT_APP_BACKEND_URL (set by compose from SITE_DOMAIN).

## 6. External services
| Service | Use | Staging setting |
|---|---|---|
| MongoDB Atlas M0 (us-east-1) | Database | Only the Droplet IP allowed; dedicated user |
| Emergent managed storage | Files (the only Emergent dependency, owner's choice) | Needs `EMERGENT_LLM_KEY`, and the storage service must accept calls from outside Emergent (confirm) |
| Stripe | Payments | **Test keys only** (`STRIPE_MODE=test`). The webhook goes to `https://staging.afrovending.com/api/stripe/webhook` |
| Resend | Email | `EMAIL_SENDING_ENABLED=false` by default. Staging only reaches allow-listed test addresses. No marketing sends |
| DigitalOcean Spaces | Encrypted DB backups | Bucket `afrovending-staging-backups` |
| Let's Encrypt | HTTPS | Automatic via Caddy |
| UptimeRobot | External uptime | `/api/v1/health` |

## 7. Staging deployment commands (after approval)
```bash
ssh deploy@104.131.113.79
sudo mkdir -p /opt/afrovending && sudo chown deploy:deploy /opt/afrovending   # if not already owned by deploy
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""   # add the .pub to GitHub repo → Settings → Deploy keys (read-only)
printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n' >> ~/.ssh/config
git clone git@github.com:afrovending/Main-Marketplace.git /opt/afrovending
cd /opt/afrovending/deploy
cp .env.staging.example .env && cp ../backend/.env.example .env.production && cp .env.backup.example .env.backup
nano .env .env.production .env.backup && chmod 600 .env .env.production .env.backup
docker run --rm caddy:2-alpine caddy hash-password --plaintext '<staging-site-password>'   # paste into STAGING_AUTH_HASH
bash scripts/deploy.sh <commit-sha>
curl -fsS https://staging.afrovending.com/api/v1/health
```
Afterwards: bootstrap the Super Admin, enrol MFA, use **Stop New Orders** until testing, run the checks in STAGING_PLAN §4 step 8, then the restore drill.

## 8. Outstanding blockers
1. ~~Rotate the exposed preview admin password~~ Rotated and sessions revoked. The owner still has to set the new password via the secure card. Choose the export path: Save to GitHub (full history, old password now useless) or the sanitized single-commit export.
2. **Emergent managed storage outside Emergent is unconfirmed.** Known: authentication uses the Emergent universal key, a 5 GB quota per organization, no delete support, and no separate storage charge within the quota. Not documented: support for external hosting, SLA, bandwidth/rate limits, redundancy, export. Ask support@emergent.sh with the job ID, or switch to DigitalOcean Spaces (about $5/month, already used for backups).
3. Atlas details not yet confirmed (tier/region/network entry/hostname).
4. The GitHub repo must be **private**. Add the `staging` Environment with a required reviewer before using the deploy workflow.
5. A Stripe test webhook for the staging URL plus its signing secret. `RESEND_WEBHOOK_SECRET` is still not set.
6. Policies are still Pending Legal Review (expected for staging).
