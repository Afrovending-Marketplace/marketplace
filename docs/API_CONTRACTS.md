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

## Implemented endpoints (Phase 00)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api` | public | `{"service","versions":["v1"],"current":"/api/v1"}` |
| GET | `/api/v1/health` | public | `{"status":"ok"|"degraded","database":"ok"|"unavailable","service","version","environment","phase","time"}` |
| GET | `/api/v1/platform` | public | `{"settings": {<key>: <value>}}` — only `platform_settings` with `is_public=true` |
| GET | `/api/v1/system/schema` | public in non-production; **404 when `APP_ENV=production`** | Roles, full entity contract (collections, states, relations, indexes) and applied migrations |
| GET | `/api/docs` | public (non-prod recommended) | OpenAPI UI |
