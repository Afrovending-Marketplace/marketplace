import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { StatusBadge } from "@/components/common/StatusBadge";
import { PolicyMarkdown } from "@/pages/LegalPages";
import { api, getErrorMessage } from "@/lib/api";

const LABEL = { draft: "Draft", pending_review: "Draft — Pending Legal Review", approved: "Approved", published: "Published", archived: "Archived" };
const TONE = { draft: "neutral", pending_review: "gold", approved: "success", published: "success", archived: "neutral" };
const ET = (s) => (s ? new Date(s).toLocaleString("en-US", { timeZone: "America/New_York", dateStyle: "medium", timeStyle: "short" }) + " ET" : "—");
const act = (path, body, msg, done) => api.post(`/admin/policies/versions/${path}`, body).then(() => { toast.success(msg); done(); }).catch((e) => toast.error(getErrorMessage(e)));

function ApproveForm({ v, acceptance, done }) {
  const [f, setF] = useState({ legal_review_confirmed: false, reviewer_name: "", reviewer_firm: "", review_date: "", review_notes: "",
    classification: acceptance ? "" : "non_material", change_summary: v.change_summary || "", effective_date: v.effective_date || "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  return (
    <div className="space-y-3 rounded-xl border border-av-line p-4" data-testid="policy-approve-form">
      <h3 className="font-semibold">Record legal approval</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <Input placeholder="Reviewing attorney's name" value={f.reviewer_name} onChange={set("reviewer_name")} data-testid="approve-reviewer" />
        <Input placeholder="Law firm (optional)" value={f.reviewer_firm} onChange={set("reviewer_firm")} data-testid="approve-firm" />
        <label className="text-xs">Legal review completed on<Input type="date" value={f.review_date} onChange={set("review_date")} data-testid="approve-review-date" /></label>
        <label className="text-xs">Effective date<Input type="date" value={f.effective_date} onChange={set("effective_date")} data-testid="approve-effective-date" /></label>
      </div>
      {acceptance && (
        <select value={f.classification} onChange={set("classification")} className="h-9 w-full rounded-md border border-av-line px-2 text-sm" data-testid="approve-classification">
          <option value="">Classify this change…</option>
          <option value="material">Material — affected users must accept again</option>
          <option value="non_material">Non-material — corrections or clarifications, no re-acceptance</option>
        </select>
      )}
      <Textarea placeholder="Change summary shown to users" value={f.change_summary} onChange={set("change_summary")} data-testid="approve-summary" />
      <Textarea placeholder="Review notes (optional)" value={f.review_notes} onChange={set("review_notes")} data-testid="approve-notes" />
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={f.legal_review_confirmed} onChange={set("legal_review_confirmed")} data-testid="approve-confirm" />
        <span>I confirm an external legal review of this exact version has actually been completed and the reviewer approved it.</span></label>
      <Button size="sm" disabled={!f.legal_review_confirmed || !f.classification} onClick={() => act(`${v.id}/approve`, f, "Legal approval recorded", done)} data-testid="approve-submit">Record approval</Button>
    </div>
  );
}

function VersionPanel({ id, meta, isSuper, reload }) {
  const [v, setV] = useState(null);
  const [edit, setEdit] = useState(null);
  const [note, setNote] = useState("");
  const [typed, setTyped] = useState("");
  const load = useCallback(() => api.get(`/admin/policies/versions/${id}`).then((r) => { setV(r.data); setEdit(null); }), [id]);
  useEffect(() => { load(); }, [load]);
  if (!v) return null;
  const done = () => { load(); reload(); };
  const save = () => api.put(`/admin/policies/versions/${id}`, { body: edit.body, change_summary: edit.change_summary, effective_date: edit.effective_date || null })
    .then(() => { toast.success("Draft saved"); done(); }).catch((e) => toast.error(getErrorMessage(e)));
  const publish = () => act(`${id}/publish`, { confirm: typed }, "Published", done);
  const archive = () => (note.trim().length >= 5 ? act(`${id}/archive`, { reason: note }, "Archived", done) : toast.error("Write the reason for archiving (at least 5 characters) in the note box first."));
  return (
    <div className="space-y-4" data-testid="policy-version-panel">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{meta.title} · v{v.version}</h2>
        <StatusBadge tone={TONE[v.status]} testId="policy-version-status">{LABEL[v.status]}</StatusBadge>
        {v.classification && <StatusBadge tone="neutral">{v.classification === "material" ? "Material" : "Non-material"}</StatusBadge>}
      </div>
      <p className="text-xs text-av-muted">Effective {v.effective_date || "[not set]"} · created by {v.created_by} · accepted by {v.acceptance_count} user(s){v.published_at && ` · published ${ET(v.published_at)}`}</p>
      {v.legal_review && <p className="text-xs text-av-muted" data-testid="policy-legal-review">Legal review: {v.legal_review.reviewer_name}{v.legal_review.reviewer_firm && `, ${v.legal_review.reviewer_firm}`} on {v.legal_review.review_date} (recorded by {v.legal_review.recorded_by})</p>}
      <div className="flex flex-wrap gap-2">
        {v.status === "draft" && !edit && <Button size="sm" variant="outline" onClick={() => setEdit({ body: v.body, change_summary: v.change_summary || "", effective_date: v.effective_date || "" })} data-testid="policy-edit">Edit draft</Button>}
        {v.status === "draft" && <Button size="sm" onClick={() => act(`${id}/submit`, { note }, "Submitted for legal review", done)} data-testid="policy-submit">Submit for legal review</Button>}
        {isSuper && v.status === "pending_review" && <Button size="sm" variant="outline" onClick={() => (note.trim().length >= 5 ? act(`${id}/request-changes`, { note }, "Sent back for changes", done) : toast.error("Write the requested changes in the note box first."))} data-testid="policy-request-changes">Request changes</Button>}
        {isSuper && v.status === "approved" && <><Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type PUBLISH to confirm" className="w-48" data-testid="policy-publish-confirm" />
          <Button size="sm" disabled={typed !== "PUBLISH"} onClick={publish} data-testid="policy-publish">Publish</Button></>}
        {isSuper && v.status !== "archived" && <Button size="sm" variant="outline" onClick={archive} data-testid="policy-archive">Archive</Button>}
      </div>
      {(v.status === "draft" || isSuper) && v.status !== "archived" && <Textarea placeholder={isSuper ? "Note / feedback / archive reason (saved in the version history)" : "Note (saved in the version history)"} value={note} onChange={(e) => setNote(e.target.value)} data-testid="policy-note" />}
      {isSuper && v.status === "pending_review" && <ApproveForm v={v} acceptance={!!meta.acceptance} done={done} />}
      {edit ? (
        <div className="space-y-2" data-testid="policy-editor">
          <Input placeholder="Change summary" value={edit.change_summary} onChange={(e) => setEdit({ ...edit, change_summary: e.target.value })} data-testid="policy-edit-summary" />
          <Input type="date" value={edit.effective_date} onChange={(e) => setEdit({ ...edit, effective_date: e.target.value })} className="w-44" data-testid="policy-edit-effective" />
          <Textarea value={edit.body} onChange={(e) => setEdit({ ...edit, body: e.target.value })} className="min-h-[420px] font-mono text-xs" data-testid="policy-edit-body" />
          <div className="flex gap-2"><Button size="sm" onClick={save} data-testid="policy-save">Save draft</Button><Button size="sm" variant="outline" onClick={() => setEdit(null)} data-testid="policy-cancel-edit">Cancel</Button></div>
        </div>
      ) : <div className="max-h-[520px] overflow-y-auto rounded-xl border border-av-line bg-white p-4"><PolicyMarkdown body={v.body} testId="policy-preview" /></div>}
      <ul className="space-y-1 text-xs text-av-muted" data-testid="policy-history">{v.history.map((h, i) => <li key={i}>{ET(h.at)} · {LABEL[h.status]} · {h.by}{h.note && ` — ${h.note}`}</li>)}</ul>
    </div>
  );
}

function PolicyDetail({ p, isSuper, reload }) {
  const [versions, setVersions] = useState([]);
  const [sel, setSel] = useState(null);
  const load = useCallback(() => api.get(`/admin/policies/${p.slug}/versions`).then((r) => { setVersions(r.data.data); setSel((s) => s || r.data.data[0]?.id); }), [p.slug]);
  useEffect(() => { setSel(null); load(); }, [load]);
  const refresh = () => { load(); reload(); };
  const newDraft = () => api.post(`/admin/policies/${p.slug}/versions`, {}).then((r) => { toast.success(`Draft v${r.data.version} created`); setSel(r.data.id); refresh(); }).catch((e) => toast.error(getErrorMessage(e)));
  return (
    <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
      <div className="space-y-2">
        <Button size="sm" variant="outline" className="w-full" onClick={newDraft} disabled={!!p.open} data-testid="policy-new-draft">New draft version</Button>
        <ul className="space-y-1 text-sm" data-testid="policy-versions">{versions.map((v) => (
          <li key={v.id}><button type="button" onClick={() => setSel(v.id)} className={`w-full rounded-lg px-3 py-2 text-left ${sel === v.id ? "bg-av-sand font-semibold" : "hover:bg-av-sand/60"}`} data-testid={`policy-version-${v.version}`}>
            v{v.version} · {LABEL[v.status]}</button></li>))}</ul>
      </div>
      {sel && <VersionPanel key={sel} id={sel} meta={p} isSuper={isSuper} reload={refresh} />}
    </div>
  );
}

export default function AdminPoliciesPage() {
  const [d, setD] = useState(null);
  const [slug, setSlug] = useState("terms");
  const [err, setErr] = useState("");
  const load = useCallback(() => api.get("/admin/policies").then((r) => setD(r.data)).catch((e) => setErr(getErrorMessage(e))), []);
  useEffect(() => { load(); }, [load]);
  if (err) return <p className="av-container py-12" data-testid="policies-error">{err}</p>;
  if (!d) return null;
  const p = d.data.find((x) => x.slug === slug);
  return (
    <div className="av-container max-w-6xl space-y-6 py-12" data-testid="admin-policies-page">
      <div><p className="av-eyebrow">Admin</p><h1 className="mt-2 text-4xl font-bold text-av-ink">Policy management</h1>
        <p className="mt-1 text-sm text-av-muted">Draft → Pending Legal Review → Approved → Published → Archived. Only published versions are public. {d.is_super_admin ? "You can approve and publish." : "Content admins edit and submit; the Super Admin approves and publishes."}</p></div>
      <div className="flex flex-wrap gap-2" data-testid="policy-tabs">{d.data.map((x) => (
        <button key={x.slug} type="button" onClick={() => setSlug(x.slug)} className={`rounded-full border px-3 py-1.5 text-sm ${x.slug === slug ? "border-av-ink bg-av-ink text-white" : "border-av-line"}`} data-testid={`policy-tab-${x.slug}`}>
          {x.title} <span className="opacity-70">· {x.published ? `v${x.published.version} live` : "not published"}</span></button>))}</div>
      <PolicyDetail p={p} isSuper={d.is_super_admin} reload={load} />
    </div>
  );
}
