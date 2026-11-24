# AfroVending: Self-hosting on DigitalOcean (Docker)

Status: **prepared, not deployed.** Every step marked 🔒 needs the owner's explicit approval first. Do not change DNS, shut down the old site, enable live Stripe or turn on production email without that approval.

## 1. Architecture

```
Visitors ──HTTPS──> DigitalOcean Cloud Firewall (22 from your IP only, 80, 443)
                         │
                ┌────────▼──────── Droplet: Ubuntu 24.04, 2 vCPU / 4 GB ───────────────┐
                │  web (Caddy): automatic Let's Encrypt, www→apex redirect, headers,   │
                │               serves the React build, proxies /api → backend         │
                │  backend (FastAPI/uvicorn ×2 workers, non-root, health-checked)      │
                │  cron (busybox crond → /api/v1/cron/* with bearer secret)            │
                │  backup (nightly 06:00 UTC: mongodump → restore drill → AES-256)     │
                └──────┬─────────────────┬──────────────────┬──────────────────┬───────┘
                       │ TLS             │ HTTPS            │ HTTPS            │ encrypted copy
              MongoDB Atlas      Emergent managed    Resend (email) +    DigitalOcean Spaces
            (IP allow-list:       file storage       Stripe (payments)   (off-Droplet backups)
             Droplet only)
External: UptimeRobot (free) checks https://afrovending.com/api/v1/health every 5 minutes
```

Files are in `deploy/`: `docker-compose.yml`, `web.Dockerfile`, `backend.Dockerfile`, `backup.Dockerfile`, `Caddyfile`, `cron/`, `backup/nightly.sh`, `scripts/server_setup.sh`, `scripts/deploy.sh`, `scripts/rollback.sh`, plus the `.env*.example` templates. No secrets go into images or git (`.dockerignore` and `.gitignore` exclude every `.env`).

## 2. Monthly costs (estimates, USD. Check current pricing)
| Item | Est. cost |
|---|---|
| Droplet Basic 2 vCPU / 4 GB / 80 GB SSD (includes 4 TB transfer) | $24 |
| Droplet weekly backups (+20%) | ~$5 |
| Spaces bucket (250 GB + 1 TB transfer) for encrypted DB backups | $5 |
| MongoDB Atlas: **Flex** tier (daily snapshots). The free M0 tier has no backups, so don't use it in production | ~$8–30 |
| Resend: free up to 3,000 emails/month (100/day); Pro is $20/month for 50k | $0–20 |
| Emergent managed storage | billed through your Emergent balance; confirm with Emergent support before launch |
| UptimeRobot free, Let's Encrypt certificates | $0 |
| **Total** | **≈ $42–85/month** |

**When to upgrade:** move to Atlas M10 (~$57/month, point-in-time restore) once you take real orders every day or the data passes 5 GB. Move to a 4 vCPU / 8 GB Droplet when CPU stays above 70% or memory above 80% for a sustained period. Add a second Droplet behind a load balancer when you need zero-downtime deploys.

## 3. Accounts to create (owner)
1. **DigitalOcean:** a Droplet (Ubuntu 24.04, 2 vCPU / 4 GB, region NYC3, add your SSH key, enable backups and monitoring), a Cloud Firewall (inbound 22 from your IP only, 80 and 443 from anywhere) and a Spaces bucket `afrovending-backups` (private) with an access key limited to that bucket.
2. **MongoDB Atlas:** a Flex cluster in AWS us-east-1, a database user with a strong password, and under Network Access only the Droplet's IP (never 0.0.0.0/0). Copy the `mongodb+srv://` connection string into `MONGO_URL`.
3. **Resend:** see section 6.
4. **UptimeRobot:** an HTTP(s) monitor on `https://afrovending.com/api/v1/health`, every 5 minutes, alerting info@afrovending.com.

## 4. Server setup (once)
```bash
scp deploy/scripts/server_setup.sh ~/.ssh/id_ed25519.pub root@<droplet-ip>:/root/
ssh root@<droplet-ip> 'bash /root/server_setup.sh /root/id_ed25519.pub'
ssh deploy@<droplet-ip>
git clone git@github.com:afrovending/Main-Marketplace.git /opt/afrovending && cd /opt/afrovending/deploy
cp .env.example .env && cp .env.production.example .env.production && cp .env.backup.example .env.backup
nano .env.production .env.backup .env       # fill in the real values
chmod 600 .env .env.production .env.backup
```
`server_setup.sh` disables root and password logins, allows only the `deploy` user, enables UFW (22/80/443), fail2ban and unattended security upgrades, installs Docker with log rotation, and adds 2 GB of swap.

