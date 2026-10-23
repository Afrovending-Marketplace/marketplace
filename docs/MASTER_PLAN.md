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
| 10 | Marketplace administration dashboard | K | 02–08 | (admin views) |
| 11 | Reviews (submission, star ratings, moderation, review notifications — still scheduled here, not built in Phase 09), notifications (email), support | L | 02, 06, 08 | reviews, notifications, support_tickets |
| 12 | Marketing, SEO, CMS content, newsletter, coupons, subscriptions | M, A | 04, 06, 07 | coupons (+ content entities) |
| 13 | Security hardening, audit, backups & monitoring | N | all | — |
| 14 | Launch readiness & production deploy | all | 00–13 | — |

```
00 ─► 01 ─► 02 ─► 03 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─┬─► 09
                                                    ├─► 10
                                                    └─► 11 ─► 12 ─► 13 ─► 14
```

## Phase 01 → later swap points
Storefront pages read through `frontend/src/lib/catalog.js`. Phase 04/05 replace its functions with `/api/v1` calls and delete `frontend/src/data/dev/`.

## Current status
See PHASE_STATUS.md.
