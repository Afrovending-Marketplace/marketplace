# AfroVending — Phase Status

| Phase | Status | Date |
|---|---|---|
| 00 Project foundation | ✅ Complete | 2026-10-17 |
| 01 Public storefront | ✅ Complete | 2026-10-17 |
| 02 Identity & customer accounts | ✅ Complete | 2026-10-17 |
| 03 Vendor onboarding (+ brand red theme) | ✅ Complete | 2026-10-17 |
| 04 Product catalog & inventory | ✅ Complete | 2026-10-19 |
| 05 Search & product discovery (+ weekly low-stock digest) | ✅ Complete | 2026-10-19 |
| 06 Shopping cart & checkout (drafts, no payment) | ✅ Complete | 2026-10-22 |
| 07 Marketplace payments & commission accounting (+ save for later) | ✅ Complete (Stripe TEST mode; vendor accounts SIMULATED) — awaiting owner approval | 2026-10-22 |
| 08–14 | ⏸ Not started | — |

## Phase 07 deliverables
See docs/PAYMENT_ARCHITECTURE.md (approved). One Stripe Checkout payment per multi-vendor order; vendor_orders/order_items created only on verified webhook or server-side Stripe re-check; commission rules (vendor → category → 10% default, versioned, audited); actual Stripe fee allocated by largest remainder; append-only `commission_ledger`; per-vendor-order refunds (proportional tax, commission returned, transfer reversal or owed balance); disputes (holds, vendor evidence, admin attribution, lost → liable vendor only); payout release (7-day hold, idempotent, daily cron `payout-release`); reconciliation report; receipts + vendor notices; cart "Save for later". Live payments blocked by `guard()` unless an admin flag is set (not settable in Phase 07).

Owner actions before go-live: claim the Stripe sandbox and enable Connect (real Express accounts replace simulated ones); tax adviser review (marketplace-facilitator, 1099-K); Vendor Agreement + customer terms updates for fees/refunds/chargebacks/negative balances.

## Phase 06 deliverables
- Cart API `/api/v1/cart` (+ `/items`, `/accept-prices`, `/coupon`, `/shipping`, `/address`, `/merge`): customer carts persist by account; guest carts use an unguessable token (`X-Cart-Token`, stored hashed, 30-day expiry) and merge once into the account cart on sign-in.
- Every read re-validates product/variant status, vendor visibility and stock; flags unavailable / out-of-stock / insufficient stock and price changes (old → new) which must be accepted before checkout.
- `core/pricing.evaluate` computes all money server-side: per-vendor subtotals, shipping (admin options or "rate to be confirmed"), coupon discount (percent/fixed, window, min spend, limit, vendor scope; allocated per vendor), estimated tax only when an admin-entered rate matches the address, estimated total, `final: false`.
- Checkout `POST /api/v1/checkout/start` (sign-in, `Idempotency-Key`): blocks on cart issues, missing address or shipping choice; creates one draft order with an immutable snapshot; repeats with the same key return the same draft; same key + different cart → 409; newer drafts mark older ones abandoned; drafts expire after 24 h. No payment, no stock reservation yet.
- UI: Add to cart on live products, header count, `/cart` grouped by vendor, `/checkout` review (address, per-vendor shipping, totals clearly marked estimated), `/checkout/draft/:id`, admin `/admin/commerce` (shipping options, coupons, tax rates — none pre-filled).

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
