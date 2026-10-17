# AfroVending — Architecture

## Confirmed stack (Decision D-001)
| Layer | Choice | Notes |
|---|---|---|
| Frontend | React 19 (CRA + CRACO), React Router 7, Tailwind CSS 3, shadcn/ui (Radix), lucide-react, sonner | JavaScript (JSX). Platform-supported; Next.js/TypeScript not used. |
| Backend | Python 3 · FastAPI · Motor (async MongoDB) · Pydantic v2 | Modular package `backend/afrovending/`. Entry: `backend/server.py` (supervisor runs `server:app` on 0.0.0.0:8001). |
| Database | MongoDB (`MONGO_URL`, `DB_NAME`) | Collections/indexes defined centrally; transactions for money/stock writes (replica set in prod). |
| Auth (Phase 01) | One provider only — chosen at Phase 01 (JWT email+password or Emergent-managed Google login). | Not implemented in Phase 00. |
| Storage (Phase 03) | Emergent object storage | Product/vendor media, private KYC documents with controlled access. |
| Payments (Phase 07) | Stripe Connect, test mode until approved | No real transactions without approval. |
| Email (Phase 11) | Resend (Emergent-managed) | Transactional only. |
| Deployment | Emergent preview → Emergent production (on approval) | Codebase is portable (env-driven). |
| Source control | Git repo in workspace; GitHub via the platform's "Save to GitHub" | See DEPLOYMENT_RUNBOOK.md. |

## Repository layout
```
backend/
  server.py                 # app assembly: lifespan (migrations), middleware, error handlers, routers
  afrovending/
    core/config.py          # env-driven settings (fail fast), APP_VERSION, CURRENT_PHASE
    core/db.py              # single Motor client/db
    core/models.py          # PyObjectId, BaseDocument (_id→id), PlatformSetting, AuditLog
    core/roles.py           # Role enum + scopes (single source of truth)
    core/errors.py          # APIError + uniform error envelope handlers
    core/logging.py         # logging config, request-id + access log middleware
    schema/entities.py      # ENTITY REGISTRY: collections, phases, owners, states, relations, indexes
    migrations/runner.py    # versioned migrations recorded in schema_migrations
    api/v1/                 # versioned routers (/api/v1/...)
  fixtures/                 # dev/seed fixtures (idempotent, $setOnInsert)
  scripts/export_schema_doc.py
  tests/                    # pytest suites (one file per phase)
frontend/src/
  App.js                    # router: AppShell layout + routes
  config/site.js            # brand, nav, footer, FUTURE_ROUTES (phase-tagged placeholders)
  config/designTokens.js    # design-system tokens for documentation page
  components/layout/        # AppShell, SiteHeader, MobileNav, SiteFooter, BrandLogo, ApiStatus
  components/common/        # StatusAlert, StatusBadge, SectionHeading (shared primitives)
  components/ui/            # shadcn primitives (Button themed with brand variants)
  components/home/, components/design-system/
  pages/                    # one default-export page per route
  lib/api.js                # axios instance → `${REACT_APP_BACKEND_URL}/api/v1`
  constants/testIds/        # data-testid registry per feature
docs/                       # this documentation set
```

## Module boundaries (A–N)
Each future module gets `backend/afrovending/<module>/` (models, service, router) and registers its router in `api/v1/__init__.py`. Modules talk through service functions, never by writing another module's collections directly. Shared concerns (auth dependency, permissions, audit, pagination) live in `core/`.

## Authorization model (enforced from Phase 01)
- Roles: see `core/roles.py` and DATABASE_SCHEMA.md. A user may hold several roles (`users.roles` array).
- Every protected endpoint uses a server-side dependency (`require_roles(...)`) plus an ownership check (`resource.<owner_field> == current_user` or vendor membership). UI hiding is never the control.
- Vendor-scoped queries always filter by `vendor_id` derived from the session, never from client input.
- Admin actions and all money/state transitions write `audit_logs`.

## Cross-cutting
- Request ID: accepted from `X-Request-ID` or generated; returned in header and every error body.
- Logging: stdout, `LOG_LEVEL` env; one access line per request (method, path, status, ms, request_id). No secrets/PII in logs.
- Migrations: run at startup, idempotent, recorded in `schema_migrations` + audit log. Indexes are created only for entities whose phase is active.
- Config: all URLs/credentials from env; missing required env fails at boot.
