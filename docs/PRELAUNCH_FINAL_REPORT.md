# AfroVending — Final Pre-Launch Report (2026-11-09)

**Status:** Pre-launch preparation complete. **Launch is not authorized.** No production deployment, DNS change, live payment activation or customer communication has taken place. Phase 15 has not started.

Verification evidence: `/app/test_reports/iteration_27–30.json`, `backend/tests/test_phase15_t1_*.py`, `backend/tests/test_phase16_t1_ops_gate.py` (14/14).

---

## 1. Critical and High security issues — still resolved
| Finding | Severity | Status | Re-verified (iteration 30, 2026-11-09) |
|---|---|---|---|
| Last-unit overselling under concurrent checkout | High | Resolved | Two simultaneous checkouts → one succeeds, one 409 |
| Login rate limit bypass via spoofed proxy headers | High | Resolved | Spoofed X-Forwarded-For still locked out (429) |
| Refunded-but-still-shippable units | High | Resolved | Refunded unshipped units cancelled + stock released; shipping a refunded unit refused; partial-ship case correct (7/7) |
| Medium items F3–F6, F8 | Medium | Resolved | Earlier retests |

**No Critical or High issue is open.**

## 2. Sample products and clean catalog
- The sample catalog is frontend-only display data, shown **only on preview hosts** (`*.preview.emergentagent.com`, localhost). On afrovending.com and `*.emergent.host`, it never loads.
- Sample products are labelled "not for sale", Add to cart is disabled, and the cart API rejects them because they don't exist in the database. Verified in iteration 30.
- Production database starts clean: 1 Super Admin, 43 categories, and 0 vendors, products and orders. Only vendor-listed, admin-approved products can be sold.

## 3. Live-order lock (implemented)
- **Production is locked by default.** In any environment with APP_ENV=production, a live Stripe key or non-test Stripe mode, `POST /checkout/start` and `POST /payments/orders/{id}/checkout` return **503 orders_closed** until both of these hold:
  1. Every one of the 10 payment readiness items is **Verified**.
  2. The Super Admin activated live orders with a **fresh authenticator code** and typed `ACTIVATE LIVE ORDERS`.
- The lock is checked on the server at every order attempt. If any payment item stops being Verified, orders close again.
- **Test results never count:** payment items can only be marked Verified in production with live Stripe keys. Connect and payouts also need a real (non-simulated) connected account or payout on record.
- **Emergency "Stop new orders":** Super Admin only, takes effect immediately in every environment, no checklist needed. Resuming needs a fresh authenticator code.
- **While orders are paused:** browsing, wishlists, existing orders, refunds, disputes and fulfilment keep working. The cart and checkout show "Checkout is closed".
- Every activate, deactivate, stop and resume is logged with who, when and a snapshot of the checklist (orders_gate_log plus the audit log).
- Preview (test mode) stays open so test checkout keeps working.

Payment readiness items:
1. Stripe claimed and live
2. Connect enabled with vendor onboarding working
3. Real vendor transfers and payouts
4. Authorization and capture
5. Refunds, partial refunds, chargebacks and reversals
6. Commission and Stripe fee calculations
7. Multi-vendor ledger reconciliation
8. Webhook signatures, retries and idempotency
9. Inventory reservation and overselling
10. Super Admin MFA

## 4. Stripe: claim, Connect, vendor onboarding, payout readiness
**A. Claim and configure Stripe** (after deployment approval)
1. In Emergent: **Manage → Payments → Claim your sandbox**, then sign in to or create the Stripe account for **AfroVending Online Marketplace LLC**.
2. In the Stripe Dashboard, complete business verification: legal name, EIN, address, representative ID, bank account for platform revenue, and statement descriptor "AFROVENDING".
3. Turn on 2-step authentication for every Stripe team member.

**B. Enable Stripe Connect**
1. Dashboard → **Connect → Get started**, then choose platform model **"Marketplace"**, accounts **Express**, and payouts managed by Stripe. This app uses separate charges and transfers, US only, USD.
2. **Settings → Connect → Branding:** set the AfroVending name, icon and colour. **Onboarding:** collect requirements "eventually due".
3. Complete Stripe's **platform profile and Connect review**, which can take several business days.
4. Emergent's guide doesn't cover Connect on a claimed sandbox, so ask **support@emergent.sh** to confirm before step 5.
5. Add a production webhook endpoint `https://afrovending.com/api/stripe/webhook` with these events: checkout.session.*, payment_intent.payment_failed, charge.succeeded, charge.updated, charge.refund.updated, refund.*, charge.dispute.*, account.updated, payout.paid, payout.failed. Include **Connect events** for account.updated and payout.*. Store the signing secret as the production `STRIPE_WEBHOOK_SECRET` (secrets panel; never in chat).

