# AfroVending staging plan: DigitalOcean Droplet + MongoDB Atlas

Status: **awaiting the owner's approval of the configuration and costs.** Nothing is created yet. Staging never touches afrovending.com DNS, the existing website, live Stripe, public checkout or marketing email.

## 1. Recommended configuration
| Item | Recommendation | Why |
|---|---|---|
| Droplet | Basic Regular, **2 vCPU / 4 GB RAM / 80 GB SSD**, Ubuntu 24.04 LTS | Same size as planned production, so the staging run proves the size. The React build needs about 2 GB RAM and the app runs at about 1 GB |
| Region | **NYC3 (New York)** | Close to U.S. East customers and to Atlas us-east-1 (about 5–10 ms) |
| Droplet backups | Weekly (+20%) | Enough for staging; nightly encrypted DB dumps cover the data |
| Database | **MongoDB Atlas M0 Free**, AWS **us-east-1 (N. Virginia)** | Staging holds test data only; 512 MB is plenty. Production uses Flex or M10 (M0 has no snapshots) |
| Off-Droplet backups | DigitalOcean Spaces bucket `afrovending-staging-backups`, NYC3, private | Tests the nightly encrypted backup and restore path |
| Monitoring | DigitalOcean Monitoring (free) + UptimeRobot free | Independent of the app's own alert emails |

## 2. Estimated monthly cost (USD, before tax. Confirm on the DigitalOcean/Atlas pricing pages at creation)
| Item | Cost |
|---|---|
| Droplet 2 vCPU / 4 GB | $24.00 |
| Weekly Droplet backups (20%) | $4.80 |
| Spaces (250 GB storage + 1 TB transfer included) | $5.00 |
| Atlas M0 | $0.00 |
| Bandwidth (4 TB included with the Droplet) | $0.00 |
| Let's Encrypt HTTPS, UptimeRobot, DO Monitoring | $0.00 |
| **Staging total** | **≈ $33.80/month** (DigitalOcean bills by the hour, so destroying it afterwards stops the cost) |

Optional: Atlas Flex instead of M0, to mirror production backups: +$8–30/month.
Production later: the same Droplet (≈ $29) + Spaces ($5) + Atlas Flex (≈ $8–30) or M10 (≈ $57) + Resend ($0–20) = **≈ $42–111/month**.

## 3. Credentials and permissions
**Option A: you click, I guide (recommended, no credentials shared).** You need a DigitalOcean account with billing, an SSH key on your computer, and an Atlas account.

**Option B: I provision through the APIs.** You add these through the secure key card only:
- `DIGITALOCEAN_TOKEN`: a Personal Access Token with **custom scopes**: `droplet:create,read,update`, `ssh_key:create,read`, `firewall:create,read,update`, `project:create,read,update`, `monitoring:create,read`, `tag:create,read`. No `domain:*` scope, so DNS can't be touched. Set it to expire in 7 days and revoke it after setup.
- Spaces access key: created by you in the control panel (scoped to the one bucket); its two values go in the secure card.
- `ATLAS_PUBLIC_KEY` / `ATLAS_PRIVATE_KEY`: an Atlas **project-level** API key with the **Project Owner** role on a new project "AfroVending Staging" only, with an access list limited to the Emergent IP shown at that time. Revoke it after setup.
- The staging app itself only needs: the Atlas connection string, Stripe **test** keys, your Resend key, the storage key and newly generated secrets.

