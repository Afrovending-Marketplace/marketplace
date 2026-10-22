# AfroVending — API Contracts

## Conventions
- **Base path:** `/api/v1`. Breaking changes ship as `/api/v2`; v1 contracts are never silently changed. `/api` returns available versions.
- **Format:** JSON, snake_case fields. IDs are strings (`id`). Timestamps ISO-8601 UTC. Money: integer `amount_minor` + `currency`.
- **Single resource:** returned as the object. **Lists:** `{"data": [...], "meta": {"page": 1, "page_size": 20, "total": 0}}` (page_size max 100).
- **Errors (all endpoints):**
  ```json
  {"error": {"code": "validation_error", "message": "Request validation failed.", "details": [{"field": "email", "message": "..."}], "request_id": "..."}}
  ```
  Codes: `bad_request` 400, `unauthorized` 401, `forbidden` 403, `not_found` 404, `method_not_allowed` 405, `conflict` 409, `validation_error` 422, `rate_limited` 429, `internal_error` 500. Raise `APIError(status, code, message, details)` from services.
- **Validation:** Pydantic models on every request body/query; unknown fields ignored on input models unless stated.

## Phase 07 endpoints (under `/api/v1` unless noted)
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/payments/orders/{id}/checkout` | order owner | `{origin_url}` (must be an allowed origin). Re-validates draft, freezes commission plan, creates Stripe Checkout Session (idempotency key `pay:{order}:{attempt}`); reuses an open session |
| GET | `/payments/orders/{id}` | owner | Server-side Stripe re-check when pending; receipt with vendor orders/refunds |
| POST | `/payments/orders/{id}/cancel` | owner | Expires open session; order back to draft |
| GET | `/payments/orders` | customer | Orders & receipts |
| POST | `/api/stripe/webhook` | Stripe signature | Verified, stored once per event id; handles checkout.session.*, refund.*, charge.dispute.*, charge.updated, account.updated, payout.* |
| POST | `/vendor/payments/onboarding` · `/onboarding/simulate-complete` · `/onboarding/refresh` | vendor | Express account link, or SIMULATED account while Connect is off |
| GET | `/vendor/payments/summary` · `/vendor/payments/ledger` | vendor (own only) | Buckets pending/eligible/held/transferred/paid/owed; per-order breakdown |
| POST | `/vendor/payments/disputes/{id}/evidence` | vendor in dispute | |
| GET/PUT | `/admin/payments/config` | read: marketplace/super; write: super | `hold_days` |
| GET/POST/DELETE | `/admin/payments/commission-rules` | write: super_admin | `{scope, target, rate_bps}` versioned; 0–5000 bps |
| GET | `/admin/payments/payments` · `/vendor-orders` · `/refunds` · `/disputes` · `/payouts` · `/ledger` · `/reconciliation` | marketplace/super | |
| POST | `/admin/payments/payments/{id}/sync-fee` | super | Records actual Stripe fee when available |
| POST | `/admin/payments/vendor-orders/{id}/refunds` | super, `Idempotency-Key` | `{lines:[{order_item_id, quantity}], include_shipping, reason}` |
| POST | `/admin/payments/vendor-orders/{id}/holds` · `/holds/{hold}/release` | super | |
| POST | `/admin/payments/disputes/{id}/attribute` | super | `{attributions:[{vendor_order_id, amount_minor, vendor_liable}]}` |
| POST | `/admin/payments/payouts/release` · `/payouts/{id}/simulate-paid` | super | Idempotent release; simulation test-mode only |
| POST | `/cron/payout-release` | cron bearer | Daily |
| POST | `/cart/items/{variant}/save-for-later` · `/cart/saved/{variant}/move-to-cart` · DELETE `/cart/saved/{variant}` | cart owner | |

- **Headers:** `X-Request-ID` (in/out), `X-Content-Type-Options: nosniff`.
- **Auth (from Phase 01):** documented per endpoint as `Auth: public | customer | vendor | admin(<role>)`.
- **Idempotency (from Phase 06/07):** mutating money endpoints require `Idempotency-Key` header.

## Phase 06 endpoints (all under `/api/v1`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/cart` | customer cookie or `X-Cart-Token` | Server-evaluated cart `{groups[], item_count, coupon, totals, blocking[]}` |
| POST | `/cart/items` | any (guest gets `cart_token` once) | `{variant_id, quantity}` — 404 unavailable, 409 out/insufficient stock |
| PATCH / DELETE | `/cart/items/{variant_id}` | cart owner | Set quantity (0 removes) / remove |
| POST | `/cart/accept-prices` | cart owner | Accept current prices |
| PUT / DELETE | `/cart/coupon` | cart owner | Apply `{code}` (422 invalid) / remove |
| PUT | `/cart/shipping` · `/cart/address` | owner · signed in | `{vendor_id, method_id}` · `{address_id}` (own addresses only) |
| POST | `/cart/merge` | signed in + `X-Cart-Token` | One-time guest → account merge |
| POST | `/checkout/start` | signed in + `Idempotency-Key` | Draft order (200 `{order, replayed}`); 409 blocked / key conflict |
| GET | `/checkout/orders/{id}` | order owner | Draft order snapshot |
| GET/POST/PUT | `/admin/commerce/{shipping-methods,coupons,tax-rates}[/{id}]` | marketplace/super admin | Checkout settings |


