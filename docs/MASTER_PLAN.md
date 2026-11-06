# AfroVending — Master Plan

**Product:** AfroVending Online Marketplace (AfroVending Online Marketplace LLC) · https://www.afrovending.com
**Positioning:** From Culture to Commerce.
**Mission:** Connect African, Caribbean, diaspora and global entrepreneurs with customers through a secure, culturally relevant digital marketplace.

## Delivery model
- One persistent codebase, one shared architecture (see ARCHITECTURE.md). Never regenerated after Phase 00.
- One phase at a time; each phase stops for owner approval.
- No real payments, production deploys or live-data changes without explicit approval.

## Phase roadmap and dependency map
Owner redefined Phase 01 as "Public Storefront" (D-011); later phases shifted accordingly.

| Phase | Name | Modules | Depends on | Activates entities |
|---|---|---|---|---|
| 00 | Project foundation | A (shell), N (base) | — | platform_settings, audit_logs, schema_migrations |
| 01 | Public storefront (templates + labelled development data) | A | 00 | — (frontend only) |
| 02 | Authentication, accounts & roles (server-side RBAC) | B | 00 | users, roles |
| 03 | Vendor onboarding & verification | C | 02 | vendor_applications, vendors, vendor_verifications |
| 04 | Catalog: categories, products, variants, inventory, media; vendor product management | E, D | 03 | categories, products, product_variants, product_images, inventory |
| 05 | Live vendor storefronts + search, filters & discovery | D, F | 04 | vendor_stores (+ search indexes) |
| 06 | Multi-vendor cart & checkout (no live charges) | G | 02, 04, 05 | carts, cart_items, orders, order_items, vendor_orders |
| 07 | Payments (Stripe Connect test mode), commission ledger, payouts | H | 03, 06 | payments, refunds, commission_ledger, payouts |
| 08 | Order management, shipping, tracking & returns | I | 06, 07 | shipping_methods, shipments, returns |
| 09 | Vendor analytics dashboard (control center; review summary card is empty until Phase 11) | J | 06–08 | (aggregations) |
| 10 | Marketplace administration: 5 admin roles with granular server-side permissions, TOTP MFA for admins, CLI bootstrap + in-app invites, basic support tickets, homepage banners/featured, overview, exports, refund two-person approval | K | 02–08 | admin_invites, support_tickets, content_banners, admin_approvals |
| 11 | Customer trust & communication: verified-purchase product reviews (after delivery/collection, one per order item), separate seller ratings (one per vendor suborder), one public vendor response, auto-moderation + abuse reports + admin decisions, order messaging with contact/link/payment masking, in-app notification center, preferences, rate limits (support tickets reused from Phase 10) | L | 02, 06, 08, 10 | reviews, seller_ratings, review_reports, order_messages, notifications |
| 12 | Marketing & monetization: SEO metadata/canonicals/JSON-LD, sitemap/robots, share previews, funded coupons (marketplace vs vendor), campaigns, featured placements, sponsored-listing infra (locked off), subscription framework (billing locked off), wishlists, consented abandoned-cart reminders, analytics + consent + GA4-ready, referral tracking, marketing opt-in/unsubscribe, review photos | M, A | 04, 06, 07, 10, 11 | coupons, coupon_redemptions, campaigns, wishlists, analytics_events, referrals, cart_reminders, sponsored_listings, subscription_requests |
| 13 | Full marketplace QA & security audit (report + Launch Blockers List: docs/PHASE13_AUDIT_REPORT.md; Phase 14 gated on owner approval), wishlist "Price dropped" badge, overselling fix, trusted-proxy rate limits, security headers, preview email allowlist, wishlist daily price-drop/back-in-stock alerts | N | all | wishlist_alerts, wishlist_digests |
| 14 | Legacy migration & launch preparation (docs/PHASE14_MIGRATION_PLAN.md, PRODUCTION_SUPPORT_RUNBOOK.md): idempotent staging importer, activation flow, legacy redirects, backup/restore drill, launch checklist M1–M11; cutover gated on owner approval | all | 00–13 | users.migration, legacy_orders, legacy_redirects, legacy_image_queue, migration_runs, migration_activation_log |

```
00 ─► 01 ─► 02 ─► 03 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─┬─► 09
                                                    ├─► 10
                                                    └─► 11 ─► 12 ─► 13 ─► 14
```

## Phase 01 → later swap points
Storefront pages read through `frontend/src/lib/catalog.js`. Phase 04/05 replace its functions with `/api/v1` calls and delete `frontend/src/data/dev/`.

## Current status
See PHASE_STATUS.md.
