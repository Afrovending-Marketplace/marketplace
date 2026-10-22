"""Central registry of every marketplace entity: collection, phase, ownership, lifecycle, relations, indexes."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Index:
    keys: tuple
    unique: bool = False
    options: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return "_".join(f"{k}_{v}" for k, v in self.keys)


def I(*fields: str, unique: bool = False, **options) -> Index:
    """`-field` = descending, `field:text` = text index."""
    keys = []
    for f in fields:
        if f.endswith(":text"):
            keys.append((f[:-5], "text"))
        elif f.startswith("-"):
            keys.append((f[1:], -1))
        else:
            keys.append((f, 1))
    return Index(tuple(keys), unique, options)


@dataclass(frozen=True)
class Entity:
    name: str
    collection: str
    phase: int
    module: str
    owner: str
    description: str
    states: tuple = ()
    relations: tuple = ()
    indexes: tuple = ()
    append_only: bool = False
    state_field: Optional[str] = "status"


ENTITIES: tuple = (
    Entity("PlatformSettings", "platform_settings", 0, "K", "system (super_admin writes)",
           "Key/value platform configuration. Public keys are exposed via /api/v1/platform.",
           indexes=(I("key", unique=True), I("is_public")), state_field=None),
    Entity("AuditLogs", "audit_logs", 0, "N", "system (admins read)",
           "Append-only record of privileged and state-changing actions.",
           relations=("actor_id -> users",),
           indexes=(I("-created_at"), I("actor_id", "-created_at"), I("entity_type", "entity_id", "-created_at")),
           append_only=True, state_field=None),
    Entity("SchemaMigrations", "schema_migrations", 0, "N", "system",
           "Applied versioned migrations.", indexes=(I("version", unique=True),), append_only=True, state_field=None),

    Entity("Users", "users", 2, "B", "self (user_id = _id)",
           "Single identity table for customers, vendors and admins. Roles are an array.",
           states=("pending_verification", "active", "suspended", "deactivated"),
           indexes=(I("email", unique=True), I("roles"), I("status", "-created_at"))),
    Entity("Roles", "roles", 2, "B", "system (super_admin writes)",
           "Role catalog with permission sets; keys match afrovending.core.roles.Role.",
           indexes=(I("key", unique=True),), state_field=None),
    Entity("Addresses", "addresses", 2, "B", "user_id",
           "Customer address book (max 10, one default).", relations=("user_id -> users",),
           indexes=(I("user_id", "-is_default", "created_at"),), state_field=None),
    Entity("Sessions", "sessions", 2, "B", "user_id",
           "Server-side login sessions referenced by JWT `sid`; revocable.", states=("active", "revoked"),
           relations=("user_id -> users",), indexes=(I("user_id", "status"), I("expires_at", expireAfterSeconds=0))),
    Entity("AuthTokens", "auth_tokens", 2, "B", "user_id",
           "Single-use hashed tokens for email verification and password reset.", relations=("user_id -> users",),
           indexes=(I("token_hash", unique=True), I("user_id", "purpose"), I("expires_at", expireAfterSeconds=0)),
           state_field=None),
    Entity("RateLimits", "rate_limits", 2, "N", "system",
           "Fixed-window counters for login, registration, recovery and contact limits.",
           indexes=(I("key", unique=True), I("expires_at", expireAfterSeconds=0)), state_field=None),
    Entity("PrivacyRequests", "privacy_requests", 2, "B", "user_id; marketplace_admin/super_admin resolve",
           "Data export / deletion / correction requests.", states=("submitted", "in_review", "completed", "rejected"),
           relations=("user_id -> users",), indexes=(I("user_id", "-created_at"), I("status", "-created_at"))),
    Entity("ContactMessages", "contact_messages", 2, "L", "system",
           "Log of contact form submissions and delivery result.", states=("sent", "failed"),
           indexes=(I("-created_at"),)),

    Entity("VendorApplications", "vendor_applications", 3, "C", "applicant user_id; admins review",
           "Business details submitted by a vendor applicant.",
           states=("draft", "submitted", "under_review", "changes_requested", "approved", "rejected", "withdrawn"),
           relations=("user_id -> users", "reviewed_by -> users"),
           indexes=(I("user_id", "-created_at"), I("status", "-submitted_at"))),
    Entity("Vendors", "vendors", 3, "C", "owner_user_id; admins manage status",
           "Approved business entity on the marketplace.",
           states=("pending", "active", "suspended", "closed"),
           relations=("owner_user_id -> users", "application_id -> vendor_applications"),
           indexes=(I("owner_user_id", unique=True), I("slug", unique=True), I("status"))),
    Entity("VendorVerification", "vendor_verifications", 3, "C", "vendor_id (read); admins write",
           "Identity / business / payout-eligibility checks per vendor.",
           states=("not_started", "pending", "verified", "failed", "expired"),
           relations=("vendor_id -> vendors",),
           indexes=(I("vendor_id", "check_type", unique=True), I("status"))),

    Entity("Categories", "categories", 4, "E", "system (marketplace_admin writes)",
           "Two-level catalog taxonomy (parent_id). Slug is immutable; hide instead of delete when in use.",
           states=("active", "hidden"), relations=("parent_id -> categories",),
           indexes=(I("slug", unique=True), I("parent_id", "sort_order"), I("status"))),
    Entity("Products", "products", 4, "E", "vendor_id",
           "Sellable listing owned by one vendor. Public only when active + vendor active + store published. "
           "Content edits to an active product return it to pending_review; products that were ever active can only be archived.",
           states=("draft", "pending_review", "active", "rejected", "archived"),
           relations=("vendor_id -> vendors", "owner_user_id -> users", "category_id -> categories"),
           indexes=(I("slug", unique=True), I("vendor_id", "status"), I("vendor_id", "sku", unique=True), I("category_id", "status"),
                    I("category_slug", "status"), I("status", "submitted_at"), I("status", "price_min_minor"),
                    I("status", "in_stock"), I("tags"),
                    I("title:text", "tags:text", "description:text", weights={"title": 10, "tags": 5, "description": 1},
                      default_language="english"))),
    Entity("ProductVariants", "product_variants", 4, "E", "vendor_id (via product)",
           "Purchasable SKU (size/colour/etc.) with price in minor units.",
           states=("active", "inactive"), relations=("product_id -> products", "vendor_id -> vendors"),
           indexes=(I("sku", unique=True), I("product_id"))),
    Entity("ProductImages", "product_images", 4, "E", "vendor_id (via product)",
           "Object-storage references for product media.",
           relations=("product_id -> products", "variant_id -> product_variants"),
           indexes=(I("product_id", "sort_order"),), state_field=None),
    Entity("Inventory", "inventory", 4, "E", "vendor_id",
           "Stock per variant: quantity_on_hand, quantity_reserved.",
           relations=("variant_id -> product_variants", "vendor_id -> vendors"),
           indexes=(I("variant_id", unique=True), I("vendor_id"), I("product_id")), state_field=None),
    Entity("SearchQueries", "search_queries", 5, "E", "system (admin aggregate read)",
           "Anonymous search log: normalized query, result_count, filter names, day. No user/session/IP. TTL 180 days.",
           indexes=(I("created_at"), I("query", "created_at"), I("expires_at", expireAfterSeconds=0)), append_only=True, state_field=None),
    Entity("CronRuns", "cron_runs", 5, "E", "system",
           "Scheduled job deliveries (idempotency by run_id). TTL 30 days.",
           states=("queued", "done", "failed"), indexes=(I("run_id", unique=True), I("expires_at", expireAfterSeconds=0))),
    Entity("StockAdjustments", "stock_adjustments", 4, "E", "vendor_id (read own); system writes",
           "Append-only stock movement log: delta, before, after, reason, actor.",
           relations=("variant_id -> product_variants", "product_id -> products", "vendor_id -> vendors", "actor_id -> users"),
           indexes=(I("product_id", "-created_at"), I("variant_id", "-created_at"), I("vendor_id", "-created_at")),
           append_only=True, state_field=None),
    Entity("ProductImports", "product_imports", 4, "E", "vendor_id",
           "CSV import batch: validated preview, row errors, commit result. Expires after 24h.",
           states=("previewed", "committing", "committed"), relations=("vendor_id -> vendors", "user_id -> users"),
           indexes=(I("vendor_id", "-created_at"), I("expires_at", expireAfterSeconds=0))),

    Entity("VendorStores", "vendor_stores", 3, "D", "vendor_id",
           "Public storefront profile (branding, policies) for a vendor.",
           states=("draft", "published", "paused"), relations=("vendor_id -> vendors",),
           indexes=(I("vendor_id", unique=True), I("slug", unique=True), I("status"), I("owner_user_id"))),
    Entity("Files", "files", 3, "N", "owner_user_id; private docs readable by marketplace_admin/super_admin only",
           "Object-storage references. Public: logo/banner. Private: verification_doc (soft delete only).",
           relations=("owner_user_id -> users", "application_id -> vendor_applications"),
           indexes=(I("owner_user_id", "purpose"), I("application_id")), state_field=None),
    Entity("VendorPolicyAcceptances", "vendor_policy_acceptances", 3, "C", "user_id",
           "Append-only record of Vendor Agreement version accepted, with timestamp and IP.",
           relations=("user_id -> users", "application_id -> vendor_applications"),
           indexes=(I("user_id", "-accepted_at"), I("application_id")), append_only=True, state_field=None),

    Entity("Carts", "carts", 6, "G", "user_id or guest token (sha256 stored)",
           "One active cart per customer or guest; spans vendors. Items embedded: {variant_id, product_id, vendor_id, quantity, added_price_minor}. "
           "Guest carts expire after 30 days; merged into the customer cart on sign-in.",
           states=("active", "merged", "converted", "abandoned"), relations=("user_id -> users",),
           indexes=(I("user_id", "status"), I("token_hash", sparse=True), I("expires_at", expireAfterSeconds=0))),
    Entity("Orders", "orders", 6, "G", "customer_id",
           "Customer-facing order. Phase 06 creates idempotent drafts with an immutable server-priced snapshot (vendor_groups, totals, "
           "amounts_final=false); payment (Phase 07) moves it to pending_payment/paid and creates VendorOrders/OrderItems.",
           states=("draft", "abandoned", "expired", "pending_payment", "paid", "partially_fulfilled", "fulfilled", "completed",
                   "cancelled", "partially_refunded", "refunded"),
           relations=("customer_id -> users", "cart_id -> carts"),
           indexes=(I("order_number", unique=True), I("customer_id", "-created_at"), I("status", "-created_at"),
                    I("customer_id", "idempotency_key", unique=True))),
    Entity("TaxRates", "tax_rates", 6, "G", "marketplace admin",
           "Admin-entered estimated tax rates by country/region (basis points). None are seeded: without a rate, tax shows as not calculated.",
           states=("active", "inactive"), indexes=(I("country", "region", unique=True),)),
    Entity("VendorOrders", "vendor_orders", 7, "I", "vendor_id (fulfils); customer_id (reads)",
           "The slice of a paid order a single vendor must fulfil, with its money breakdown (items, shipping, tax, commission, fee share, refunds) "
           "and earning_status pending → eligible (after hold days) → transferred → paid; holds block release.",
           states=("pending", "accepted", "processing", "shipped", "delivered", "cancelled", "returned"),
           relations=("order_id -> orders", "vendor_id -> vendors", "payment_id -> payments"),
           indexes=(I("order_id", "vendor_id", unique=True), I("vendor_id", "status", "-created_at"), I("payment_id"), I("vendor_id", "earning_status"))),
    Entity("OrderItems", "order_items", 7, "G", "customer_id; vendor_id",
           "Immutable price/qty snapshot of a purchased variant, with the commission rate, source and amount applied at payment.",
           relations=("order_id -> orders", "vendor_order_id -> vendor_orders", "variant_id -> product_variants"),
           indexes=(I("order_id"), I("vendor_order_id", "variant_id", unique=True), I("vendor_id", "-created_at")), state_field=None),

    Entity("Payments", "payments", 7, "H", "system; customer reads own",
           "One Stripe payment (Checkout Session → PaymentIntent) for a whole multi-vendor order, with the frozen per-vendor plan and actual Stripe fee.",
           states=("requires_payment", "processing", "succeeded", "failed", "cancelled", "needs_review"),
           relations=("order_id -> orders",),
           indexes=(I("order_id"), I("idempotency_key", unique=True), I("provider_session_id", unique=True, sparse=True),
                    I("provider_payment_id", unique=True, sparse=True))),
    Entity("Refunds", "refunds", 7, "H", "admins write; customer reads own",
           "Full or partial refund of one vendor order (items, shipping, proportional tax, commission returned).",
           states=("processing", "pending", "succeeded", "failed"),
           relations=("payment_id -> payments", "order_id -> orders", "vendor_order_id -> vendor_orders"),
           indexes=(I("payment_id"), I("order_id"), I("status", "-created_at"), I("idempotency_key", unique=True),
                    I("provider_refund_id", unique=True, sparse=True))),
    Entity("CommissionLedger", "commission_ledger", 7, "H", "system; vendor reads own",
           "Append-only ledger (accounts vendor/platform/tax; types gross_sale, shipping, tax_collected, commission, processing_fee_allocation, refund, "
           "commission_reversal, transfer, transfer_reversal, dispute_*, liability_recovery). Unique entry_key makes every write idempotent.",
           relations=("vendor_id -> vendors", "vendor_order_id -> vendor_orders", "payment_id -> payments"),
           indexes=(I("entry_key", unique=True), I("vendor_id", "account", "-created_at"), I("payment_id"), I("account", "type")),
           append_only=True, state_field=None),
    Entity("Payouts", "payouts", 7, "H", "vendor reads own; super_admin releases",
           "Stripe transfer of one vendor order's net earnings to the vendor's connected account (transferred), then bank payout (paid).",
           states=("transferred", "paid", "failed"),
           relations=("vendor_id -> vendors", "vendor_order_id -> vendor_orders"),
           indexes=(I("vendor_id", "-created_at"), I("status"), I("idempotency_key", unique=True), I("destination", "status"))),
    Entity("ConnectedAccounts", "connected_accounts", 7, "H", "vendor_id",
           "Vendor's Stripe Connect Express account (or SIMULATED sandbox account while Connect is not enabled).", state_field=None,
           relations=("vendor_id -> vendors",), indexes=(I("vendor_id", unique=True), I("stripe_account_id", unique=True))),
    Entity("Disputes", "disputes", 7, "H", "admins; vendors read/submit evidence for own orders",
           "Stripe dispute with admin attribution to responsible vendor orders and vendor evidence.",
           states=("warning_needs_response", "needs_response", "under_review", "won", "lost"),
           relations=("payment_id -> payments", "order_id -> orders"),
           indexes=(I("provider_dispute_id", unique=True), I("payment_id"))),
    Entity("WebhookEvents", "webhook_events", 7, "H", "system",
           "Verified Stripe events, stored once by event id for idempotent processing.", states=("processing", "processed", "failed"),
           indexes=(I("event_id", unique=True),)),
    Entity("CommissionRules", "commission_rules", 7, "H", "super_admin",
           "Versioned commission rates (bps) by scope default/category/vendor. Changes supersede; history kept.",
           states=("active", "superseded", "ended"), indexes=(I("scope", "scope_id", "status"),)),

    Entity("ShippingMethods", "shipping_methods", 6, "I", "vendor_id (null = platform-wide)",
           "Admin-defined shipping options (flat amount, optional free-over threshold). None seeded: checkout shows 'rate to be confirmed'.", states=("active", "inactive"), relations=("vendor_id -> vendors",),
           indexes=(I("vendor_id", "status"),)),
    Entity("Shipments", "shipments", 8, "I", "vendor_id; customer reads own",
           "Carrier tracking for a vendor order.",
           states=("label_created", "in_transit", "out_for_delivery", "delivered", "exception", "returned"),
           relations=("vendor_order_id -> vendor_orders",),
           indexes=(I("vendor_order_id"), I("tracking_number"))),
    Entity("Returns", "returns", 8, "I", "customer_id requests; vendor_id/admins resolve",
           "Return/RMA for one or more order items.",
           states=("requested", "approved", "rejected", "in_transit", "received", "refunded", "closed"),
           relations=("order_item_id -> order_items", "customer_id -> users", "vendor_id -> vendors"),
           indexes=(I("customer_id", "-created_at"), I("vendor_id", "status"))),

    Entity("Reviews", "reviews", 11, "L", "customer_id; admins moderate",
           "One review per purchased order item.",
           states=("pending", "published", "hidden", "rejected"),
           relations=("product_id -> products", "customer_id -> users", "order_item_id -> order_items"),
           indexes=(I("order_item_id", unique=True), I("product_id", "status", "-created_at"))),
    Entity("Notifications", "notifications", 11, "L", "user_id",
           "In-app/email notification for one user.", states=("unread", "read", "archived"),
           relations=("user_id -> users",), indexes=(I("user_id", "status", "-created_at"),)),
    Entity("SupportTickets", "support_tickets", 11, "L", "requester_id; support_admin handles",
           "Customer or vendor help request.",
           states=("open", "pending_customer", "pending_internal", "resolved", "closed"),
           relations=("requester_id -> users", "order_id -> orders", "assignee_id -> users"),
           indexes=(I("requester_id", "-created_at"), I("status", "-updated_at"))),

    Entity("Coupons", "coupons", 6, "M", "vendor_id (null = platform coupon)",
           "Discount codes (percent in bps or fixed cents), window, min subtotal, usage limit. Redemptions are counted at payment (Phase 07).", states=("draft", "active", "paused", "expired"),
           relations=("vendor_id -> vendors",), indexes=(I("code", unique=True), I("vendor_id", "status"))),
)

ENTITIES_BY_COLLECTION = {e.collection: e for e in ENTITIES}


def active_entities(phase: int) -> list:
    return [e for e in ENTITIES if e.phase <= phase]


def entity_contract(e: Entity) -> dict:
    return {
        "name": e.name,
        "collection": e.collection,
        "phase": e.phase,
        "module": e.module,
        "owner": e.owner,
        "description": e.description,
        "state_field": e.state_field,
        "states": list(e.states),
        "relations": list(e.relations),
        "append_only": e.append_only,
        "indexes": [{"name": i.name, "keys": [list(k) for k in i.keys], "unique": i.unique, **i.options}
                    for i in e.indexes],
    }