## Phase 05 endpoints (all under `/api/v1`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/catalog/search?q&category&vendor&min&max&in_stock&sort&page&limit&log` | public | `{data, page, limit, total, has_more, mode: text\|partial\|browse, sort, query, facets}`; 422 bad price, 404 unknown category |
| GET | `/catalog/suggest?q` | public | `{keywords, products, categories, vendors}` (q ≥ 2 chars) |
| GET / DELETE | `/admin/search-analytics?days` | marketplace/super admin · DELETE super admin | Aggregated report with privacy block / purge (audited) |
| PUT | `/vendor/preferences` | vendor | `{low_stock_alerts: instant\|weekly}` |
| POST | `/cron/low-stock-digest` | Bearer `WEBHOOK_CRON_SECRET` | 202 accepted / duplicate; 401 bad auth; 400 bad envelope |


## Phase 04 endpoints (all under `/api/v1`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/catalog/categories` | public | Active category tree with live product counts |
| GET | `/catalog/products?category&vendor&q&sort&page&limit&min_price&max_price` | public | Paginated live products `{data,page,limit,total}` |
| GET | `/catalog/products/{slug}` | public | Live product with variants (in_stock/low_stock, no exact counts) |
| GET | `/catalog/storefront` | public | Snapshot `{categories, products, vendors}` for the storefront shell |
| GET/POST | `/vendor/products` | vendor | List (+counts, low_stock) / create draft (variants optional) |
| GET/PATCH/DELETE | `/vendor/products/{id}` | owner vendor | Detail / edit (requeues live product on content change) / delete (never-live only) |
| PUT | `/vendor/products/{id}/variants` | owner vendor | `{option_names?, variants[]}` upsert; omitted variants deactivated |
| POST/DELETE | `/vendor/products/{id}/images[/{image_id}]` | owner vendor | Multipart upload → WebP main+thumb / delete |
| PUT | `/vendor/products/{id}/images/order` | owner vendor | `{image_ids[]}` |
| POST | `/vendor/products/{id}/submit\|archive\|unarchive` | owner vendor | State transitions |
| POST | `/vendor/inventory/{variant_id}/adjust` | owner vendor | `{mode: delta\|set, quantity, reason, note}` |
| GET | `/vendor/products/{id}/stock-history` | owner vendor | Append-only adjustments |
| GET | `/vendor/products/import/template` | signed in | CSV template |
| POST | `/vendor/products/import/preview` · `/{batch_id}/commit` | vendor | Validate CSV (row errors) · create valid products as drafts (one-time) |
| GET | `/admin/products?status` · `/admin/products/{id}` | marketplace/super admin | Moderation queue / detail |
| POST | `/admin/products/{id}/moderate` | marketplace/super admin | `{decision: approve\|reject\|take_down, note}` (note required unless approve) |
| GET/POST/PATCH/DELETE | `/admin/categories[/{id}]` | marketplace/super admin | Category management (slug immutable; hide blocked with live products; delete only empty) |

Other vendors' product ids return 404. Suspended vendors get 403 `vendor_suspended` on every write.


