# AfroVending — Phase 14 Completion & Launch Readiness Report (2026-11-09)

**Status: Phase 14 preparation COMPLETE.** Launch is **NOT authorized.**
- No production deployment, DNS change, live payments or launch emails have happened.
- The old website has not been changed.

## 1. Staging website
- **Production-like staging (preview):** https://culture-to-commerce.preview.emergentagent.com
  - Clean database: 1 Super Admin, 43 categories, and 0 vendors, products and orders.
  - Stripe is in TEST mode.
  - The preview shows sample products while the catalog is empty. Set `localStorage.av_no_sample = "1"` in the browser to see the clean-launch view.
- **Production:** not deployed yet. On the first deploy, Emergent provides `<app>.emergent.host` with its own managed database and automatic SSL. afrovending.com is then attached (see §7).

## 2. Phase 13 security audit — final status
| Finding | Severity | Status | Evidence |
|---|---|---|---|
| F1 Last-unit overselling | High | **Resolved** | qa_audit test_10, retest_fixes, iter21, prelaunch test_01 (two real checkouts at once: one succeeds, one gets 409); iterations 27–29 |
| F2 Rate-limit IP behind the proxy | High | **Resolved** | Live preview: 6 bad logins → 429. Spoofed X-Forwarded-For, X-Real-IP and CF-Connecting-IP don't get around it. A different email is not locked out. |
| F3–F6, F8 (Medium) | Medium | Resolved | retest_fixes 5/5, iter21 4/4 |
| Refund of unshipped units could still ship (found 2026-11-09) | High (money/goods) | **Resolved** | Refunded units that never shipped are cancelled and their stock released, and a fully refunded order becomes *cancelled*. Refunding a shipped unit never cancels the unshipped ones. test_phase15_t1_refund_cancel 7/7 (iteration 29) |
| R1–R9 (Low) | Low | Documented | R9 (backups/monitoring) was partly addressed by the backup and restore drill. |

**No Critical or High issue in the code is open.** The remaining launch blockers are configuration and approval items (§10).

## 3. Feature checklist
| Area | Status | Verified by |
|---|---|---|
| Registration, email verification, login and logout, password reset, account, addresses | Completed | phase02 13/13; UI test in iteration 27. Reset was confirmed through the API; the UI reset-link check was inconclusive because of how the test was set up. |
| Vendor application → admin approval → store profile → public store | Completed | phase03; UI test in iteration 27 |
| Product listings (variants, stock, images, moderation, search, categories) | Completed | phase04 5/5, phase05 7/7 |
| Cart (multi-vendor), shipping, coupons, Stripe TEST checkout (4242) | Completed | phase06, phase07 7/7, phase12 9/9; real Stripe test checkout at 390 px |
| Orders, fulfillment (ship/track/deliver, pickup), packing slips, delay alerts | Completed | phase08 12/12 |
| Refunds (full/partial), immutable ledger, commission reversal | Completed | prelaunch test_05/06, refund_cancel 7/7 |
| Vendor dashboard and statements | Completed | phase09 5/5 |
| Admin roles, MFA, audit log, support tickets | Completed | phase10 4/4, admin_spot 3/3 |
| Reviews, seller ratings, order messaging, notifications | Completed | phase11 7/7 |
| Marketing: coupons, referrals, analytics, SEO, wishlist alerts, price badge | Completed | phase12, phase13 wishlist 3/3 |
| Launch checklist, Founding Vendor badge and page, legacy redirects, launch banner | Completed | phase14 suites (5/5, 6/6, 5/5, 24/24, 5/5) |
| Mobile usability (390 px) on key pages | Completed | Iterations 27–29. No overflow. **Minor:** some checkboxes, radios and password toggles are smaller than 24 px. |
| **Stripe Connect onboarding, transfers and payouts** | **Incomplete: SIMULATED** | Needs Connect enabled on the claimed Stripe account |
| **Live payments** | Not enabled (by design) | Needs your authorization |
| **Branded email from afrovending.com** | Not configured | Needs domain verification |
| **Abandoned-cart and wishlist marketing emails** | Built, switched **OFF** | Need your approval |
| Paid vendor subscriptions and sponsored listings | Built, **disabled** | Pricing not approved |
| GA4 | Disabled | No Measurement ID yet |
| Production DNS, SSL and custom domain | Untested | Can only be tested after deploy |

