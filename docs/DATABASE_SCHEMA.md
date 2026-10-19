# AfroVending — Database Schema Contract

> GENERATED from `backend/afrovending/schema/entities.py` by `backend/scripts/export_schema_doc.py`. Do not edit by hand.

## Conventions
- Database: MongoDB (`MONGO_URL`, `DB_NAME` from env). Collections are snake_case plural.
- IDs: Mongo `ObjectId` in `_id`, exposed in APIs as string `id` via `BaseDocument` (`PyObjectId`). Foreign keys are stored as ObjectId and named `<entity>_id`.
- Human-facing numbers (e.g. `order_number`) are separate unique fields, never the `_id`.
- Every document has `created_at` / `updated_at` (UTC BSON datetime).
- Money: integer minor units (`amount_minor`) + ISO-4217 `currency`. Never floats.
- Lifecycle: the state lives in `status` unless noted; transitions are enforced server-side and audited.
- Append-only collections are never updated or deleted; corrections are new entries.
- Soft delete: business records use a terminal state (`archived`, `closed`, `deactivated`) instead of deletion.
- Indexes are created only for entities whose phase is active, via versioned migrations (`schema_migrations`).
- Multi-document writes that touch money or stock (checkout, refunds, payouts) use Mongo transactions (replica set required in production).

## Roles
| Role | Scope |
|---|---|
| `guest` | Unauthenticated visitor. Read-only access to public storefront content. |
| `customer` | Registered shopper. Owns their profile, carts, orders, returns, reviews and tickets. |
| `vendor_applicant` | Customer who submitted a vendor application. Owns only their application. |
| `vendor` | Approved vendor owner. Owns their vendor, store, products, inventory and vendor orders. |
| `vendor_team_member` | Future: delegated access to one vendor, scoped by vendor-granted permissions. |
| `support_admin` | Reads customer/order data to resolve tickets. Cannot change financial records. |
| `marketplace_admin` | Approves vendors, moderates catalog and reviews, manages categories and orders. |
| `super_admin` | Full platform control incl. settings, admin accounts, payouts and refunds. |

## Entity summary
| Entity | Collection | Phase | Module | Owner |
|---|---|---|---|---|
| PlatformSettings | `platform_settings` | 00 | K | system (super_admin writes) |
| AuditLogs | `audit_logs` | 00 | N | system (admins read) |
| SchemaMigrations | `schema_migrations` | 00 | N | system |
| Users | `users` | 02 | B | self (user_id = _id) |
| Roles | `roles` | 02 | B | system (super_admin writes) |
| Addresses | `addresses` | 02 | B | user_id |
| Sessions | `sessions` | 02 | B | user_id |
| AuthTokens | `auth_tokens` | 02 | B | user_id |
| RateLimits | `rate_limits` | 02 | N | system |
| PrivacyRequests | `privacy_requests` | 02 | B | user_id; marketplace_admin/super_admin resolve |
| ContactMessages | `contact_messages` | 02 | L | system |
| VendorApplications | `vendor_applications` | 03 | C | applicant user_id; admins review |
| Vendors | `vendors` | 03 | C | owner_user_id; admins manage status |
| VendorVerification | `vendor_verifications` | 03 | C | vendor_id (read); admins write |
| Categories | `categories` | 04 | E | system (marketplace_admin writes) |
| Products | `products` | 04 | E | vendor_id |
| ProductVariants | `product_variants` | 04 | E | vendor_id (via product) |
| ProductImages | `product_images` | 04 | E | vendor_id (via product) |
| Inventory | `inventory` | 04 | E | vendor_id |
| SearchQueries | `search_queries` | 05 | E | system (admin aggregate read) |
| CronRuns | `cron_runs` | 05 | E | system |
| StockAdjustments | `stock_adjustments` | 04 | E | vendor_id (read own); system writes |
| ProductImports | `product_imports` | 04 | E | vendor_id |
| VendorStores | `vendor_stores` | 03 | D | vendor_id |
| Files | `files` | 03 | N | owner_user_id; private docs readable by marketplace_admin/super_admin only |
| VendorPolicyAcceptances | `vendor_policy_acceptances` | 03 | C | user_id |
| Carts | `carts` | 06 | G | user_id or guest_token |
| CartItems | `cart_items` | 06 | G | cart owner |
| Orders | `orders` | 06 | G | customer_id |
| VendorOrders | `vendor_orders` | 06 | I | vendor_id (fulfils); customer_id (reads) |
| OrderItems | `order_items` | 06 | G | customer_id; vendor_id |
| Payments | `payments` | 07 | H | system; customer reads own |
| Refunds | `refunds` | 07 | H | admins write; customer reads own |
| CommissionLedger | `commission_ledger` | 07 | H | system; vendor reads own |
| Payouts | `payouts` | 07 | H | vendor reads own; super_admin approves |
| ShippingMethods | `shipping_methods` | 08 | I | vendor_id (null = platform-wide) |
| Shipments | `shipments` | 08 | I | vendor_id; customer reads own |
| Returns | `returns` | 08 | I | customer_id requests; vendor_id/admins resolve |
| Reviews | `reviews` | 11 | L | customer_id; admins moderate |
| Notifications | `notifications` | 11 | L | user_id |
| SupportTickets | `support_tickets` | 11 | L | requester_id; support_admin handles |
| Coupons | `coupons` | 12 | M | vendor_id (null = platform coupon) |