**C. Vendor onboarding** (after Connect approval)
1. The vendor applies, the admin approves, and the vendor opens **Vendor → Payments → Set up payouts**. The app then creates a real Express account (no longer simulated) and sends the vendor to Stripe's hosted onboarding.
2. Stripe sends account.updated, and the app records transfers_enabled, payouts_enabled and details_submitted.

**D. Verify real payout readiness** (each step is evidence for the matching checklist item)
1. Onboard one real test vendor (a trusted founding vendor, or your own LLC).
2. Make a small live purchase (e.g. $1–$5) → check the receipt, the ledger and the commission.
3. Refund part of it, then the rest → check the ledger reversals.
4. Ship it, wait for the 7-day hold or adjust it, and let payout-release run. Confirm a **real transfer** in Stripe → Connect → Transfers, and the vendor's bank payout arriving (payout.paid).
5. Reconcile: Admin → Payments → reconciliation shows no issues.
6. Record each piece of evidence on /admin/launch. Then the Super Admin activates live orders.

## 5. DNS for afrovending.com and www.afrovending.com
**Current state:** the domain is delegated to DigitalOcean name servers, but the zone is missing, so the lookups fail.

**DigitalOcean steps** (Networking → Domains)
1. **Add domain:** `afrovending.com`. Keep the NS records ns1/ns2/ns3.digitalocean.com. At the registrar, confirm the name servers are exactly ns1/ns2/ns3.digitalocean.com.
2. **Before cutover**, recreate the records the old site needs (if it should stay reachable), with TTL **300**.
3. **At cutover** (only after your approval and the production deploy), in Emergent go to **Deployments → Manage → Domain → Add** `afrovending.com`, then `www.afrovending.com`. Emergent shows the exact values to use; enter them in DigitalOcean:

| Type | Host | Value | TTL |
|---|---|---|---|
| A | `@` | `162.159.142.117` (as shown by Emergent) | 300 |
| A | `@` | `172.66.2.113` (as shown by Emergent) | 300 |
| CNAME | `www` | `afrovending.com.` | 300 |
| TXT | as shown by Emergent (if a verification record is requested) | value shown | 300 |

4. Remove any old A, AAAA or CNAME records for `@`/`www` that point to the old droplet. **Never** have two different A targets plus an AAAA for the same host.
5. Set **afrovending.com as primary**; www then redirects to it, and the app also redirects www → apex. SSL is issued automatically, usually in 5–15 minutes.
6. Set production `FRONTEND_URL=https://afrovending.com` and add it to CORS_ORIGINS. Then run the DNS and SSL checks on /admin/launch; both must show Verified.

The IP values above come from Emergent's guide. **Always use the values Emergent's Domain screen shows at the time.**

## 6. Resend (email) domain verification
Recommended sending subdomain: `mail.afrovending.com`, with sender `AfroVending <no-reply@mail.afrovending.com>` and replies to info@afrovending.com.
1. Emergent support says a custom sending domain needs **your own Resend account** (free plan: 3,000 emails/month, 100/day). Create it at resend.com and turn on 2FA.
2. Go to Resend → **Domains → Add domain** `mail.afrovending.com`, region US East. Resend then shows the exact records; add them in DigitalOcean:

| Type | Host (in DigitalOcean) | Value | Purpose |
|---|---|---|---|
| MX | `send.mail` | `feedback-smtp.us-east-1.amazonses.com` (priority 10) | Bounce handling (SPF return path) |
| TXT | `send.mail` | `v=spf1 include:amazonses.com ~all` | SPF |
| TXT | `resend._domainkey.mail` | long DKIM key shown by Resend | DKIM |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:info@afrovending.com` | DMARC (move to `p=quarantine` after 2–4 weeks of clean reports) |

3. Click **Verify** in Resend (usually minutes, up to 72 h). Then create an API key with "Sending access" only, and I'll request it through the secure secrets card. Never paste it in chat.
4. Afterwards: send test emails to Gmail and Outlook and check SPF, DKIM and DMARC all pass. Then mark "email_domain" Verified.
5. **Marketing emails stay OFF** until you approve them separately. That covers abandoned cart and the wishlist digest, which also need a tested unsubscribe.

## 7. Deployment architecture, costs, backup and rollback
- **Architecture:** Emergent managed hosting with a React static build, a FastAPI backend under `/api` and managed MongoDB in production (a separate database from preview). Automatic SSL, and platform scheduling for 3 cron jobs (crons faster than every 15 minutes are discarded in production).
- **Costs:**

| Item | Cost (per Emergent support guide; please confirm) |
|---|---|
| Emergent deployment | ~50 credits/month (≈ US$10), including the database and SSL. The site stops if credits run out, so turn on auto top-up. |
| Domain renewal | Your registrar (expires 2027-01-16) |
| DigitalOcean DNS | Free. The old droplet keeps costing money until you approve cancelling it. |
| Stripe | No monthly fee. Card fees (~2.9% + 30¢) plus Connect fees per active account and payout. |
| Resend | Free plan to start; Pro is about $20/month if volume grows |
| UptimeRobot | Free plan (5-minute checks, email alerts) |

- **Backups:** `backend/scripts/backup_db.sh` writes a gzip archive with a SHA-256 checksum and collection counts, and keeps the newest 14. `restore_verify.sh` restores to a scratch database and compares counts; the latest drill passed. For production: before cutover, ask Emergent support how to take and restore managed-database snapshots, then run a backup daily, keep it off the server, and repeat the restore drill monthly.
- **Rollback:**
  - App: Emergent rollback to a checkpoint, then redeploy.
  - Orders: use Emergent **Stop new orders** at once (no redeploy needed).
  - DNS within 72 h: put back the old records (TTL 300 means about 5 minutes).
  - Data written in the meantime stays in the new database.

## 8. Administrator MFA
- **Confirmed by code and tests:** every admin endpoint requires an MFA-verified session. Invited admins have no admin access until they enroll an authenticator and verify a code, so they get `403 mfa_required`.
- The Super Admin is enrolled. The checklist items admin_mfa and super_admin_mfa check this automatically.
- **Live-order activation and resume need a fresh authenticator code** (step-up).
- Before production: change the Super Admin password (ADMIN_PASSWORD secret), and use a dedicated, secured admin mailbox.

## 9. Legal policies — present, but NOT ready
Pages exist at /privacy, /terms, /vendor-agreement, /shipping-policy, /returns-policy and /prohibited-products. Each has its section structure, but **every section is placeholder text**, and each page shows "Draft — requires founder and legal review".
**This is a launch blocker.** Counsel needs to supply or approve the text. Points to cover:
- US marketplace terms
- Payments facilitated by Stripe
- Vendor-of-record responsibility
- Returns timelines
- CAN-SPAM marketing consent
- CCPA/state privacy rights
- Cookies and analytics

The cookie and consent settings page already exists.

## 10. Monitoring and error reporting (implemented)
**What is built:**
- **Health checks:**
  - `GET /api/health` and `/api/v1/health` are public and return only `{"status":"ok"}` (503 when the database is down).
  - `GET /api/v1/health/ready` is for Super Admins only and shows each component.
- **Automatic health check every 15 minutes** (the platform minimum in production). It covers:
  - the database and API
  - delayed or failed background jobs
  - Stripe webhook failures and backlogs
  - checkout, payment, email, refund and order errors
  - inventory consistency
- **Incidents:** one per component, never duplicated. Each records UTC times, duration and severity, and you get one alert when it opens and one on recovery.
- **Error log:**
  - Captures server exceptions, 5xx responses, webhook, refund and amount-mismatch failures (critical), email failures, job failures and browser errors.
  - Passwords, tokens, keys, card numbers and emails are removed before saving, and query strings are dropped.
  - Every error carries its correlation ID, and detailed logs are kept for 30 days.
- **Alerts to info@afrovending.com:**
  - critical errors immediately
  - 10 server errors within 5 minutes (you can change this)
  - 60-minute cooldown per incident
  - suppressed outside production
- **Admin → Operations** (/admin/ops, Super Admin only): health, incidents, errors with filters, Acknowledge or Resolve (logged in the audit log), and alert settings. Times are shown in ET.
- A future Sentry hookup can be added in one place (`record_error`).

**External monitor — UptimeRobot (free; you create the account):**
1. Sign up at uptimerobot.com with info@afrovending.com and turn on 2FA.
2. **Add New Monitor → Keyword**:
   - URL `https://afrovending.com/api/health`
   - keyword `"ok"`, alert when not present
   - interval **5 minutes**
   - name "AfroVending API"
3. Add a second **HTTP(s)** monitor for `https://afrovending.com` (the storefront), also every 5 minutes.
4. In the alert contact (email info@afrovending.com), choose to notify **after 2 consecutive failures**. On the free plan, set this per monitor under "Advanced" if offered; otherwise alerts arrive after the first failure. Turn on **recovery notifications**.
5. **Test it:** pause the monitor, change the URL to `https://afrovending.com/api/health-test-404`, and resume it. Within about 10 minutes you should get a "down" email. Change the URL back and you should get a "recovered" email. Because UptimeRobot runs outside Emergent, it alerts even if Emergent hosting is completely down.
6. Then mark the "monitoring" item Verified on /admin/launch.