## 4. Stripe Connect and payment readiness
- **Ready now:** Stripe test-mode checkout; verified, idempotent webhooks; multi-vendor separate charges with transfer groups; commission precedence (vendor → category → default 10%, with plan rates 10/7/5%); refunds, disputes and holds; an immutable ledger; and the 7-day payout eligibility calculation.
- **Not ready:**
  - Stripe Connect isn't enabled on the account, so connected-account onboarding, transfers and payouts are **simulated**.
  - Live keys aren't in use.
- **To go live (your actions):**
  1. Claim the Stripe sandbox (Manage → Payments → "Claim your sandbox") and complete verification (KYC).
  2. Enable **Connect** on that account. Emergent's knowledge base doesn't cover Connect on managed sandboxes, so confirm with support@emergent.sh.
  3. Re-run the payout tests against Connect test accounts.
  4. Give your separate approval for live mode.

## 5. Admin MFA and role permissions
- **MFA:** the one active admin (Super Admin) is enrolled. Admin API access needs an MFA-verified session. The checklist's *admin_mfa* auto-check finds every unenrolled admin; any admin you invite must enroll before launch.
- **Roles (tested):**
  - super_admin has everything.
  - finance_admin is the only role that can issue refunds and payouts.
  - marketplace_admin handles vendors, catalog and applications, can view finance, and can't change commission rates or credentials.
  - support_admin handles tickets and customers and can't issue refunds.
  - content_admin handles homepage, banners and promotions only.
  - Customers and vendors get 403 on admin endpoints.
  - Vendors are isolated from each other (403/404 on another vendor's products and orders).
  - The last Super Admin can't be removed, and role changes revoke the person's sessions.

## 6. Email (Resend) and notifications
- **Working:** transactional email through Emergent Managed Resend: verification, reset, orders, shipping, refunds, review replies and support. In-app notifications and per-user preferences work. Outside production, email goes only to an allowlist.
- **Needed:**
  1. Verify **afrovending.com** as the sending domain (SPF, DKIM and DMARC records).
  2. Set the sender address, e.g. no-reply@afrovending.com.
  3. Test unsubscribe end to end.
  4. Approve switching on the marketing emails (abandoned cart, wishlist digest).
  - **Clarification needed:** the Emergent support guide says a custom sending domain needs **your own Resend account and API key**. If you want a custom domain, that is one extra subscription.

## 7. Domain, SSL, DNS and redirect cutover
- **Today:** afrovending.com doesn't resolve. DigitalOcean name servers refuse the zone, and www has no records. The domain is registered until 2027-01-16.
- **Plan:**
  1. Fix DNS hosting: re-add the zone at DigitalOcean, or point the name servers to your preferred DNS provider. Lower the TTL to 300.
  2. Deploy, then go to Manage → Domain and add afrovending.com and www. Use Auto-Link, or set apex A records `162.159.142.117` and `172.66.2.113` plus `www` CNAME → apex (per Emergent's guide).
  3. Choose **afrovending.com as the primary domain** so www → apex. SSL is issued automatically, usually within 5–15 minutes.
  4. In the production secrets, set FRONTEND_URL to `https://afrovending.com`.
  5. On the in-app checklist, run the DNS and SSL checks; both must show Verified.
- **Redirects:**
  - Matching old pages and about 30 old categories send visitors to their new equivalents.
  - /product-tag/* goes to search.
  - Unrelated or removed pages show 404, never the homepage.
  - Redirects work inside the app (browser-side 301 equivalent).

## 8. Backup and rollback
- **Backup:** `backend/scripts/backup_db.sh` creates a gzip archive, a SHA-256 checksum and per-collection counts, and keeps the newest 14.
- **Restore drill:** `restore_verify.sh` restores into a scratch database and compares the counts. Latest drill: PASS.
- **Production:** run the backup every day and copy it off the server (30 daily and 12 monthly copies). Repeat the restore drill every month.
- **Rollback:**
  - App: use the Emergent platform rollback to a checkpoint.
  - DNS (within 72 h): put the old records back; with TTL 300 this takes about 5 minutes. Data from the window stays in the new database.
- **Old site:** you or the host need to make an archive backup first (droplet snapshot, MySQL dump, storage zip, checksums).

## 9. Costs, subscriptions and configuration
| Item | Cost (per Emergent support guide; please confirm) |
|---|---|
| Emergent deployment | **50 credits/month (~US$10)**, including managed MongoDB and SSL. The deployment stops if credits run out. |
| Custom domain on Emergent | No extra Emergent cost |
| Domain registration | Your registrar's renewal (expires 2027-01-16) |
| Stripe | No monthly fee. Standard transaction fees, plus Connect fees for payouts. |
| Resend custom sending domain | Possibly your own Resend plan; see resend.com pricing |
| GA4 | Free (optional) |
| Old site hosting (DigitalOcean) | Keep paying until the archive is confirmed, then cancel with your approval |
| Uptime monitoring | Free tiers exist (e.g. UptimeRobot); optional |

**Configuration still needed:**
- Production secrets: FRONTEND_URL, plus Stripe through the claim flow.
- CONTACT_INBOX.
- Every admin enrolls MFA.
- Legal review of the Terms, Privacy Policy and vendor agreement.

## 10. Final launch readiness checklist
| # | Item | Owner | Status |
|---|---|---|---|
| 1 | Critical and High audit findings resolved | Dev | ✅ Verified (iterations 19–29) |
| 2 | End-to-end buyer, vendor and admin tests | Dev | ✅ Verified (iterations 27–29) |
| 3 | Backup and restore drill | Dev | ✅ PASS on staging |
| 4 | Clean database (no legacy data) | Dev | ✅ Verified |
| 5 | Old-site archive backup | You / host | ⛔ Open |
| 6 | Fix DNS delegation | You | ⛔ Open |
| 7 | Deploy, attach the domain, SSL, FRONTEND_URL | You + Emergent | ⛔ Open (needs your approval) |
| 8 | Claim Stripe, enable Connect, authorize live mode | You | ⛔ Open |
| 9 | Admin MFA for every admin | Admins | 🟡 Super Admin done |
| 10 | Email sending domain, then approve marketing emails | You | ⛔ Open |
| 11 | Legal review | You / counsel | ⛔ Open |
| 12 | Uptime monitor and alert contacts | You | ⛔ Open |
| 13 | In-app checklist (/admin/launch) all Verified → final approval → record the launch date | Super Admin | Pending |

## 11. Proposed Phase 15 — Post-Launch Operations and Growth (for approval)
1. **Launch operations (weeks 0–2):** watch the dashboard (errors, checkout success rate, webhook failures), an incident rota, a daily backup check and a vendor support queue.
2. **Vendor acquisition:** the Founding Vendor recruitment kit (share cards, referral links), onboarding progress emails and a listing-quality score.
3. **Buyer growth:** marketing emails once approved, SEO content pages for categories, social sharing, and a review-request email after delivery.
4. **Payments maturity:** Stripe Connect onboarding and payouts, automated payout statements and a 1099 readiness review.
5. **Trust and safety:** a fraud review queue, vendor performance scores and an automated policy for late shipments.
6. **Analytics:** a weekly owner KPI email (GMV, orders, active vendors, conversion) and cohort retention.
7. **Monetization (needs approved pricing):** paid vendor plans and disclosed sponsored listings.
8. **Accessibility and mobile polish:** 24 px+ tap targets and screen-reader labels (the remaining Low items).
