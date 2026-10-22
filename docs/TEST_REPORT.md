# AfroVending — Test Report

## How to run
```
cd backend && pytest tests                     # local (API_BASE_URL defaults to http://localhost:8001)
API_BASE_URL=<preview-url> pytest tests        # against preview
```
Test data rule: any record a test creates must use a `TEST_` prefix and be deleted afterwards. Tests never point at production data.

## Phase 00 — 2026-10-17
| Suite | Scope | Result |
|---|---|---|
| `backend/tests/test_phase00_foundation.py` (11) | Entity registry integrity (all 29 required entities, unique collections, valid relations, unique index names, 8 roles); health, request-id echo, public-only platform settings, schema contract + migration 0001, 404/405 error envelopes | ✅ 11/11 |
| `backend/tests/test_phase00_public_api.py` (8, testing agent) | Same contracts via public preview URL incl. request-id sanitisation | ✅ 8/8 |
| E2E Playwright (testing agent, 47 checks) | Header nav → coming-soon pages with correct phase, header icon notices, hero/vendor CTAs, collection tiles, footer API status + links, design-system sections/modal/form validation, 404, skip link, mobile 390px menu, no horizontal overflow | ✅ 47/47 |

Fixed after testing: React `fetchPriority` warning, mobile menu missing dialog description (a11y), unhandled 500s now keep `X-Request-ID`/CORS headers.

Not covered: frontend unit tests (no Jest/RTL suites yet; e2e covers the shell).

## Phase 01 — 2026-10-17
| Suite | Scope | Result |
|---|---|---|
| Backend regression (19) | Phase 00 suites (phase assertion relaxed to ≥ 0) | ✅ 19/19 |
| E2E Playwright (testing agent, iteration_2) | 13 feature groups: announcement bar, header search/account/cart/sell, 9 category routes, home sections, product/vendor cards, sort, PDP interactions, vendor store, contact & newsletter (UI-only messaging), FAQ, legal drafts, redirects, 404, footer links (16/16), mobile menu, no page overflow on 11 pages at 390px | ✅ 100% |
| Accessibility (axe-core wcag2a/aa/21a/21aa) | 14 desktop pages + mobile home, mobile menu, mobile PDP, search dialog; keyboard skip link | ✅ 0 violations (after fixing clay contrast, search trigger ARIA, select label, step-number contrast) |

Design notes fixed after testing: hero stacks to one column below 1024px; 8 featured products (no orphan slot); shea product image corrected.

## Phase 02 — 2026-10-17
| Suite | Scope | Result |
|---|---|---|
| `backend/tests/test_phase02_identity.py` (13) + `test_phase02_extended.py` (10, testing agent) + Phase 00 suites | Registration, bcrypt hashing, duplicate/weak password, logout revocation, expired token, lockout (incl. XFF spoof bypass), reset & verify tokens single-use, RBAC 403s, address ownership, deactivation, foreign Origin | ✅ 42/42 (after fixing XFF bypass) |
| E2E Playwright (iteration_3) | Register/login/logout/next, recovery pages, profile, password change, addresses CRUD/default, privacy requests, deactivation, /admin & /vendor gating, content pages, 6 policy drafts, Phase 01 regression, 390px overflow | ✅ all flows except contact delivery (DNS) — admin nav link added after run and verified |
| Email delivery | Verification email to `delivered+…@resend.dev` | ✅ delivered (202). Provider burst limit (429) observed during bulk tests — handled gracefully |
| Contact → info@afrovending.com | Real send | ❌ PENDING — provider: "Undeliverable recipient" (afrovending.com MX lookups refused) |

Note: tests require the HTTPS preview URL (Secure cookies).

## Phase 03 — 2026-10-17
| Suite | Scope | Result |
|---|---|---|
| `test_phase03_vendors.py` (3) + `test_phase03_extended.py` (7, testing agent) + all earlier suites | Only approved+active vendors publish; draft/suspended stores not public; suspend/reactivate; policy acceptance required & recorded; request-info + required document; docs hidden from public, owner and other users, admin-only download; vendor isolation (applications, files); slug uniqueness & sync; re-apply after rejection | ✅ 52/52 |
| E2E Playwright (iteration_4) | Apply flow with uploads, unverified gating, admin review dialog, request info → doc upload → approve, vendor dashboard edit/publish, public store, suspend/reactivate, /forbidden gating, brand red | ✅ all flows; fixes applied after: mobile slug row overflow, Approve/Reject colours, toast wording, status badge colours, empty vendor list state, location formatting |