## Phase 03 endpoints (all under `/api/v1`)
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/files` | user, 30/h | multipart `purpose` = logo (2 MB) / banner (5 MB) / verification_doc (10 MB, PDF allowed); blocked when vendor suspended |
| GET | `/files/{id}` | public | logo/banner only; private docs → 404 |
| GET | `/vendor/policy` | public | current Vendor Agreement version |
| GET/PUT | `/vendor/application` | verified user | own application only; editable in draft / changes_requested; new draft allowed after rejection |
| POST | `/vendor/application/submit` | user | `{accept_policy, policy_version}`; records acceptance |
| GET/PATCH | `/vendor/store` | approved vendor (own store only) | PATCH blocked when suspended; slug unique |
| POST | `/vendor/store/publish` · `/unpublish` | approved vendor | publish requires vendor `active` |
| GET | `/stores`, `/stores/{slug}` | public | published stores of active vendors only |
| GET | `/admin/vendor-applications[/{id}]` | marketplace_admin, super_admin | detail includes documents + policy acceptance |
| POST | `/admin/vendor-applications/{id}/decision` | marketplace_admin, super_admin | `{decision: approve|reject|request_info, note, require_documents}`; emails applicant |
| GET/DELETE | `/admin/vendor-documents/{file_id}` | marketplace_admin, super_admin | download (audited) / soft delete |
| GET | `/admin/vendors` | marketplace_admin, super_admin | |
| POST | `/admin/vendors/{id}/suspend` · `/reactivate` | marketplace_admin, super_admin | `{reason}`; suspend pauses store |

## Phase 02 endpoints (all under `/api/v1`)
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | public, 10/h/IP | `{name,email,password}` → 201 `{user, verification_email_sent}` + cookies |
| POST | `/auth/login` | public, lockout 5/15 min per IP+email, 20 per email | → `{user}` + cookies; 401 `invalid_credentials`, 403 `account_inactive`, 429 |
| POST | `/auth/logout` | cookie | revokes session, clears cookies |
| POST | `/auth/refresh` | refresh cookie | new access cookie |
| GET | `/auth/me` | user | `{user}` |
| POST | `/auth/verify-email` | public | `{token}` single-use, 24 h |
| POST | `/auth/resend-verification` | user, 3/h | |
| POST | `/auth/forgot-password` | public | always generic 200; token 1 h |
| POST | `/auth/reset-password` | public | `{token,password}`; revokes all sessions |
| POST | `/auth/change-password` | user | revokes other sessions |
| GET/PATCH | `/account/profile` | user | `{name, phone}` |
| GET/POST | `/account/addresses` | user (owner-scoped) | max 10; first = default |
| PATCH/DELETE | `/account/addresses/{id}` | owner | 404 for other users' ids |
| POST | `/account/deactivate` | user (non-admin) | `{password, reason}` |
| GET/POST | `/account/privacy-requests` | user | types `data_export`, `data_deletion`, `data_correction` |
| GET | `/admin/users` | any admin | paginated |
| POST | `/admin/staff` | super_admin | strong password required |
| GET/PATCH | `/admin/privacy-requests[/{id}]` | marketplace_admin, super_admin | |
| GET | `/admin/audit-logs` | super_admin | paginated |
| POST | `/contact` | public, 5/h/IP | `{name,email,subject,message}` → emails CONTACT_INBOX; 503 if undeliverable |

User object: `{id, email, name, phone, roles[], status, email_verified, created_at}`. Mutating requests with a foreign `Origin` → 403.

## Phase 01
No new endpoints (storefront uses frontend development data). `health.phase` now reports `1`.

## Implemented endpoints (Phase 00)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api` | public | `{"service","versions":["v1"],"current":"/api/v1"}` |
| GET | `/api/v1/health` | public | `{"status":"ok"|"degraded","database":"ok"|"unavailable","service","version","environment","phase","time"}` |
| GET | `/api/v1/platform` | public | `{"settings": {<key>: <value>}}` — only `platform_settings` with `is_public=true` |
| GET | `/api/v1/system/schema` | public in non-production; **404 when `APP_ENV=production`** | Roles, full entity contract (collections, states, relations, indexes) and applied migrations |
| GET | `/api/docs` | public (non-prod recommended) | OpenAPI UI |
