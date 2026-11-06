# AfroVending — Phase 13 Audit Report (2026-11-06)

Environment: preview, Stripe test mode, test fixtures only. No production deploy; no real payments; no emails to real customers.

## Executive summary
The audit covered authentication and authorization (7 roles + MFA), vendor and customer data isolation, input validation, injection and XSS, CSRF, uploads, payments and webhooks, inventory, multi-vendor orders, refunds and commissions, mobile layout and accessibility, SEO, performance, backups and monitoring.
- It found **2 High** and **4 Medium** issues. All of these are fixed and retested.
- The **9 Low** issues are listed below.
- **There are no Critical issues and no open launch blockers in the code.**
- Several things outside the code are still needed before launch (see the final section).

## Findings — fixed in Phase 13
| # | Severity | Issue | Repro | Files | Fix |
|---|---|---|---|---|---|
| F1 | High | Two shoppers could both be charged for the last unit, because stock was only reserved when the payment webhook arrived. | Stock 1; two buyers start Stripe checkout at the same time and both pay; both orders end up paid. | api/v1/payments.py, core/payments.py | Stock is now reserved atomically when the Checkout session is created; the second buyer gets 409 `out_of_stock`. The stock is released exactly once on cancel, expiry or failure, and mark_paid skips the reservation when stock is already held. |
| F2 | High | Rate limits were keyed on the load balancer's IP, so every visitor shared one bucket. Anyone could also lock any account by failing its login a few times. | Check `rate_limits` keys: every key shows the load balancer IP. | core/security.py `client_ip` | Uses the `TRUSTED_PROXY_HOPS` hop count (default 2). When that hop is a Cloudflare address, the client address is taken from CF-Connecting-IP or the entry Cloudflare added. Addresses the client writes into the header are never trusted. Retest: 6 bad logins from one client now return 429, and other visitors are not affected. |
| F3 | Medium | Missing HSTS, X-Frame-Options and Referrer-Policy headers, so the admin console could be framed (clickjacking). | `curl -I /api/v1/health` | core/logging.py | Added the three headers to every API response. The hosting/ingress layer must add the same headers for the React app. |
| F4 | Medium (privacy) | Outside production, email could reach real addresses stored in the preview database. | Any notification sent to a real address in preview. | core/email.py `try_send` | Outside production, email only goes to example.com, resend.dev, the admin address and the `EMAIL_TEST_ALLOWLIST` entries. Everything else is skipped and logged. |
| F5 | Medium | The 9:00 AM ET send time relied on the scheduler's timezone setting. | Read crons.yml and the code. | core/wishlist_alerts.py, .emergent/crons.yml | The job now runs hourly and the code sends only during the 9 AM US Eastern hour, so daylight saving time is handled. |
| F6 | Medium (consumer protection) | A brief price markup could create a fake "X% off" alert. | Raise the price for one run, then lower it again. | core/wishlist_alerts.py | A higher price only becomes the new reference after it has held for 7 days. |
| F8 | Medium | If creating the Stripe session failed, or the amount check failed, the held stock was never released, and retrying the order was stuck on "payment in progress". | Make the Stripe call fail during checkout, then retry. | api/v1/payments.py | The payment is marked failed and the stock is released once. The order's attempt counter now goes up before stock is reserved, so a retry gets a new payment. mark_paid now reads the claimed payment record. Retest: test_phase13_iter21 4/4. |
| F7 | Low | Cron failure logs were mislabelled, and the health endpoint showed an old version. | — | api/v1/cron.py, core/config.py | Corrected both. |

