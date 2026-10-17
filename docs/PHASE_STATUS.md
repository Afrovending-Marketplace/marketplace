# AfroVending — Phase Status

| Phase | Status | Date |
|---|---|---|
| 00 Project foundation | ✅ Complete | 2026-10-17 |
| 01 Public storefront | ✅ Complete — awaiting owner approval | 2026-10-17 |
| 02 Authentication, accounts & roles | ⏸ Not started | — |
| 03–14 | ⏸ Not started | — |

## Phase 01 deliverables
- Announcement bar (dismissible, remembered per browser), redesigned header (logo, search entry, account, cart, "Sell on AfroVending"), category navigation for all 9 categories, mobile menu.
- Homepage: promotional hero, shop-by-category, featured products, trending categories, new arrivals, featured vendors, how it works, vendor CTA.
- Reusable `ProductCard`, `VendorCard`, `CategoryTile`, `ProductRail`, `ListingLayout`, `SortSelect`, `FilterSidebar`, `Breadcrumbs`, `PageHero`, `DevDataNotice`, `LegalLayout`, `NewsletterSignup`.
- Templates: `/shop`, `/categories`, `/categories/:slug`, `/products/:slug`, `/vendors`, `/vendors/:slug`, `/search?q=`.
- Content layouts: `/about`, `/contact`, `/faq`, `/privacy`, `/terms`, `/sell` (vendor info). `/help` → `/faq`, `/become-vendor` → `/sell`.
- Development data: `frontend/src/data/dev/catalog.js` (9 categories, 5 fictional vendors, 16 fictional products). Labelled on every page and card.

## Deferred (intentionally not built)
Accounts (Phase 02), cart/checkout (06), real search & filters (05), newsletter & contact delivery (11/12), reviews (11), legal copy (owner/legal counsel), vendor applications (03).