## 4. Staging deployment steps
1. Create the Droplet (NYC3, 2 vCPU / 4 GB, Ubuntu 24.04, SSH key only, Monitoring on, weekly backups on, tag `afrovending-staging`).
2. Create a Cloud Firewall: inbound 22/tcp from your IP only, 80/tcp and 443/tcp/udp from anywhere; outbound all. Attach it to the tag.
3. Atlas: create the project "AfroVending Staging" and an M0 cluster in AWS us-east-1. Add the database user `afrovending_staging` with a generated password and **readWrite on `afrovending_staging` only**. Add the Droplet's IP to Network Access (never 0.0.0.0/0).
4. Create the Spaces bucket `afrovending-staging-backups` (private) and a bucket-limited access key.
5. Run `deploy/scripts/server_setup.sh` (it disables root and password SSH, turns on UFW, fail2ban, unattended upgrades and Docker, and adds swap).
6. On the Droplet as `deploy`: clone the repo, then copy `deploy/.env.staging.example` → `.env`, `.env.production.example` → `.env.production` and `.env.backup.example` → `.env.backup`. Fill them in with **`APP_ENV=staging`**, `DB_NAME=afrovending_staging`, `FRONTEND_URL`/`CORS_ORIGINS` = the staging URL, Stripe **test** keys, `EMAIL_SENDING_ENABLED=true`, a new admin password and new JWT, cron and backup secrets.
7. `bash scripts/deploy.sh <reviewed commit>`: this builds versioned images, starts them, waits for HTTPS and checks health.
8. Create the Super Admin (bootstrap), enrol MFA, then run the checks: sign-in, MFA, admin roles, a test vendor and product, Stripe **test** checkout with card 4242…, a refund, an email to an allow-listed address, cron ticks in Operations, then `docker compose run --rm backup /usr/local/bin/nightly.sh` (backup → restore drill → encrypted Spaces copy).
9. Add an UptimeRobot monitor on `/api/v1/health`, then mark **staging_verified** on the launch checklist.

**Expected URL:** `https://<droplet-ip-with-dashes>.sslip.io` (for example `https://203-0-113-10.sslip.io`). It gets a real certificate automatically, and Caddy falls back to ZeroSSL if Let's Encrypt is rate-limited. Optional: if you approve one new DNS record, `staging.afrovending.com` (a new A record only, leaving existing records untouched) gives a cleaner URL.

## 5. Security
- The whole staging site is behind a password (Caddy basic auth). It carries `noindex` and robots `Disallow: /`. Only `/api/v1/health` and the Stripe/Resend webhooks are open.
- SSH key-only for the `deploy` user, with no root login. The DO Cloud Firewall plus UFW, fail2ban and automatic security patches are on.
- Containers run as non-root, have memory/CPU limits and rotated logs. MongoDB isn't on the Droplet at all; Atlas accepts only the Droplet IP over TLS, with a least-privilege DB user.
- Secrets live only in `deploy/.env*` (chmod 600) and never in git or images. Staging uses new secrets that are different from production.
- `APP_ENV=staging`: email goes only to allow-listed test addresses, Stripe is **test mode only**, sample catalog is off, and the production order lock doesn't apply because it's test money only.

## 6. Backups
Atlas M0 has no snapshots, so the nightly container (06:00 UTC) handles backups. It runs mongodump, a restore drill into a scratch database, then an AES-256 encrypted copy to Spaces with 35-day retention. Weekly Droplet backups come on top. The decryption passphrase is stored offline by you.

## 7. Monitoring
- UptimeRobot (every 5 min) watches `/api/v1/health`, independent of the app's email.
- DigitalOcean Monitoring alert policies: CPU > 80% for 10 min, memory > 85%, disk > 80%, sent to info@afrovending.com.
- Inside the app: Admin → Operations (incidents, production errors, email deliveries, cron health). Docker health checks restart unhealthy containers.

## 8. Rollback
- App: `bash scripts/rollback.sh` switches back to the previous image release, which takes seconds.
- Data: decrypt the latest Spaces backup and run `mongorestore --drop` (see LAUNCH_GUIDE_DIGITALOCEAN.md §5).
- Whole server: restore the weekly Droplet backup, or destroy and recreate the Droplet from these steps. Nothing in staging affects afrovending.com.
- To tear down: destroy the Droplet, the bucket and the Atlas project. Billing stops at the next hour.