## Remaining Medium/Low findings (not launch blockers)
| # | Severity | Issue / feature | Repro | Recommended fix | Effort | Priority | Launch impact |
|---|---|---|---|---|---|---|---|
| R1 | Low | Wishlist alerts: an alert is recorded before that day's email slot is claimed, so a change found after the digest went out is never emailed. | Two price drops on one day, the second found after that day's email went out. | Carry undelivered alerts into the next day's digest. | S | P3 | None |
| R2 | Low | Uploads are not checked against the file's actual contents (magic bytes). Mitigated: files are served with their declared type and nosniff. | Upload HTML bytes as image/png. | Check magic bytes on upload. | S | P2 | None |
| R3 | Low | The CSRF origin guard allows a request when the Origin header is missing. | A POST with no Origin header. | Fall back to checking Referer. | S | P2 | Low |
| R4 | Low | Failed cron runs don't raise an alert. | — | Email the admin when a cron run fails. | S | P2 | Operations |
| R5 | Low | Home, shop, cart and account pages have no canonical link, social preview tags or structured data. | View the page source. | Add `<Seo>` to these pages. | S | P2 | SEO |
| R6 | Low | Some icon-only switches and filter buttons have no aria-label for screen readers. | Screen reader. | Add aria-labels. | S | P2 | Accessibility |
| R7 | Low | The wishlist threshold label is fixed at "5%" and the toggles show no error message. | — | Use the admin's threshold in the label and add toasts. | S | P3 | None |
| R8 | Low | The admin threshold input accepts decimals and shows an error in basis points. | Enter 0.5. | Use whole-number % validation. | S | P3 | None |
| R9 | Low | The runbook has no restore drill, RPO/RTO targets or monitoring section. | docs/DEPLOYMENT_RUNBOOK.md | Add a mongodump/mongorestore procedure, RPO/RTO, alerts on 5xx and cron failures, and log retention. | M | P1 before launch | Operations |

## Test results (all re-run after the fixes, one file at a time)
| Suite | Result |
|---|---|
| test_phase07_payments (webhook dedupe, a redirect never marks an order paid, refunds, ledger) | 7/7 |
| test_phase08_fulfillment (multi-vendor, partial shipment, inventory, returns) | 12/12 |
| test_phase10_admin (role permissions) | 4/4 |
| test_phase11_trust (reviews, message privacy) | 7/7 |
| test_phase12_marketing (coupon funding, analytics, consent, referrals) | 9/9 |
| test_phase13_qa_audit, by the testing agent (CSRF, injection, isolation, uploads, lockout, cron secrets, roles, headers, last-unit oversell) | 9/10 at first; 10/10 after F1 |
| test_phase13_retest_fixes, by the testing agent (client IP, reservation release, headers, email allowlist) | 4/5 at first; 5/5 after the Cloudflare-aware F2 fix |
| test_phase13_seo_perf (sitemap: 51 URLs, all resolve; robots; API about 0.15–0.2 s) | 3/3 |
| test_phase13_wishlist_alerts (5% threshold, daylight saving, consent, dedupe, restock) | 2/2 |
| UI at 390px (home, shop, product, cart, checkout, account, vendor, admin) | No overflow, no broken images, no JS errors |

## Security recommendations
- Confirm `TRUSTED_PROXY_HOPS` in production by logging the raw X-Forwarded-For header once.
- Add the security headers at the frontend host.
- Rotate JWT and cron secrets at launch.
- Require MFA enrollment for every admin.
- Close R2 and R3.

## Performance recommendations
- Public API p50 is about 0.15–0.2 s.
- Product images already have thumbnails; add width/height attributes and lazy-load below the fold.
- Watch the `analytics_events` volume. Its TTL is 400 days.

## Production launch readiness
**Code: ready for staging sign-off. Production: not approved and not deployed.** These are still needed before launch:
1. Verify the afrovending.com sending domain, then approve the marketing switches. Abandoned-cart and wishlist emails are OFF.
2. Activate Stripe Connect and approve live payments. Live payments are OFF.
3. Approve pricing and billing for paid plans and sponsored listings. Both are locked OFF.
4. Complete the backup and restore drill and the monitoring setup (R9).
5. Get legal review of the Terms and Privacy Policy drafts.
