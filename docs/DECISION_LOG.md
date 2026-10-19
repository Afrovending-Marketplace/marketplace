# AfroVending — Decision Log

| ID | Date | Decision | Rationale / status |
|---|---|---|---|
| D-001 | 2026-10-17 | Use platform stack React + FastAPI (Python) + MongoDB instead of Next.js/TypeScript/PostgreSQL. | Approved by owner. Equivalent collections, indexes, transactions and server-side authorization designed. |
| D-002 | 2026-10-17 | ObjectId `_id` exposed as string `id`; FKs `<entity>_id`; separate human numbers (e.g. `order_number`). | Mongo-native, stable API ids. |
| D-003 | 2026-10-17 | Money as integer minor units + ISO currency. | Avoids float rounding in commission/payout math. |
| D-004 | 2026-10-17 | Single `users` collection with `roles` array; vendors are a separate business entity owned by a user. | Rule: no duplicate user tables. Supports vendor team members later. |
| D-005 | 2026-10-17 | Central entity registry in code + generated DATABASE_SCHEMA.md; indexes created only for active phases via versioned migrations. | Docs always match code; no premature collections. |
| D-006 | 2026-10-17 | Default currency USD seeded as an **assumption**. | Pending owner confirmation (markets/currencies). |
| D-007 | 2026-10-17 | Default commission rate left `null`. | Business decision required before Phase 07. |
| D-008 | 2026-10-17 | API versioned under `/api/v1`; uniform error envelope with request_id. | Stable contracts for future clients/mobile. |
| D-009 | 2026-10-17 | `/api/v1/system/schema` disabled (404) when `APP_ENV=production`. | Avoid exposing internals publicly. |
| D-010 | 2026-10-17 | Auth provider choice deferred to the auth phase kickoff (now Phase 02). | One provider only, selected with owner. |
| D-011 | 2026-10-17 | Owner defined Phase 01 = Public Storefront. Roadmap renumbered (auth → 02, vendor onboarding → 03, catalog → 04, storefronts+search → 05). Entity registry `phase` metadata updated; no DB fields/collections changed. | Owner instruction. |
| D-012 | 2026-10-17 | Primary clay darkened to #B24B25 for WCAG AA text/button contrast; original #C85A32 kept as `av-clay-bright` (decorative). | axe-core color-contrast failures on links and primary buttons. |
| D-013 | 2026-10-17 | Storefront dev data lives in the frontend (`data/dev/catalog.js`) behind `lib/catalog.js`; no catalog collections created early. | Avoids premature schema/business logic; one swap point for Phase 04/05. |
| D-014 | 2026-10-17 | Newsletter and contact forms validate input only and state clearly that nothing is saved or sent. | No email/support integration exists yet. (Contact form superseded by D-019.) |
| D-015 | 2026-10-17 | Auth = email + password, JWT (15-min access / 7-day refresh) in httpOnly Secure SameSite=None cookies, backed by revocable `sessions` docs (`sid` claim). One `users` collection for all roles. | Owner choice. `auth_providers[]` lets Google sign-in link to the same user by email later (no duplicate accounts). |
| D-016 | 2026-10-17 | Super admin seeded from `ADMIN_EMAIL`/`ADMIN_PASSWORD` env (strong-password policy enforced at boot). Staff admins only via `POST /admin/staff` (super_admin). | Owner requirement; rotate secret before production. |
| D-017 | 2026-10-17 | Rate limits in Mongo `rate_limits` (TTL). Client IP = rightmost `X-Forwarded-For` entry; plus per-account login lockout (20/15 min) independent of IP. | Fix for XFF spoofing found in testing. |
| D-018 | 2026-10-17 | Email via Emergent managed Resend. Sender address is platform-managed and cannot be info@afrovending.com; display name "AfroVending", Reply-To info@afrovending.com. | Managed service; custom sending domain not supported by the managed integration. |
| D-019 | 2026-10-17 | Contact form emails info@afrovending.com from a fixed server template; logged to `contact_messages`. | Owner request. **Delivery pending**: afrovending.com DNS currently refuses MX queries, so the provider rejects the recipient. |
| D-020 | 2026-10-17 | Brand red #D40000 (logo red) replaces terracotta for `av-clay` / `--primary`; hover #B00000. Contrast 5.5:1 on white (AA). | Owner request. |
| D-021 | 2026-10-17 | Vendor stores moved to Phase 03 (`vendor_stores`); media/documents in Emergent object storage (`files`). Verification status lives on the application (`verification_status`); `vendor_verifications` is reserved. Docs retained during review/active life + 90 days, admin soft delete. | Smallest change that meets onboarding needs. |
| D-026 | 2026-10-19 | Search uses MongoDB text + regex-prefix fallback and indexes, not an external engine. | Catalog is pre-launch (0 live products); tested to 1,500 products. Revisit (Atlas Search/Meilisearch) past ~50k products. |
| D-027 | 2026-10-19 | Search analytics are anonymous (no user/IP), redacted, DNT/GPC-aware, k=2 reporting threshold, 180-day TTL, super-admin purge. | Privacy by default. |
| D-028 | 2026-10-19 | Weekly low-stock digest via platform cron (Mon 09:00 UTC) with per-vendor preference; instant emails remain default. | Owner request; platform-managed scheduling. |
| D-023 | 2026-10-19 | Every product has ≥1 variant (a "Default" variant when no options); stock lives in `inventory` per variant; all changes recorded in append-only `stock_adjustments`. Variant SKUs are uppercase and globally unique. | One stock model for simple and optioned products; safe audit trail. |
| D-024 | 2026-10-19 | Products visible publicly only when status=active AND vendor active AND store published. Edits to content/images/variant structure of a live product return it to pending_review. Ever-live products can't be deleted, only archived. | Moderation integrity; preserves history for future orders. |
| D-025 | 2026-10-19 | Storefront keeps labelled dev data until the first live product exists, then uses `/api/v1/catalog/storefront` only (no mixing). | Avoids empty storefront before launch without mixing fake and real items. |
| D-022 | 2026-10-17 | Rejected applicants may start a new application (old one kept). Admin decisions claim the application atomically before creating the vendor. Opaque tokens are hex (email safety gate rejected random text containing "cvv"). | Fixes from Phase 03 testing. |
