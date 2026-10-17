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
           "Hierarchical catalog taxonomy (parent_id).",
           states=("active", "hidden"), relations=("parent_id -> categories",),
           indexes=(I("slug", unique=True), I("parent_id", "sort_order"))),
    Entity("Products", "products", 4, "E", "vendor_id",
           "Sellable listing owned by one vendor.",
           states=("draft", "pending_review", "active", "inactive", "rejected", "archived"),
           relations=("vendor_id -> vendors", "category_id -> categories"),
           indexes=(I("slug", unique=True), I("vendor_id", "status"), I("category_id", "status"),
                    I("title:text", "description:text", "tags:text"))),
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
           indexes=(I("variant_id", unique=True), I("vendor_id")), state_field=None),

    Entity("VendorStores", "vendor_stores", 5, "D", "vendor_id",
           "Public storefront profile (branding, policies) for a vendor.",
           states=("draft", "published", "paused"), relations=("vendor_id -> vendors",),
           indexes=(I("vendor_id", unique=True), I("slug", unique=True), I("status"))),

    Entity("Carts", "carts", 6, "G", "user_id or guest_token",
           "One active cart per customer or guest session; spans multiple vendors.",
           states=("active", "converted", "abandoned", "expired"), relations=("user_id -> users",),
           indexes=(I("user_id", "status"), I("guest_token"), I("expires_at", expireAfterSeconds=0))),
    Entity("CartItems", "cart_items", 6, "G", "cart owner",
           "Line in a cart; price is re-validated at checkout.",
           relations=("cart_id -> carts", "variant_id -> product_variants", "vendor_id -> vendors"),
           indexes=(I("cart_id", "variant_id", unique=True),), state_field=None),
    Entity("Orders", "orders", 6, "G", "customer_id",
           "Customer-facing order; split into VendorOrders per vendor.",
           states=("pending_payment", "paid", "partially_fulfilled", "fulfilled", "completed",
                   "cancelled", "partially_refunded", "refunded"),
           relations=("customer_id -> users",),
           indexes=(I("order_number", unique=True), I("customer_id", "-created_at"), I("status", "-created_at"))),
    Entity("VendorOrders", "vendor_orders", 6, "I", "vendor_id (fulfils); customer_id (reads)",
           "The slice of an order a single vendor must fulfil.",
           states=("pending", "accepted", "processing", "shipped", "delivered", "cancelled", "returned"),
           relations=("order_id -> orders", "vendor_id -> vendors"),
           indexes=(I("order_id"), I("vendor_id", "status", "-created_at"))),
    Entity("OrderItems", "order_items", 6, "G", "customer_id; vendor_id",
           "Immutable price/qty snapshot of a purchased variant.",
           relations=("order_id -> orders", "vendor_order_id -> vendor_orders", "variant_id -> product_variants"),
           indexes=(I("order_id"), I("vendor_order_id"), I("vendor_id", "-created_at")), state_field=None),

    Entity("Payments", "payments", 7, "H", "system; customer reads own",
           "Provider payment record (Stripe Connect). Idempotency enforced.",
           states=("requires_payment", "processing", "succeeded", "failed", "cancelled", "refunded"),
           relations=("order_id -> orders",),
           indexes=(I("order_id"), I("idempotency_key", unique=True),
                    I("provider_payment_id", unique=True, sparse=True))),
    Entity("Refunds", "refunds", 7, "H", "admins write; customer reads own",
           "Full or partial refund against a payment.",
           states=("requested", "approved", "processing", "succeeded", "failed", "rejected"),
           relations=("payment_id -> payments", "order_id -> orders", "return_id -> returns"),
           indexes=(I("payment_id"), I("order_id"), I("status", "-created_at"))),
    Entity("CommissionLedger", "commission_ledger", 7, "H", "system; vendor reads own",
           "Append-only double-entry style ledger of sales, commission, refunds, payouts (minor units).",
           relations=("vendor_id -> vendors", "vendor_order_id -> vendor_orders", "payout_id -> payouts"),
           indexes=(I("vendor_id", "-created_at"), I("source_type", "source_id", "entry_type", unique=True)),
           append_only=True, state_field=None),
    Entity("Payouts", "payouts", 7, "H", "vendor reads own; super_admin approves",
           "Transfer of vendor balance to connected account.",
           states=("scheduled", "processing", "paid", "failed", "cancelled"),
           relations=("vendor_id -> vendors",),
           indexes=(I("vendor_id", "-created_at"), I("status"))),

    Entity("ShippingMethods", "shipping_methods", 8, "I", "vendor_id (null = platform-wide)",
           "Rate rules a vendor offers.", states=("active", "inactive"), relations=("vendor_id -> vendors",),
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

    Entity("Coupons", "coupons", 12, "M", "vendor_id (null = platform coupon)",
           "Discount codes with usage limits.", states=("draft", "active", "paused", "expired"),
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