## PlatformSettings (`platform_settings`) — Phase 00

Key/value platform configuration. Public keys are exposed via /api/v1/platform.

- **Owner:** system (super_admin writes)
- **Index** `key_1` (unique)
- **Index** `is_public_1`

## AuditLogs (`audit_logs`) — Phase 00

Append-only record of privileged and state-changing actions.

- **Owner:** system (admins read)
- **Append-only:** yes
- **Relations:** `actor_id -> users`
- **Index** `created_at_-1`
- **Index** `actor_id_1_created_at_-1`
- **Index** `entity_type_1_entity_id_1_created_at_-1`

## SchemaMigrations (`schema_migrations`) — Phase 00

Applied versioned migrations.

- **Owner:** system
- **Append-only:** yes
- **Index** `version_1` (unique)

## Users (`users`) — Phase 02

Single identity table for customers, vendors and admins. Roles are an array.

- **Owner:** self (user_id = _id)
- **States (`status`):** `pending_verification` → `active` → `suspended` → `deactivated`
- **Index** `email_1` (unique)
- **Index** `roles_1`
- **Index** `status_1_created_at_-1`

## Roles (`roles`) — Phase 02

Role catalog with permission sets; keys match afrovending.core.roles.Role.

- **Owner:** system (super_admin writes)
- **Index** `key_1` (unique)

## Addresses (`addresses`) — Phase 02

Customer address book (max 10, one default).

- **Owner:** user_id
- **Relations:** `user_id -> users`
- **Index** `user_id_1_is_default_-1_created_at_1`

## Sessions (`sessions`) — Phase 02

Server-side login sessions referenced by JWT `sid`; revocable.

- **Owner:** user_id
- **States (`status`):** `active` → `revoked`
- **Relations:** `user_id -> users`
- **Index** `user_id_1_status_1`
- **Index** `expires_at_1` expireAfterSeconds=0

## AuthTokens (`auth_tokens`) — Phase 02

Single-use hashed tokens for email verification and password reset.

- **Owner:** user_id
- **Relations:** `user_id -> users`
- **Index** `token_hash_1` (unique)
- **Index** `user_id_1_purpose_1`
- **Index** `expires_at_1` expireAfterSeconds=0

## RateLimits (`rate_limits`) — Phase 02

Fixed-window counters for login, registration, recovery and contact limits.

- **Owner:** system
- **Index** `key_1` (unique)
- **Index** `expires_at_1` expireAfterSeconds=0

## PrivacyRequests (`privacy_requests`) — Phase 02

Data export / deletion / correction requests.

- **Owner:** user_id; marketplace_admin/super_admin resolve
- **States (`status`):** `submitted` → `in_review` → `completed` → `rejected`
- **Relations:** `user_id -> users`
- **Index** `user_id_1_created_at_-1`
- **Index** `status_1_created_at_-1`

## ContactMessages (`contact_messages`) — Phase 02

Log of contact form submissions and delivery result.

- **Owner:** system
- **States (`status`):** `sent` → `failed`
- **Index** `created_at_-1`

