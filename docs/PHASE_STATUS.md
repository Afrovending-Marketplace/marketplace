# AfroVending — Phase Status

| Phase | Status | Date |
|---|---|---|
| 00 Project foundation | ✅ Complete | 2026-10-17 |
| 01 Public storefront | ✅ Complete | 2026-10-17 |
| 02 Identity & customer accounts | ✅ Complete | 2026-10-17 |
| 03 Vendor onboarding (+ brand red theme) | ✅ Complete | 2026-10-17 |
| 04 Product catalog & inventory | ✅ Complete | 2026-10-19 |
| 05 Search & product discovery (+ weekly low-stock digest) | ✅ Complete — awaiting owner approval | 2026-10-19 |
| 05–14 | ⏸ Not started | — |

## Phase 05 deliverables
- `GET /api/v1/catalog/search`: MongoDB weighted text index (title 10, tags 5, description 1, English stemming) with relevance sort; automatic word-prefix fallback for partial words ("bask" → basket); filters category (+subcategories), vendor (multi), price min/max, in stock; sorts relevance/featured/newest/price; page+limit (max 120) with `has_more`; facets (category counts unscoped, vendor/price/stock scoped to category).
- `GET /api/v1/catalog/suggest`: keywords (tags), products, categories, vendors by word prefix.
- Storefront `/shop`, `/search`, `/categories/:slug` share one discovery layout: filters (sheet on mobile), chips, sort, Load more, empty and error states; all state in the URL (`q, category, vendor, min, max, in_stock, sort, page`).
- Only active products of active vendors with published stores appear anywhere in search, suggestions or facets.
- Search analytics (`search_queries`): normalized text, result count, filter names, time; no user/session/IP/device; emails & phone numbers redacted; DNT / Global Privacy Control honoured; logged once per distinct search per browser session; TTL 180 days; admin report hides queries seen < 2 times; purge = super admin only. Admin page `/admin/search-insights`.
- Infrastructure: MongoDB indexes only (text, status+price, status+in_stock, tags). Tested at 1,500+ products: < 2 s per query end-to-end over the preview network; no external/paid search service.
- Restock reminders: vendors choose instant per-item emails or a weekly summary (`PUT /vendor/preferences`); platform cron `.emergent/crons.yml` calls `POST /api/v1/cron/low-stock-digest` Mondays 09:00 UTC (Bearer secret, idempotent by run id, work runs in background).

## Phase 04 deliverables
- Vendor products (`/vendor/products`, `/vendor/products/new`, `/vendor/products/:id`): title, description, category (2-level), tags, SKU, price (USD), up to 8 images, low-stock threshold.
- Variants: up to 3 options (e.g. Size/Color/Material), generated combinations, variant SKU (globally unique), price, stock. Removed variants are deactivated (SKU + history kept).
- Images: JPG/PNG/WEBP ≤10 MB, validated with Pillow, EXIF stripped, WebP main (≤1600px) + thumb (480px) in object storage; reorder/delete.
- States: draft → pending_review → active / rejected; archived from any state; restore → draft. Content/image/variant-structure edits on an active product send it back to review; price/stock changes don't.
- Deletion safeguard: only never-live products can be deleted; others are archived.
- Inventory: optimistic-concurrency adjustments (add/remove/set + reason) with append-only `stock_adjustments`; low-stock dashboard banner + email when a variant crosses the threshold.
- Admin: `/admin/products` moderation (approve / reject with note / take down), `/admin/categories` (create, rename, sort, hide, delete empty; hide blocked when live products exist). Vendor emailed on every decision.
- CSV import (`/vendor/products/import`): template, preview with row-level errors, commit valid products as drafts (images added afterwards).
- Public API `/api/v1/catalog/*`; storefront switches from labelled dev data to live data as soon as one product is live (vendor active + store published).

## Phase 03 deliverables
- Vendor application (`/vendor/apply`): business, contact, location, categories, description, logo, banner, unique store slug; Vendor Agreement acceptance recorded (version, timestamp, IP) in `vendor_policy_acceptances`.
- Admin review (`/admin/vendors`): approve / reject / request more info (optionally require a verification document); applicant emailed on every decision.
- Verification documents: private object storage, downloadable only by marketplace_admin / super_admin (audited), soft-deletable by admins.
- Approval creates `vendors` + `vendor_stores` (draft) and grants the `vendor` role on the same user account (no second auth system).
- Vendor dashboard (`/vendor/dashboard`): edit store profile, publish/unpublish. Public store at `/store/:slug` only when published and vendor active.
- Suspension pauses the store, blocks edits/publishing/uploads; reactivation restores publishing. Both emailed and audited.
- Brand red (#D40000) applied to primary buttons, links, focus ring.

## Document retention & deletion policy (D-021)
- Verification documents are kept while the application is under review and while the vendor is active, plus 90 days after rejection or account closure, then deleted.
- Deletion today = admin soft delete (`DELETE /admin/vendor-documents/{id}`), which removes all access immediately. Storage has no hard-delete API; the file stays in private storage unreachable by any endpoint.
- Automated 90-day cleanup job: **not built yet** (scheduled job proposed for Phase 13). Policy text needs founder/legal review.

## Pending / owner action
- Currency: only USD accepted (D-006 assumption); confirm markets/currencies.
- CSV import does not include images; images are uploaded per product.
- Contact form delivery to info@afrovending.com still PENDING (domain DNS/MX).
- Vendor Agreement is a draft; version string `vendor-agreement-draft-2026-10-17` must be bumped when legal text is approved (vendors will re-accept).
