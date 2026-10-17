"""Regenerates docs/DATABASE_SCHEMA.md from afrovending/schema/entities.py. Run: python scripts/export_schema_doc.py"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from afrovending.core.roles import ROLE_DESCRIPTIONS  # noqa: E402
from afrovending.schema.entities import ENTITIES  # noqa: E402

lines = [
    "# AfroVending — Database Schema Contract",
    "",
    "> GENERATED from `backend/afrovending/schema/entities.py` by `backend/scripts/export_schema_doc.py`. Do not edit by hand.",
    "",
    "## Conventions",
    "- Database: MongoDB (`MONGO_URL`, `DB_NAME` from env). Collections are snake_case plural.",
    "- IDs: Mongo `ObjectId` in `_id`, exposed in APIs as string `id` via `BaseDocument` (`PyObjectId`). Foreign keys are stored as ObjectId and named `<entity>_id`.",
    "- Human-facing numbers (e.g. `order_number`) are separate unique fields, never the `_id`.",
    "- Every document has `created_at` / `updated_at` (UTC BSON datetime).",
    "- Money: integer minor units (`amount_minor`) + ISO-4217 `currency`. Never floats.",
    "- Lifecycle: the state lives in `status` unless noted; transitions are enforced server-side and audited.",
    "- Append-only collections are never updated or deleted; corrections are new entries.",
    "- Soft delete: business records use a terminal state (`archived`, `closed`, `deactivated`) instead of deletion.",
    "- Indexes are created only for entities whose phase is active, via versioned migrations (`schema_migrations`).",
    "- Multi-document writes that touch money or stock (checkout, refunds, payouts) use Mongo transactions (replica set required in production).",
    "",
    "## Roles",
    "| Role | Scope |",
    "|---|---|",
]
lines += [f"| `{r.value}` | {d} |" for r, d in ROLE_DESCRIPTIONS.items()]
lines += ["", "## Entity summary", "| Entity | Collection | Phase | Module | Owner |", "|---|---|---|---|---|"]
lines += [f"| {e.name} | `{e.collection}` | {e.phase:02d} | {e.module} | {e.owner} |" for e in ENTITIES]
for e in ENTITIES:
    lines += ["", f"## {e.name} (`{e.collection}`) — Phase {e.phase:02d}", "", e.description, ""]
    lines.append(f"- **Owner:** {e.owner}")
    if e.states:
        lines.append(f"- **States (`{e.state_field}`):** " + " → ".join(f"`{s}`" for s in e.states))
    if e.append_only:
        lines.append("- **Append-only:** yes")
    if e.relations:
        lines.append("- **Relations:** " + ", ".join(f"`{r}`" for r in e.relations))
    for i in e.indexes:
        opts = ", ".join(f"{k}={v}" for k, v in i.options.items())
        flag = " (unique)" if i.unique else ""
        lines.append(f"- **Index** `{i.name}`{flag}{' ' + opts if opts else ''}")

out = BACKEND.parent / "docs" / "DATABASE_SCHEMA.md"
out.write_text("\n".join(lines) + "\n")
print(f"Wrote {out}")
