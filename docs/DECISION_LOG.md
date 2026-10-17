# AfroVending — Decision Log

| ID | Date | Decision | Rationale / status |
|---|---|---|---|
| D-001 | 2026-10-17 | Use platform stack React + FastAPI (Python) + MongoDB instead of Next.js/TypeScript/PostgreSQL. | Approved by owner. Equivalent collections, indexes, transactions and server-side authorization designed. |
| D-002 | 2026-10-17 | ObjectId `_id` exposed as string `id`; FKs `<entity>_id`; separate human numbers (e.g. `order_number`). | Mongo-native, stable API ids. |
| D-003 | 2026-10-17 | Money as integer minor units + ISO currency. | Avoids float rounding in commission/payout math. |
| D-004 | 2026-10-17 | Single `users` collection with `roles` array; vendors are a separate business entity owned by a user. | Rule: no duplicate user tables. Supports vendor team members later. |
| D-005 | 2026-10-17 | Central entity registry in code + generated DATABASE_SCHEMA.md; indexes created only for active phases via versioned migrations. | Docs always match code; no premature collections. |
| D-006 | 2026-10-17 | Default currency USD seeded as an **assumption**. | Pending owner confirmation (markets/currencies). |
| D-007 | 2026-10-17 | Default commission rate left `null`. | Business decision required before Phase 07. |
| D-008 | 2026-10-17 | API versioned under `/api/v1`; uniform error envelope with request_id. | Stable contracts for future clients/mobile. |
| D-009 | 2026-10-17 | `/api/v1/system/schema` disabled (404) when `APP_ENV=production`. | Avoid exposing internals publicly. |
| D-010 | 2026-10-17 | Auth provider choice deferred to Phase 01 kickoff. | One provider only, selected with owner. |