## VendorApplications (`vendor_applications`) — Phase 03

Business details submitted by a vendor applicant.

- **Owner:** applicant user_id; admins review
- **States (`status`):** `draft` → `submitted` → `under_review` → `changes_requested` → `approved` → `rejected` → `withdrawn`
- **Relations:** `user_id -> users`, `reviewed_by -> users`
- **Index** `user_id_1_created_at_-1`
- **Index** `status_1_submitted_at_-1`

## Vendors (`vendors`) — Phase 03

Approved business entity on the marketplace.

- **Owner:** owner_user_id; admins manage status
- **States (`status`):** `pending` → `active` → `suspended` → `closed`
- **Relations:** `owner_user_id -> users`, `application_id -> vendor_applications`
- **Index** `owner_user_id_1` (unique)
- **Index** `slug_1` (unique)
- **Index** `status_1`

## VendorVerification (`vendor_verifications`) — Phase 03

Identity / business / payout-eligibility checks per vendor.

- **Owner:** vendor_id (read); admins write
- **States (`status`):** `not_started` → `pending` → `verified` → `failed` → `expired`
- **Relations:** `vendor_id -> vendors`
- **Index** `vendor_id_1_check_type_1` (unique)
- **Index** `status_1`

## Categories (`categories`) — Phase 04

Two-level catalog taxonomy (parent_id). Slug is immutable; hide instead of delete when in use.

- **Owner:** system (marketplace_admin writes)
- **States (`status`):** `active` → `hidden`
- **Relations:** `parent_id -> categories`
- **Index** `slug_1` (unique)
- **Index** `parent_id_1_sort_order_1`
- **Index** `status_1`

## Products (`products`) — Phase 04

Sellable listing owned by one vendor. Public only when active + vendor active + store published. Content edits to an active product return it to pending_review; products that were ever active can only be archived.

- **Owner:** vendor_id
- **States (`status`):** `draft` → `pending_review` → `active` → `rejected` → `archived`
- **Relations:** `vendor_id -> vendors`, `owner_user_id -> users`, `category_id -> categories`
- **Index** `slug_1` (unique)
- **Index** `vendor_id_1_status_1`
- **Index** `vendor_id_1_sku_1` (unique)
- **Index** `category_id_1_status_1`
- **Index** `category_slug_1_status_1`
- **Index** `status_1_submitted_at_1`
- **Index** `status_1_price_min_minor_1`
- **Index** `status_1_in_stock_1`
- **Index** `tags_1`
- **Index** `title_text_tags_text_description_text` weights={'title': 10, 'tags': 5, 'description': 1}, default_language=english

## ProductVariants (`product_variants`) — Phase 04

Purchasable SKU (size/colour/etc.) with price in minor units.

- **Owner:** vendor_id (via product)
- **States (`status`):** `active` → `inactive`
- **Relations:** `product_id -> products`, `vendor_id -> vendors`
- **Index** `sku_1` (unique)
- **Index** `product_id_1`

## ProductImages (`product_images`) — Phase 04

Object-storage references for product media.

- **Owner:** vendor_id (via product)
- **Relations:** `product_id -> products`, `variant_id -> product_variants`
- **Index** `product_id_1_sort_order_1`

## Inventory (`inventory`) — Phase 04

Stock per variant: quantity_on_hand, quantity_reserved.

- **Owner:** vendor_id
- **Relations:** `variant_id -> product_variants`, `vendor_id -> vendors`
- **Index** `variant_id_1` (unique)
- **Index** `vendor_id_1`
- **Index** `product_id_1`

## SearchQueries (`search_queries`) — Phase 05

Anonymous search log: normalized query, result_count, filter names, day. No user/session/IP. TTL 180 days.

- **Owner:** system (admin aggregate read)
- **Append-only:** yes
- **Index** `created_at_1`
- **Index** `query_1_created_at_1`
- **Index** `expires_at_1` expireAfterSeconds=0

## CronRuns (`cron_runs`) — Phase 05

Scheduled job deliveries (idempotency by run_id). TTL 30 days.

- **Owner:** system
- **States (`status`):** `queued` → `done` → `failed`
- **Index** `run_id_1` (unique)
- **Index** `expires_at_1` expireAfterSeconds=0