## 5. First deploy 🔒
1. **Staging check without touching DNS:** temporarily set `SITE_DOMAIN=<droplet-ip>.sslip.io` in `deploy/.env` and run `bash scripts/deploy.sh <commit>`. Caddy gets a real certificate for that test name. Test sign-in, MFA, the admin pages and test-mode checkout there.
2. Run the restore drill: `docker compose run --rm backup /usr/local/bin/nightly.sh` (the launch checklist's "Backup & rollback" item then turns Verified).
3. **DNS cutover 🔒** (DigitalOcean → Networking → Domains → afrovending.com): set TTL to 300 a day ahead. Point the `A @` record to the Droplet IP and add `CNAME www → afrovending.com`. Remove the old A records only for the web hosts. **Do not touch MX/TXT records for the info@ mailbox.** Then set `SITE_DOMAIN=afrovending.com` and redeploy.
4. **Rollback:** put the old A record back (TTL 300 means about 5 minutes). For the app itself, run `bash scripts/rollback.sh`, which goes back to the previous image release.

**Updates:** `bash scripts/deploy.sh <reviewed commit>` backs up the database and runs the restore drill, builds versioned images (tagged with the git commit), starts them and checks health. Only deploy commits you have reviewed; there is no automatic deploy from git.

**Database rollback** (only if data has to be reverted): download the `.enc` file from Spaces, then decrypt it with `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in X.enc -out X.archive.gz`, then run `mongorestore --uri "$MONGO_URL" --gzip --archive=X.archive.gz --drop`.

**Patching:** Ubuntu security updates install automatically. Once a month, run `docker compose pull && bash scripts/deploy.sh <same commit>` to rebuild on patched base images and `sudo apt full-upgrade` followed by a reboot if one is needed.

## 6. Resend email setup (owner)
1. Create an account at resend.com, go to Domains → Add Domain → `afrovending.com`, region us-east-1.
2. In DigitalOcean DNS add **exactly the records Resend shows you**: a TXT record `resend._domainkey` (DKIM), an MX and a TXT (SPF) on the `send` subdomain. These are on `send.afrovending.com`, so the existing MX records for info@afrovending.com are not affected.
3. Add a DMARC TXT record `_dmarc` with the value `v=DMARC1; p=none; rua=mailto:info@afrovending.com` (move to `p=quarantine` after 2–4 clean weeks).
4. Click Verify in Resend.
5. Under API Keys → Create a key with "Sending access" restricted to afrovending.com, and put it in `RESEND_API_KEY`.
6. Under Webhooks → add `https://afrovending.com/api/v1/webhooks/resend` with the events delivered, bounced, complained, delivery_delayed and failed. Copy the signing secret into `RESEND_WEBHOOK_SECRET`.
7. Sender addresses used: orders@, vendors@, security@, notifications@ and alerts@afrovending.com. Replies go to info@afrovending.com. These are sending names only and need no mailboxes, but make sure info@ is monitored.
8. 🔒 Production sending stays off (`EMAIL_SENDING_ENABLED=false`) until you approve. Then set it to `true` and redeploy. Failed sends show under Admin → Operations → Email deliveries. Outage detection doesn't depend on this email pipeline, because UptimeRobot alerts you on its own.

## 7. File storage (Emergent managed, owner's choice)
- Public media (product images and thumbnails, vendor logos, banners) is stored under `public/` and served through `/api/v1/files/{id}`. Private items (vendor verification documents, review photos until they're approved, attorney uploads) are stored under `private/` and only reach authorized admins through permission-checked, audited endpoints. Generated lawyer review packs are stored in MongoDB and only download after the Super Admin with MFA approves sharing.
- Uploads are checked for type, size limits and actual content (magic bytes), so executables are rejected. Product images are re-encoded to WebP with a single thumbnail.
- Export or migrate: run `docker compose exec backend python scripts/export_files.py /backups/files-export`. It writes every file plus a `manifest.json` with SHA-256 checksums.
- Before launch, confirm capacity, pricing, bandwidth, redundancy and availability with Emergent support (launch checklist item "storage_review").

## 8. Launch order 🔒
Legal review, then publish the policies → staging check → DNS cutover → Resend verified and sending approved → Stripe live keys and Connect verified (the 10 payment checks) → onboard founding vendors → the Super Admin turns on live orders with MFA → final approval on the launch checklist.
