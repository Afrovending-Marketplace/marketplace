# AfroVending — API Contracts

## Conventions
- **Base path:** `/api/v1`. Breaking changes ship as `/api/v2`; v1 contracts are never silently changed. `/api` returns available versions.
- **Format:** JSON, snake_case fields. IDs are strings (`id`). Timestamps ISO-8601 UTC. Money: integer `amount_minor` + `currency`.
- **Single resource:** returned as the object. **Lists:** `{"data": [...], "meta": {"page": 1, "page_size": 20, "total": 0}}` (page_size max 100).
- **Errors (all endpoints):**
  ```json
  {"error": {"code": "validation_error", "message": "Request validation failed.", "details": [{"field": "email", "message": "..."}], "request_id": "..."}}
  ```
  Codes: `bad_request` 400, `unauthorized` 401, `forbidden` 403, `not_found` 404, `method_not_allowed` 405, `conflict` 409, `validation_error` 422, `rate_limited` 429, `internal_error` 500. Raise `APIError(status, code, message, details)` from services.
- **Validation:** Pydantic models on every request body/query; unknown fields ignored on input models unless stated.
- **Headers:** `X-Request-ID` (in/out), `X-Content-Type-Options: nosniff`.
- **Auth (from Phase 01):** documented per endpoint as `Auth: public | customer | vendor | admin(<role>)`.
- **Idempotency (from Phase 06/07):** mutating money endpoints require `Idempotency-Key` header.

## Phase 02 endpoints (all under `/api/v1`)
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | public, 10/h/IP | `{name,email,password}` → 201 `{user, verification_email_sent}` + cookies |
| POST | `/auth/login` | public, lockout 5/15 min per IP+email, 20 per email | → `{user}` + cookies; 401 `invalid_credentials`, 403 `account_inactive`, 429 |
| POST | `/auth/logout` | cookie | revokes session, clears cookies |
| POST | `/auth/refresh` | refresh cookie | new access cookie |
| GET | `/auth/me` | user | `{user}` |
| POST | `/auth/verify-email` | public | `{token}` single-use, 24 h |
| POST | `/auth/resend-verification` | user, 3/h | |
| POST | `/auth/forgot-password` | public | always generic 200; token 1 h |
| POST | `/auth/reset-password` | public | `{token,password}`; revokes all sessions |
| POST | `/auth/change-password` | user | revokes other sessions |
| GET/PATCH | `/account/profile` | user | `{name, phone}` |
| GET/POST | `/account/addresses` | user (owner-scoped) | max 10; first = default |
| PATCH/DELETE | `/account/addresses/{id}` | owner | 404 for other users' ids |
| POST | `/account/deactivate` | user (non-admin) | `{password, reason}` |
| GET/POST | `/account/privacy-requests` | user | types `data_export`, `data_deletion`, `data_correction` |
| GET | `/admin/users` | any admin | paginated |
| POST | `/admin/staff` | super_admin | strong password required |
| GET/PATCH | `/admin/privacy-requests[/{id}]` | marketplace_admin, super_admin | |
| GET | `/admin/audit-logs` | super_admin | paginated |
| POST | `/contact` | public, 5/h/IP | `{name,email,subject,message}` → emails CONTACT_INBOX; 503 if undeliverable |

User object: `{id, email, name, phone, roles[], status, email_verified, created_at}`. Mutating requests with a foreign `Origin` → 403.

## Phase 01
No new endpoints (storefront uses frontend development data). `health.phase` now reports `1`.

## Implemented endpoints (Phase 00)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api` | public | `{"service","versions":["v1"],"current":"/api/v1"}` |
| GET | `/api/v1/health` | public | `{"status":"ok"|"degraded","database":"ok"|"unavailable","service","version","environment","phase","time"}` |
| GET | `/api/v1/platform` | public | `{"settings": {<key>: <value>}}` — only `platform_settings` with `is_public=true` |
| GET | `/api/v1/system/schema` | public in non-production; **404 when `APP_ENV=production`** | Roles, full entity contract (collections, states, relations, indexes) and applied migrations |
| GET | `/api/docs` | public (non-prod recommended) | OpenAPI UI |
