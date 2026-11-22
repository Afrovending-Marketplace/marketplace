# AfroVending — Launch Guide: Emergent hosting + DigitalOcean DNS (2026-11-10)

> Every stage below needs the owner's explicit approval. Nothing here has been done yet.

**Where things live:**
- **Emergent** hosts the app: website, API, database, SSL, scheduled jobs, and Stripe, email and file-storage integrations.
- **DigitalOcean** is only the **DNS provider** for afrovending.com. Its name servers are ns1, ns2 and ns3.digitalocean.com.
- You do **not** need a DigitalOcean Droplet or App Platform app.

## Stage 0 — Before you start
1. **Back up the old site.**
   - Take a DigitalOcean droplet **snapshot** under Droplets → (old droplet) → Snapshots, if the old site runs on a droplet.
   - Also export its files and database.
   - Keep the droplet running until the cutover has been stable for 72 hours.
2. **Rotate the Super Admin password** (Emergent secrets panel → `ADMIN_PASSWORD`).
3. **Create accounts:** an UptimeRobot account (free) and, if sending from afrovending.com, a Resend account. Turn on 2FA for both.
4. **Legal:** get counsel's review of all seven policies and record it in Admin → Policy management. Publishing them is required for production sign-up, vendor onboarding and checkout.

## Stage 1 — Repair the DNS zone in DigitalOcean
1. Sign in to cloud.digitalocean.com and go to **Networking → Domains**.
2. If `afrovending.com` isn't listed, enter it and click **Add Domain**. DigitalOcean creates the NS records ns1, ns2 and ns3.digitalocean.com.
3. At your **domain registrar** (where afrovending.com was bought), confirm the name servers are exactly:
   - `ns1.digitalocean.com`
   - `ns2.digitalocean.com`
   - `ns3.digitalocean.com`
4. Re-create any records you still need, such as the email (MX) records for info@afrovending.com. Keep the TTL at **300 seconds** for every record you'll change during cutover.
5. Check the zone resolves: `dig NS afrovending.com +short` should list the three DigitalOcean name servers.

## Stage 2 — Deploy to Emergent production (orders stay locked)
1. In Emergent, click **Deploy**. The first deploy costs about 50 credits a month.
2. Production gets its own empty database. The app creates the Super Admin, the categories and the seven policies (v1, Pending Legal Review) on first start.
3. **Production secrets** (Deployments → Secrets):
   - `APP_ENV=production`
   - `FRONTEND_URL=https://afrovending.com`
   - `CORS_ORIGINS` including `https://afrovending.com` and `https://www.afrovending.com`
   - a new `ADMIN_PASSWORD`
   - `ALERT_EMAIL=info@afrovending.com`
4. **Smoke-test** the `*.emergent.host` URL:
   - `/api/health` returns `{"status":"ok"}`
   - sign in as Super Admin with MFA
   - /admin/ops shows healthy
   - checkout shows **"Checkout is closed"**, because the live-order lock is on by default
5. Take a production backup (`backend/scripts/backup_db.sh`, or ask Emergent support for a managed snapshot).

## Stage 3 — Point afrovending.com to Emergent (domain cutover)
1. In Emergent go to **Deployments → Manage → Domain → Add domain**. Add `afrovending.com`, then `www.afrovending.com`.
2. Emergent shows the exact DNS records to create. In DigitalOcean (**Networking → Domains → afrovending.com → Create new record**), add them exactly as shown:

| Type | Hostname | Will direct to | TTL |
|---|---|---|---|
| A | `@` | IP shown by Emergent (guide lists `162.159.142.117`) | 300 |
| A | `@` | second IP shown by Emergent (guide lists `172.66.2.113`) | 300 |
| CNAME | `www` | `afrovending.com.` (or the target Emergent shows) | 300 |
| TXT | as shown | verification value shown by Emergent, if requested | 300 |

3. **Delete** the old A, AAAA or CNAME records for `@` and `www` that point at the old droplet, so only Emergent's records remain.
4. In Emergent, set **afrovending.com as primary** (www redirects to it). SSL is issued automatically, usually within 5–15 minutes and up to a few hours.
5. Check:
   - `dig A afrovending.com +short` shows Emergent's IPs.
   - `https://afrovending.com/api/health` returns ok over HTTPS.
   - `https://www.afrovending.com` redirects.
   - Run the DNS and SSL checks on **/admin/launch**.
6. **UptimeRobot:**
   - Add a keyword monitor on `https://afrovending.com/api/health` (keyword `ok`) and an HTTP monitor on `https://afrovending.com`, both every 5 minutes, with email alerts to info@afrovending.com.
   - Run the down/recovery test.
7. **Rollback within 72 hours:** restore the old @ and www records in DigitalOcean. With a 300-second TTL this takes about 5 minutes.

## Stage 4 — Email domain (optional at first)
1. In **Resend**, add the domain `mail.afrovending.com`.
2. Add the records Resend shows, in DigitalOcean **Networking → Domains**:
   - MX `send.mail`
   - TXT `send.mail` (SPF)
   - TXT `resend._domainkey.mail` (DKIM)
   - TXT `_dmarc`: `v=DMARC1; p=none; rua=mailto:info@afrovending.com`
3. Verify the domain in Resend, add the API key through the secure secrets card, and send test emails to your own addresses only.

## Stage 5 — Live payments (orders still locked)
1. **Stripe:**
   - Claim the account (Emergent → Manage → Payments) and complete business verification.
   - Apply for **Connect** (Express, marketplace). Confirm the Connect setup with support@emergent.sh.
   - Add the live webhook `https://afrovending.com/api/stripe/webhook`.
2. Run the real-money tests (see `docs/PRELAUNCH_FINAL_REPORT.md` §4D): one small purchase, partial and full refund, a real payout to a trusted vendor, and reconciliation.
3. Mark the 10 payment items Verified on /admin/launch. These items only accept verification in production with live keys.

## Stage 6 — Vendor onboarding
1. Make sure the policies are published.
2. Invite founding vendors. They apply, you approve them, and they connect Stripe and list products, which admins review.
3. Orders stay locked, so vendors can get ready safely.

## Stage 7 — Public launch
1. On /admin/launch, **activate live orders** (fresh authenticator code plus the confirmation phrase).
2. Give the final approval, record the launch date, and turn on the launch banner. Send announcements only after you approve them.
3. Watch /admin/ops and UptimeRobot. If anything goes wrong, click **Emergency: stop new orders**.

## Alternative: hosting the app on DigitalOcean instead of Emergent (not recommended)
**What you could use:**
- DigitalOcean App Platform or a Droplet running the FastAPI backend and the React build
- MongoDB Atlas or DigitalOcean Managed MongoDB
- an Nginx/Caddy reverse proxy that routes `/api` to the backend

**What you'd have to replace,** because these are Emergent-managed:
- the cron scheduler (`.emergent/crons.yml`), replaced by DigitalOcean Functions/cron or system cron calling the same endpoints with `WEBHOOK_CRON_SECRET`;
- object storage for vendor documents and attorney files, replaced by DigitalOcean Spaces (code change needed);
- managed email, replaced by your own Resend account and key;
- the claimed Stripe sandbox, replaced by your own Stripe account keys;
- managed SSL and deploys.

Get the code with **Save to GitHub**. Expect extra setup, monitoring and cost, and a code change for storage.