## StockAdjustments (`stock_adjustments`) — Phase 04

Append-only stock movement log: delta, before, after, reason, actor.

- **Owner:** vendor_id (read own); system writes
- **Append-only:** yes
- **Relations:** `variant_id -> product_variants`, `product_id -> products`, `vendor_id -> vendors`, `actor_id -> users`
- **Index** `product_id_1_created_at_-1`
- **Index** `variant_id_1_created_at_-1`
- **Index** `vendor_id_1_created_at_-1`

## ProductImports (`product_imports`) — Phase 04

CSV import batch: validated preview, row errors, commit result. Expires after 24h.

- **Owner:** vendor_id
- **States (`status`):** `previewed` → `committing` → `committed`
- **Relations:** `vendor_id -> vendors`, `user_id -> users`
- **Index** `vendor_id_1_created_at_-1`
- **Index** `expires_at_1` expireAfterSeconds=0

## VendorStores (`vendor_stores`) — Phase 03

Public storefront profile (branding, policies) for a vendor.

- **Owner:** vendor_id
- **States (`status`):** `draft` → `published` → `paused`
- **Relations:** `vendor_id -> vendors`
- **Index** `vendor_id_1` (unique)
- **Index** `slug_1` (unique)
- **Index** `status_1`
- **Index** `owner_user_id_1`

## Files (`files`) — Phase 03

Object-storage references. Public: logo/banner. Private: verification_doc (soft delete only).

- **Owner:** owner_user_id; private docs readable by marketplace_admin/super_admin only
- **Relations:** `owner_user_id -> users`, `application_id -> vendor_applications`
- **Index** `owner_user_id_1_purpose_1`
- **Index** `application_id_1`

## VendorPolicyAcceptances (`vendor_policy_acceptances`) — Phase 03

Append-only record of Vendor Agreement version accepted, with timestamp and IP.

- **Owner:** user_id
- **Append-only:** yes
- **Relations:** `user_id -> users`, `application_id -> vendor_applications`
- **Index** `user_id_1_accepted_at_-1`
- **Index** `application_id_1`

## Carts (`carts`) — Phase 06

One active cart per customer or guest session; spans multiple vendors.

- **Owner:** user_id or guest_token
- **States (`status`):** `active` → `converted` → `abandoned` → `expired`
- **Relations:** `user_id -> users`
- **Index** `user_id_1_status_1`
- **Index** `guest_token_1`
- **Index** `expires_at_1` expireAfterSeconds=0

## CartItems (`cart_items`) — Phase 06

Line in a cart; price is re-validated at checkout.

- **Owner:** cart owner
- **Relations:** `cart_id -> carts`, `variant_id -> product_variants`, `vendor_id -> vendors`
- **Index** `cart_id_1_variant_id_1` (unique)

## Orders (`orders`) — Phase 06

Customer-facing order; split into VendorOrders per vendor.

- **Owner:** customer_id
- **States (`status`):** `pending_payment` → `paid` → `partially_fulfilled` → `fulfilled` → `completed` → `cancelled` → `partially_refunded` → `refunded`
- **Relations:** `customer_id -> users`
- **Index** `order_number_1` (unique)
- **Index** `customer_id_1_created_at_-1`
- **Index** `status_1_created_at_-1`

## VendorOrders (`vendor_orders`) — Phase 06

The slice of an order a single vendor must fulfil.

- **Owner:** vendor_id (fulfils); customer_id (reads)
- **States (`status`):** `pending` → `accepted` → `processing` → `shipped` → `delivered` → `cancelled` → `returned`
- **Relations:** `order_id -> orders`, `vendor_id -> vendors`
- **Index** `order_id_1`
- **Index** `vendor_id_1_status_1_created_at_-1`

## OrderItems (`order_items`) — Phase 06

Immutable price/qty snapshot of a purchased variant.

- **Owner:** customer_id; vendor_id
- **Relations:** `order_id -> orders`, `vendor_order_id -> vendor_orders`, `variant_id -> product_variants`
- **Index** `order_id_1`
- **Index** `vendor_order_id_1`
- **Index** `vendor_id_1_created_at_-1`

## Payments (`payments`) — Phase 07

Provider payment record (Stripe Connect). Idempotency enforced.

