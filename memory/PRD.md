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

## Prioritized backlog
- P0: Phase 01 Auth, accounts & roles (choose single auth provider)
- P1: Phases 02–08 (vendor onboarding → orders/shipping)
- P2: Phases 09–14

## Next tasks
Await owner approval for Phase 01. Open owner decisions: default currency (USD assumed), commission rate, auth provider.
