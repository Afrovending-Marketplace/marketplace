# AfroVending — Phase Status

| Phase | Status | Date |
|---|---|---|
| 00 Project foundation | ✅ Complete | 2026-10-17 |
| 01 Public storefront | ✅ Complete | 2026-10-17 |
| 02 Identity & customer accounts (+ owner content update) | ✅ Complete — awaiting owner approval | 2026-10-17 |
| 03 Vendor onboarding & verification | ⏸ Not started | — |
| 04–14 | ⏸ Not started | — |

## Phase 02 deliverables
- Central auth (email/password): register, login, logout, refresh, me, email verification, resend, forgot/reset password, change password.
- Sessions: httpOnly cookies + revocable server sessions; logout, password reset/change and deactivation revoke sessions.
- RBAC: `require_roles()` on every admin route; frontend `ProtectedRoute` (+ role gating for `/admin`, `/vendor/dashboard`).
- Account: dashboard (orders & wishlist placeholders), profile, password, address book (≤10, default), privacy requests, deactivation.
- Admin APIs: users list, create staff (super_admin), privacy request handling, audit log viewer.
- Rate limiting + audit logs for all sensitive actions. Origin check on mutating requests.
- Branded transactional emails (verification, reset, security notices) via Emergent managed Resend — delivery verified.
- Content: About, Contact (form → info@afrovending.com), FAQ, footer contact, 6 draft policy pages.

## Pending / owner action
- **Contact form delivery to info@afrovending.com is PENDING**: afrovending.com DNS refuses MX lookups (lame delegation at Cloudflare), so the provider rejects the address. Form shows an honest failure message and logs the inquiry. Fix DNS/MX, then re-test.
- Rotate `ADMIN_PASSWORD` before production. Legal review of all policy pages.
