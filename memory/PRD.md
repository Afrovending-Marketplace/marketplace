# AfroVending — PRD

## Original problem statement
AFROVENDING — PERMANENT MASTER DEVELOPMENT INSTRUCTIONS: AfroVending Online Marketplace (https://www.afrovending.com, AfroVending Online Marketplace LLC). Scalable, responsive, multi-vendor e-commerce marketplace connecting African, Caribbean, diaspora and global entrepreneurs with customers. "From Culture to Commerce." Build phase by phase within one persistent architecture; stop after each phase for approval; modules A–N; roles Guest → Super Administrator with server-side enforcement; maintain docs/ (MASTER_PLAN, ARCHITECTURE, DATABASE_SCHEMA, API_CONTRACTS, DESIGN_SYSTEM, PHASE_STATUS, DECISION_LOG, TEST_REPORT, DEPLOYMENT_RUNBOOK).

Phase 00 request: "Execute AfroVending Phase 00: Project Foundation. Inspect workspace... Define modular architecture; confirm stack; responsive app shell with shared navigation and footer; global design system; define all core entities, relationships, IDs, ownership, lifecycle states, indexes; shared API conventions, validation, error handling, versioning; project documentation; env variable names, dev fixtures, logging, testing tools; GitHub source control where supported; dependency map Phases 01–14. Do not build checkout, vendor dashboards, payments or other future functionality. Stop and request approval before Phase 01."

## Architecture
React 19 + Tailwind + shadcn (frontend) · FastAPI modular package `backend/afrovending` · MongoDB. See /app/docs/ARCHITECTURE.md.

## User personas
Guest, Customer, Vendor Applicant, Vendor, Vendor Team Member (future), Support Admin, Marketplace Admin, Super Admin.

## Core requirements (static)
Multi-vendor marketplace modules A–N; server-side RBAC; versioned migrations; no real payments/production deploy without approval.

## Implemented
- 2026-10-17 — Phase 00: app shell, design system (/design-system), coming-soon routes per phase, 404; /api/v1 health/platform/system-schema; error envelope + request-id logging; entity registry (31 collections) + migration 0001; platform_settings fixtures; docs set; pytest baseline (11 + 8) and e2e 47/47.
- 2026-10-17 — Phase 01 Public Storefront: announcement bar, header (search entry, account, cart, sell link), 9-category nav, mobile menu, homepage sections, reusable product/vendor/category cards, category/product/vendor/search/shop templates, About/Contact/FAQ/Privacy/Terms/Sell layouts, UI-only newsletter & contact forms, labelled development data (frontend). Roadmap renumbered (auth now Phase 02). Tests: backend 19/19, e2e 100%, axe 0 violations.
- 2026-10-17 — Phase 02 Identity & accounts: JWT email/password auth with revocable sessions, verification & reset emails (Emergent Resend), profile, address book, privacy requests, deactivation, RBAC (admin APIs + route guards), rate limits, audit logs; owner content (About/Contact/FAQ/footer, 6 draft policies). Contact form → info@afrovending.com PENDING (domain DNS). Tests 42/42 backend + e2e.
- 2026-10-17 — Brand red theme (#D40000). Phase 03 Vendor onboarding: application form with logo/banner/slug, policy acceptance record, admin review (approve/reject/request info + required docs), private verification documents (admin-only), vendor role on same account, store editor + publish, public /store/:slug, suspend/reactivate, email notices. Tests 52/52 backend + e2e.
- 2026-10-19 — Phase 04 Product catalog & inventory: vendor product CRUD with deletion safeguards, variants (3 options, SKU/price/stock), optimized WebP images, draft/pending/active/rejected/archived states, inventory adjustments with append-only history + low-stock alerts, admin moderation, category management (seeded 9 + subcategories), CSV import with preview/errors, public /api/v1/catalog APIs feeding the storefront. Tests 57/57 backend + e2e (iteration_5). Next: Phase 05 storefronts & search (awaiting approval).
- 2026-10-19 — Phase 05 Search & discovery: weighted full-text search + partial fallback, suggestions, category/subcategory/price/vendor/availability filters, relevance/newest/price sorts, load-more pagination, URL state, empty/error states, anonymous privacy-safe search analytics + admin insights, indexes tested at 1,500 products. Restock reminders: vendor choice of instant vs weekly digest via platform cron. Tests 69/69 + e2e (iteration_6).

## Prioritized backlog
- P0: Phase 06 cart & checkout (awaiting approval)
- P1: Phases 06–08 (cart/checkout → orders/shipping)
- P2: Phases 09–14; automated vendor-document cleanup job; CSV image import

## Next tasks
Await owner approval for Phase 06. Email: Emergent Managed Email now; branded sending from info@afrovending.com is a go-live task (DEPLOYMENT_RUNBOOK step 7, D-029) — needs owner's email-provider account, verified afrovending.com DNS (SPF/DKIM/DMARC) and sending key. Open owner decisions: currencies (USD only today), commission rate, legal copy, supported markets, afrovending.com DNS for contact email.
