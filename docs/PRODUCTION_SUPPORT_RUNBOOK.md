# AfroVending — Production Support & Incident Response

## Severity levels
| Level | Examples | First response | Update cadence |
|---|---|---|---|
| SEV1 | Site down, checkout charging incorrectly, data leak, admin account compromised | 15 min | every 30 min |
| SEV2 | Sign-in, activation or vendor orders broken for many users; emails not sending | 1 h | every 2 h |
| SEV3 | A single feature degraded; workaround exists | 1 business day | daily |
| SEV4 | Cosmetic issue or question | 3 business days | — |

## On-call steps
1. **Detect.** Signals: uptime alert, a `/api/v1/health` failure, a 5xx spike, a support ticket, a cron failure, or a Stripe dashboard alert.
2. **Triage.** Assign a severity. Open an incident note with the time, symptoms and request ids from the logs.
3. **Contain:**
   - Payments: disable checkout. For a suspected leak: rotate JWT_SECRET (signs everyone out), WEBHOOK_CRON_SECRET and the Stripe keys.
   - Accounts: suspend the affected admins; changing a role revokes their sessions.
   - Bad deploy: roll back with the platform's rollback to the last good checkpoint.
4. **Fix and verify.** Re-run the affected tests. For data, restore with `scripts/restore_verify.sh` into a scratch database first. Never edit the ledger; add adjustments instead.
5. **Communicate.** Message affected customers and vendors only with the owner's approval. If personal data was exposed, notify as the law requires; the owner and counsel decide.
6. **Review.** Write a post-incident note within 5 business days covering the timeline, root cause, fix and prevention. Record it in DECISION_LOG if the policy changes.

## Routine operations
- **Daily:** backup (`scripts/backup_db.sh`), copied off the server. Check cron runs: payouts, handling alerts, abandoned carts, wishlist alerts.
- **Weekly:** review the 5xx rate and slow requests; review the moderation queues and support tickets.
- **Monthly:** restore drill (`scripts/restore_verify.sh`), review admin access, check the dependency updates.
- **Support channels:** support tickets (`/support`), the contact form inbox (CONTACT_INBOX), and vendor order messages.

## Key contacts
[Owner name / phone], [Hosting or DigitalOcean account holder], [Registrar], [Stripe account owner], [Legal counsel]. These are placeholders for the owner to fill in.