- **Owner:** system; customer reads own
- **States (`status`):** `requires_payment` → `processing` → `succeeded` → `failed` → `cancelled` → `refunded`
- **Relations:** `order_id -> orders`
- **Index** `order_id_1`
- **Index** `idempotency_key_1` (unique)
- **Index** `provider_payment_id_1` (unique) sparse=True

## Refunds (`refunds`) — Phase 07

Full or partial refund against a payment.

- **Owner:** admins write; customer reads own
- **States (`status`):** `requested` → `approved` → `processing` → `succeeded` → `failed` → `rejected`
- **Relations:** `payment_id -> payments`, `order_id -> orders`, `return_id -> returns`
- **Index** `payment_id_1`
- **Index** `order_id_1`
- **Index** `status_1_created_at_-1`

## CommissionLedger (`commission_ledger`) — Phase 07

Append-only double-entry style ledger of sales, commission, refunds, payouts (minor units).

- **Owner:** system; vendor reads own
- **Append-only:** yes
- **Relations:** `vendor_id -> vendors`, `vendor_order_id -> vendor_orders`, `payout_id -> payouts`
- **Index** `vendor_id_1_created_at_-1`
- **Index** `source_type_1_source_id_1_entry_type_1` (unique)

## Payouts (`payouts`) — Phase 07

Transfer of vendor balance to connected account.

- **Owner:** vendor reads own; super_admin approves
- **States (`status`):** `scheduled` → `processing` → `paid` → `failed` → `cancelled`
- **Relations:** `vendor_id -> vendors`
- **Index** `vendor_id_1_created_at_-1`
- **Index** `status_1`

## ShippingMethods (`shipping_methods`) — Phase 08

Rate rules a vendor offers.

- **Owner:** vendor_id (null = platform-wide)
- **States (`status`):** `active` → `inactive`
- **Relations:** `vendor_id -> vendors`
- **Index** `vendor_id_1_status_1`

## Shipments (`shipments`) — Phase 08

Carrier tracking for a vendor order.

- **Owner:** vendor_id; customer reads own
- **States (`status`):** `label_created` → `in_transit` → `out_for_delivery` → `delivered` → `exception` → `returned`
- **Relations:** `vendor_order_id -> vendor_orders`
- **Index** `vendor_order_id_1`
- **Index** `tracking_number_1`

## Returns (`returns`) — Phase 08

Return/RMA for one or more order items.

- **Owner:** customer_id requests; vendor_id/admins resolve
- **States (`status`):** `requested` → `approved` → `rejected` → `in_transit` → `received` → `refunded` → `closed`
- **Relations:** `order_item_id -> order_items`, `customer_id -> users`, `vendor_id -> vendors`
- **Index** `customer_id_1_created_at_-1`
- **Index** `vendor_id_1_status_1`

## Reviews (`reviews`) — Phase 11

One review per purchased order item.

- **Owner:** customer_id; admins moderate
- **States (`status`):** `pending` → `published` → `hidden` → `rejected`
- **Relations:** `product_id -> products`, `customer_id -> users`, `order_item_id -> order_items`
- **Index** `order_item_id_1` (unique)
- **Index** `product_id_1_status_1_created_at_-1`

## Notifications (`notifications`) — Phase 11

In-app/email notification for one user.

- **Owner:** user_id
- **States (`status`):** `unread` → `read` → `archived`
- **Relations:** `user_id -> users`
- **Index** `user_id_1_status_1_created_at_-1`

## SupportTickets (`support_tickets`) — Phase 11

Customer or vendor help request.

- **Owner:** requester_id; support_admin handles
- **States (`status`):** `open` → `pending_customer` → `pending_internal` → `resolved` → `closed`
- **Relations:** `requester_id -> users`, `order_id -> orders`, `assignee_id -> users`
- **Index** `requester_id_1_created_at_-1`
- **Index** `status_1_updated_at_-1`

## Coupons (`coupons`) — Phase 12

Discount codes with usage limits.

- **Owner:** vendor_id (null = platform coupon)
- **States (`status`):** `draft` → `active` → `paused` → `expired`
- **Relations:** `vendor_id -> vendors`
- **Index** `code_1` (unique)
- **Index** `vendor_id_1_status_1`
