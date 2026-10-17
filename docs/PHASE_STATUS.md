# AfroVending — Phase Status

| Phase | Status | Date |
|---|---|---|
| 00 Project foundation | ✅ Complete | 2026-10-17 |
| 01 Public storefront | ✅ Complete | 2026-10-17 |
| 02 Identity & customer accounts | ✅ Complete | 2026-10-17 |
| 03 Vendor onboarding (+ brand red theme) | ✅ Complete — awaiting owner approval | 2026-10-17 |
| 04 Catalog & vendor product management | ⏸ Not started | — |
| 05–14 | ⏸ Not started | — |

## Phase 03 deliverables
- Vendor application (`/vendor/apply`): business, contact, location, categories, description, logo, banner, unique store slug; Vendor Agreement acceptance recorded (version, timestamp, IP) in `vendor_policy_acceptances`.
- Admin review (`/admin/vendors`): approve / reject / request more info (optionally require a verification document); applicant emailed on every decision.
- Verification documents: private object storage, downloadable only by marketplace_admin / super_admin (audited), soft-deletable by admins.
- Approval creates `vendors` + `vendor_stores` (draft) and grants the `vendor` role on the same user account (no second auth system).
- Vendor dashboard (`/vendor/dashboard`): edit store profile, publish/unpublish. Public store at `/store/:slug` only when published and vendor active.
- Suspension pauses the store, blocks edits/publishing/uploads; reactivation restores publishing. Both emailed and audited.
- Brand red (#D40000) applied to primary buttons, links, focus ring.

## Document retention & deletion policy (D-021)
- Verification documents are kept while the application is under review and while the vendor is active, plus 90 days after rejection or account closure, then deleted.
- Deletion today = admin soft delete (`DELETE /admin/vendor-documents/{id}`), which removes all access immediately. Storage has no hard-delete API; the file stays in private storage unreachable by any endpoint.
- Automated 90-day cleanup job: **not built yet** (scheduled job proposed for Phase 13). Policy text needs founder/legal review.

## Pending / owner action
- Contact form delivery to info@afrovending.com still PENDING (domain DNS/MX).
- Vendor Agreement is a draft; version string `vendor-agreement-draft-2026-10-17` must be bumped when legal text is approved (vendors will re-accept).