## Phase 07 — 2026-10-22
| Suite | Scope | Result |
|---|---|---|
| `test_phase07_payments.py` (7) + all earlier suites | Multi-vendor payment (real Stripe test PaymentIntent + signed webhook), commission priority vendor>category>default, actual fee allocation sums exactly, duplicate/invalid-signature webhooks, amount mismatch → needs_review, cancel + failed payment, partial refund affecting one vendor, dispute attributed to one vendor (lost → only liable vendor debited), idempotent payout release with simulated account, save for later | ✅ 81/81 |
| E2E Playwright (iteration_8) | Real Stripe hosted checkout with 4242 card, webhook-confirmed paid order, receipts, save for later, vendor earnings + simulated payout account, admin reconciliation/commission/holds/real refund/release/simulated payout, permissions, 390px | ✅ all flows; fixed after: mobile admin tabs, vendor "net" column, commission rate error text, order row links, refund button disabling, stale copy |


## Phase 06 — 2026-10-22
| Suite | Scope | Result |
|---|---|---|
| `test_phase06_cart.py` (5) + all earlier suites | Guest cart token, browser price ignored, stock limits, quantity/remove; mixed-vendor grouping & totals; TBC shipping vs admin flat rate; tax only with admin rate; coupons (invalid, min spend, percent + per-vendor allocation); price change flag/accept; archived product unavailable; insufficient stock; guest merge once; idempotent checkout incl. 4 concurrent identical requests → 1 draft, key reuse with changed cart → 409, older draft abandoned, other users 404 | ✅ 74/74 |
| E2E (iteration_7) | PDP add to cart, guest cart, merge on login, coupons, price change, unavailable item, checkout review, draft page, admin settings, 390px | ✅ all flows; fixes after: cart page sideways scroll on phones, alert spacing, copy, address formatting, coupon row, sticky totals, clearer stock error, item count excludes unavailable lines, tax round-half-up, known shipping shown as "$X + TBC" |


## Phase 05 — 2026-10-19
| Suite | Scope | Result |
|---|---|---|
| `test_phase05_search.py` (7) + `test_phase05_extended.py` (5, testing agent) + all earlier suites | Relevance ranking, partial-word fallback, exclusions (draft/pending/rejected/suspended/unpublished), category+subcategory, price bounds, vendor multi-select, in-stock, sort orders, facets, pagination without duplicates, suggestions, analytics privacy (DNT/GPC, redaction, k=2, TTL, purge permissions), performance with 1,500 products (text index used, < 2 s), vendor preference + cron auth/idempotency/background run | ✅ 69/69 |
| E2E (iteration_6) | Shop/search/category discovery UI, URL restore, back/forward, chips, load more, empty/error, suggestions, admin insights, vendor preference, 390px | ✅; fixes after: analytics double-logging (now explicit `log` flag once per session), stale-response guard, load-more error keeps grid, filter count, dev-data errors & prefix suggestions, price-desc uses max variant price, purge super-admin only, insights error state |


## Phase 04 — 2026-10-19
| Suite | Scope | Result |
|---|---|---|
| `test_phase04_catalog.py` (5) + all earlier suites | Product create/validation (price, category, currency), variants (options, duplicate combos/SKUs), image upload (type check, fake image rejected, WebP ≤1600px served), submit requirements, moderation approve/reject (note required), public catalog visibility, price-only edit stays live, content edit requeues, delete blocked after live, archive locks edits, suspended vendor blocked; stock add/remove/set, negative blocked, system reasons blocked, history before/after; cross-vendor isolation (404), customer/admin gating; CSV preview errors (row+field), commit once, drafts with variants/stock; admin categories create/hide/delete rules | ✅ 57/57 |
| E2E Playwright (iteration_5) | Vendor create → images → variants → inventory → submit; admin approve/reject; storefront /shop, category, PDP variants, /store; requeue on edit; archive/restore/delete; CSV import; categories admin; permissions; 390px layouts | ✅ all flows after fixes: variants save (missing product id), duplicate error toast text, suspended vendor create links hidden, banner text for live data, mobile inventory layout, "From" price on cards, single-variant price sync, optimized image dimensions, CSV reports all row errors, image reorder blocked when archived |
| Test isolation | Test user prefixes per module (TEST_, TEST2_, TEST2X_, TEST4_) and per-worker cleanup so parallel runs don't delete each other's users | ✅ DB clean after run (only owner admin remains) |

