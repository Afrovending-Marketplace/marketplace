# AfroVending — Master Plan

**Product:** AfroVending Online Marketplace (AfroVending Online Marketplace LLC) · https://www.afrovending.com
**Positioning:** From Culture to Commerce.
**Mission:** Connect African, Caribbean, diaspora and global entrepreneurs with customers through a secure, culturally relevant digital marketplace.

## Delivery model
- One persistent codebase, one shared architecture (see ARCHITECTURE.md). Never regenerated after Phase 00.
- One phase at a time; each phase stops for owner approval.
- No real payments, production deploys or live-data changes without explicit approval.

## Phase roadmap and dependency map

| Phase | Name | Modules | Depends on | Activates entities |
|---|---|---|---|---|
| 00 | Project foundation (shell, design system, schema contracts, API conventions, docs) | A (shell), N (logging/audit base) | — | platform_settings, audit_logs, schema_migrations |
| 01 | Authentication, accounts & roles (RBAC enforced server-side) | B | 00 | users, roles |
| 02 | Vendor onboarding & verification | C | 01 | vendor_applications, vendors, vendor_verifications |
| 03 | Catalog: categories, products, variants, inventory, media (object storage) | E | 02 | categories, products, product_variants, product_images, inventory |
| 04 | Vendor storefronts & vendor product management | D | 02, 03 | vendor_stores |
| 05 | Search, filters & discovery | F | 03, 04 | (text/compound indexes on products) |
| 06 | Multi-vendor cart & checkout (no live charges) | G | 01, 03, 05 | carts, cart_items, orders, order_items, vendor_orders |
| 07 | Payments (Stripe Connect, test mode), commission ledger, payouts | H | 02, 06 | payments, refunds, commission_ledger, payouts |
| 08 | Order management, shipping, tracking & returns | I | 06, 07 | shipping_methods, shipments, returns |
| 09 | Vendor analytics dashboard | J | 06, 07, 08 | (read models/aggregations) |
| 10 | Marketplace administration dashboard | K | 01–08 | (admin views over all entities) |
| 11 | Ratings, reviews, notifications (email via Resend) & support | L | 01, 06, 08 | reviews, notifications, support_tickets |
| 12 | Marketing, SEO, CMS content, coupons, subscriptions & promotions | M, A (CMS) | 03, 06, 07 | coupons (+ content entities defined then) |
| 13 | Security hardening, audit review, backups & monitoring | N | all | (audit_logs coverage, rate limits, alerts) |
| 14 | Launch readiness: performance, accessibility audit, production deploy runbook execution | all | 00–13 | — |

```
00 ─► 01 ─► 02 ─┬─► 03 ─┬─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─┬─► 09
                │       └────────────────────► 06       ├─► 10
                └─────────────────────────────► 07       ├─► 11 ─► 12 ─► 13 ─► 14
```

## Current status
See PHASE_STATUS.md. Phase 00 complete, awaiting approval for Phase 01.