## 11. Launch Day Checklist (as of 2026-11-09)
| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Critical and High findings resolved | **Verified** | iteration_30 regression 13/13; §1 |
| 2 | End-to-end buyer, vendor and admin tests (staging) | **Verified** | iterations 27–30 |
| 3 | Clean catalog; sample products not purchasable | **Verified** | iteration_30; §2 |
| 4 | Live-order lock + emergency stop | **Verified** (staging) | test_phase16_t1_ops_gate 14/14 |
| 5 | Monitoring and error log built | **Verified** (staging) | iteration_30 |
| 6 | Backup and restore drill | **Verified** (staging) / **Pending** (production) | restore_verify PASS |
| 7 | Super Admin MFA | **Verified** | auto check |
| 8 | Every additional admin has MFA | **Pending** | Enforced by code; no other admins yet |
| 9 | Old-site archive backup | **Blocked** | Needs you or the old host |
| 10 | DNS zone fixed at DigitalOcean | **Blocked** | Zone missing (§5) |
| 11 | Production deploy | **Pending** | Needs your approval |
| 12 | Domain attached + SSL + FRONTEND_URL | **Blocked** | Depends on 10 and 11 |
| 13 | External uptime monitor + alert test | **Pending** | Your UptimeRobot account (§10) |
| 14 | Resend domain verified + test emails | **Blocked** | Your Resend account + DNS (§6) |
| 15 | Legal policy text approved | **Blocked** | Placeholder text (§9) |
| 16 | Stripe claimed + KYC | **Pending** | Your action (§4A) |
| 17 | Stripe Connect approved + real vendor payout | **Blocked** | Depends on 16 + Stripe review |
| 18 | 10 payment readiness items Verified (production) | **Blocked** | Depends on 16–17 |
| 19 | Live orders activated | **Blocked** | Depends on 18 + your approval |
| 20 | Final approval + public launch recorded | **Pending** | Super Admin, last |

## 12. Safe deployment sequence (each stage needs your explicit approval)
1. **Stage 0 — preparation (no approval needed):**
   - Archive the old site.
   - Fix the DigitalOcean zone, recreating the current records with TTL 300.
   - Approve the legal text.
   - Create the UptimeRobot and Resend accounts.
   - Rotate the admin password.
2. **Stage 1 — production infrastructure:**
   - Deploy to `*.emergent.host`. Orders are locked automatically and there's no public domain yet.
   - Smoke-test it, run a backup and restore check, and confirm /admin/ops is healthy.
3. **Stage 2 — domain cutover:**
   - Attach the domain, add the DNS records and wait for SSL. Then set FRONTEND_URL and run the DNS and SSL checks.
   - Point UptimeRobot at afrovending.com and test the alert.
   - The site is reachable, but orders stay locked.
4. **Stage 3 — email:** verify the Resend domain, add the key through the secrets card, and send test emails to your own addresses only.
5. **Stage 4 — live payments:**
   - Claim Stripe and complete KYC. Get Connect approved.
   - Add the live webhook and run the real-money tests in §4D with your own vendor account.
   - Mark the 10 payment items Verified. **Orders are still locked.**
6. **Stage 5 — vendor onboarding:**
   - Invite and approve founding vendors, who complete Stripe onboarding and list products. Admins moderate the listings.
   - Orders stay locked, so vendors can prepare without risk.
7. **Stage 6 — public launch:**
   - Activate live orders (fresh authenticator code).
   - Give final approval, record the launch date, switch on the launch banner, and send announcements (only after approval).
   - Watch /admin/ops. Use **Stop new orders** if anything goes wrong.

## 13. What you need to do, in order
1. Arrange the **old-site archive** with your old host or developer.
2. **DigitalOcean:** add the afrovending.com zone and check the registrar name servers (§5).
3. Have **counsel provide or approve the policy text** (§9).
4. Create **UptimeRobot** and **Resend** accounts, both with 2FA.
5. Decide on and approve **Stage 1 (production deploy)**.
6. Approve **Stage 2 (domain cutover)**.
7. **Claim Stripe**, complete KYC, apply for **Connect**, and confirm Connect with Emergent support.
8. Run the real-money payment tests with one vendor, then approve **live orders**.
9. Have any new admins enroll in MFA, and rotate the admin password.
10. Give final approval and the public launch go-ahead.
