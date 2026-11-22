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
      <div className="space-y-6">
        <ChangeTracker slug={p.slug} isSuper={isSuper} />
        {sel && <VersionPanel key={sel} id={sel} meta={p} isSuper={isSuper} reload={refresh} />}
      </div>
    </div>
  );
}

const CHG = { open: "Open", in_progress: "In progress", done: "Done", wont_do: "Won't do" };
const CHG_TONE = { open: "danger", in_progress: "gold", done: "success", wont_do: "neutral" };

function ChangeTracker({ slug, isSuper }) {
  const [d, setD] = useState(null);
  const [notes, setNotes] = useState({});
  const load = useCallback(() => api.get("/admin/policies/changes", { params: { slug } }).then((r) => setD(r.data)).catch(() => {}), [slug]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    window.addEventListener("av:changes-updated", load);
    return () => window.removeEventListener("av:changes-updated", load);
  }, [load]);
  if (!d || !d.data.length) return null;
  const set = (c, status) => api.put(`/admin/policies/changes/${c.id}`, { status, note: notes[c.id] || "" })
    .then(() => { toast.success(`Marked ${CHG[status].toLowerCase()}`); setNotes({ ...notes, [c.id]: "" }); load(); }).catch((e) => toast.error(getErrorMessage(e)));
  const open = d.counts.open + d.counts.in_progress;
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-4 text-sm" data-testid="change-tracker">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Attorney-requested changes</h3>
        <StatusBadge tone={open ? "danger" : "success"} testId="change-tracker-open-count">{open ? `${open} open — approval blocked` : "All resolved"}</StatusBadge>
      </div>
      <ul className="space-y-2">{d.data.map((c) => (
        <li key={c.id} className="space-y-2 rounded-xl bg-av-sand p-3" data-testid={`change-item-${c.id}`}>
          <div className="flex flex-wrap items-center gap-2"><StatusBadge tone={CHG_TONE[c.status]} testId={`change-status-${c.id}`}>{CHG[c.status]}</StatusBadge>
            <span className="text-xs text-av-muted">v{c.version}{c.clause && ` · clause ${c.clause}`} · {c.reviewer_name} (pack #{c.pack_number})</span></div>
          <p className="whitespace-pre-wrap">{c.description}</p>
          {c.resolution_note && <p className="text-xs text-av-muted">Resolution: {c.resolution_note}</p>}
          <div className="flex flex-wrap items-center gap-2">
            <Input placeholder="Note (required for Done / Won't do)" value={notes[c.id] || ""} onChange={(e) => setNotes({ ...notes, [c.id]: e.target.value })} className="h-8 max-w-xs" data-testid={`change-note-${c.id}`} />
            {c.status === "open" && <Button size="sm" variant="outline" onClick={() => set(c, "in_progress")} data-testid={`change-progress-${c.id}`}>Start</Button>}
            {["open", "in_progress"].includes(c.status) && <Button size="sm" variant="outline" onClick={() => set(c, "done")} data-testid={`change-done-${c.id}`}>Done</Button>}
            {isSuper && ["open", "in_progress"].includes(c.status) && <Button size="sm" variant="outline" onClick={() => set(c, "wont_do")} data-testid={`change-wontdo-${c.id}`}>Won't do</Button>}
            {isSuper && ["done", "wont_do"].includes(c.status) && <Button size="sm" variant="outline" onClick={() => set(c, "open")} data-testid={`change-reopen-${c.id}`}>Reopen</Button>}
          </div>
        </li>))}</ul>
    </section>
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
      <ReviewPack isSuper={d.is_super_admin} />
    </div>
  );
}

function ReviewPack({ isSuper }) {
  const [packs, setPacks] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get("/admin/policies/review-pack").then((r) => setPacks(r.data.data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const make = async () => {
    setBusy(true);
    try { await api.post("/admin/policies/review-pack"); toast.success("Review pack generated"); load(); } catch (e) { toast.error(getErrorMessage(e)); } finally { setBusy(false); }
  };
  const download = async (p, format) => {
    try {
      const r = await api.get(`/admin/policies/review-pack/${p.id}/download`, { params: { format }, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = Object.assign(document.createElement("a"), { href: url, download: `AfroVending-Legal-Policy-Review-Pack-CONFIDENTIAL-${new Date(p.created_at).toLocaleDateString("en-CA", { timeZone: "America/New_York" })}.${format}` });
      a.click();
      URL.revokeObjectURL(url);
      load();
    } catch (e) { toast.error(getErrorMessage(e)); }
  };
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="review-pack">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h2 className="font-semibold">Lawyer review pack</h2><p className="text-xs text-av-muted">Confidential Word and PDF documents with all seven current drafts, the open questions and the review record. Downloads unlock only after the Super Admin approves the pack for external sharing. Nothing is emailed automatically.</p></div>
        <Button size="sm" onClick={make} disabled={busy} data-testid="review-pack-generate">{busy ? "Generating…" : "Generate new pack"}</Button>
      </div>
      {packs.length === 0 ? <p className="text-sm text-av-muted" data-testid="review-pack-empty">No pack generated yet.</p> : (
        <ul className="divide-y divide-av-line text-sm">{packs.map((p) => <PackRow key={p.id} p={p} isSuper={isSuper} download={download} reload={load} />)}</ul>)}
    </section>
  );
}

function PackRow({ p, isSuper, download, reload }) {
  const [ok1, setOk1] = useState(false);
  const [ok2, setOk2] = useState(false);
  const approve = () => api.post(`/admin/policies/review-pack/${p.id}/approve-sharing`, { confirm: ok1, acknowledge_not_legal_approval: ok2 })
    .then(() => { toast.success("Approved for external sharing"); reload(); }).catch((e) => toast.error(getErrorMessage(e)));
  return (
    <li className="space-y-3 py-3" data-testid={`review-pack-${p.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>Pack #{p.pack_number} · {ET(p.created_at)} · {p.created_by} · {p.downloads} download(s)</span>
        <span className="flex flex-wrap gap-2">
          <StatusBadge tone={p.external_sharing_approved ? "indigo" : "gold"} testId={`review-pack-share-status-${p.id}`}>{p.external_sharing_approved ? "Approved for External Sharing" : "Internal only — not approved for sharing"}</StatusBadge>
          <StatusBadge tone="neutral" testId={`review-pack-legal-status-${p.id}`}>Not legally approved</StatusBadge>
        </span>
      </div>
      {p.external_sharing_approved ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-av-muted">Approved for sharing by {p.sharing_approved_by} on {ET(p.sharing_approved_at)}.</span>
          <Button size="sm" variant="outline" onClick={() => download(p, "docx")} data-testid={`review-pack-docx-${p.id}`}>Download Word</Button>
          <Button size="sm" variant="outline" onClick={() => download(p, "pdf")} data-testid={`review-pack-pdf-${p.id}`}>Download PDF</Button>
        </div>
      ) : isSuper ? (
        <div className="space-y-2 rounded-xl bg-av-sand p-3" data-testid={`review-pack-approve-box-${p.id}`}>
          <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={ok1} onChange={(e) => setOk1(e.target.checked)} data-testid={`review-pack-confirm-${p.id}`} />
            <span>I approve this pack for sharing with AfroVending's reviewing attorney.</span></label>
          <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={ok2} onChange={(e) => setOk2(e.target.checked)} data-testid={`review-pack-ack-${p.id}`} />
            <span>I understand this is <b>not</b> legal approval. All policies stay Pending Legal Review.</span></label>
          <Button size="sm" variant={ok1 && ok2 ? "default" : "outline"} disabled={!ok1 || !ok2} onClick={approve} data-testid={`review-pack-approve-share-${p.id}`}>Approve for External Sharing</Button>
        </div>
      ) : <p className="text-xs text-av-muted">Waiting for the Super Admin to approve external sharing.</p>}
      <AttorneyRecords p={p} isSuper={isSuper} reload={reload} />
    </li>
  );
}

const SLUGS = [["terms", "Terms of Service"], ["privacy", "Privacy Policy"], ["vendor_agreement", "Vendor Agreement"], ["shipping", "Shipping & Delivery"],
  ["returns", "Returns & Refunds"], ["cookies", "Cookie Policy"], ["prohibited", "Prohibited Products"]];

function ChangeCreator({ pid, r }) {
  const [items, setItems] = useState(null);
  const start = () => setItems((r.requested_changes || "").split(/\n+/).map((s) => s.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, "").trim()).filter((s) => s.length >= 5)
    .map((description) => ({ description, policy_slug: "", clause: "" })).concat([]).slice(0, 50));
  const upd = (i, k, v) => setItems(items.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const save = () => {
    const ready = items.filter((x) => x.description.trim().length >= 5);
    if (!ready.length || ready.some((x) => !x.policy_slug)) { toast.error("Choose the affected policy for every item."); return; }
    api.post(`/admin/policies/review-pack/${pid}/attorney-review/${r.id}/changes`, { items: ready })
      .then((res) => { toast.success(`${res.data.data.length} checklist item(s) created`); setItems(null); setCreated(res.data.data.length); window.dispatchEvent(new Event("av:changes-updated")); })
      .catch((e) => toast.error(getErrorMessage(e)));
  };
  const [created, setCreated] = useState(r.changes_created || 0);
  if (created) return <p className="mt-2 text-xs text-av-muted" data-testid={`change-created-${r.id}`}>{created} checklist item(s) created from this feedback.</p>;
  if (!items) return <Button size="sm" variant="outline" className="ml-2 mt-2" onClick={start} data-testid={`change-create-${r.id}`}>Turn requested changes into checklist items</Button>;
  return (
    <div className="mt-3 space-y-2" data-testid={`change-creator-${r.id}`}>
      {items.map((x, i) => (
        <div key={i} className="grid gap-2 sm:grid-cols-[180px_90px_1fr]" data-testid={`change-draft-${i}`}>
          <select value={x.policy_slug} onChange={(e) => upd(i, "policy_slug", e.target.value)} className="h-9 rounded-md border border-av-line px-2" data-testid={`change-draft-policy-${i}`}>
            <option value="">Affected policy…</option>{SLUGS.map(([s, t]) => <option key={s} value={s}>{t}</option>)}
          </select>
          <Input placeholder="Clause" value={x.clause} onChange={(e) => upd(i, "clause", e.target.value)} className="h-9" data-testid={`change-draft-clause-${i}`} />
          <Input value={x.description} onChange={(e) => upd(i, "description", e.target.value)} className="h-9" data-testid={`change-draft-desc-${i}`} />
        </div>))}
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => setItems([...items, { description: "", policy_slug: "", clause: "" }])} data-testid="change-draft-add">Add item</Button>
        <Button size="sm" onClick={save} data-testid="change-draft-save">Create checklist items</Button>
        <Button size="sm" variant="outline" onClick={() => setItems(null)} data-testid="change-draft-cancel">Cancel</Button>
      </div>
    </div>
  );
}

function AttorneyRecords({ p, isSuper, reload }) {
  const [open, setOpen] = useState(false);
  const EMPTY = { reviewer_name: "", reviewer_firm: "", received_on: "", comments: "", recommendations: "", requested_changes: "" };
  const [f, setF] = useState(EMPTY);
  const [file, setFile] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = () => {
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => fd.append(k, v));
    if (file) fd.append("file", file);
    api.post(`/admin/policies/review-pack/${p.id}/attorney-review`, fd).then(() => { toast.success("Attorney review recorded"); setF(EMPTY); setFile(null); setOpen(false); reload(); }).catch((e) => toast.error(getErrorMessage(e)));
  };
  const getFile = (r) => api.get(`/admin/policies/review-pack/${p.id}/attorney-review/${r.id}/file`, { responseType: "blob" }).then((res) => {
    const url = URL.createObjectURL(res.data);
    Object.assign(document.createElement("a"), { href: url, download: r.filename }).click();
    URL.revokeObjectURL(url);
  }).catch((e) => toast.error(getErrorMessage(e)));
  return (
    <div className="space-y-2" data-testid={`attorney-records-${p.id}`}>
      {p.attorney_records.map((r) => (
        <div key={r.id} className="rounded-xl border border-av-line p-3 text-xs" data-testid={`attorney-record-${r.id}`}>
          <p className="font-semibold">Attorney feedback — {r.reviewer_name}{r.reviewer_firm && `, ${r.reviewer_firm}`} · received {r.received_on} · recorded by {r.recorded_by}</p>
          {r.comments && <p className="mt-1 whitespace-pre-wrap"><b>Comments:</b> {r.comments}</p>}
          {r.recommendations && <p className="mt-1 whitespace-pre-wrap"><b>Recommendations:</b> {r.recommendations}</p>}
          {r.requested_changes && <p className="mt-1 whitespace-pre-wrap"><b>Requested changes:</b> {r.requested_changes}</p>}
          {r.filename && <Button size="sm" variant="outline" className="mt-2" onClick={() => getFile(r)} data-testid={`attorney-file-${r.id}`}>Download {r.filename}</Button>}
          {isSuper && <ChangeCreator pid={p.id} r={r} />}
        </div>))}
      {isSuper && !open && <Button size="sm" variant="outline" className="h-auto whitespace-normal text-left" onClick={() => setOpen(true)} data-testid={`attorney-add-${p.id}`}>Record attorney feedback / upload reviewed document</Button>}
      {isSuper && open && (
        <div className="space-y-2 rounded-xl border border-av-line p-3" data-testid={`attorney-form-${p.id}`}>
          <p className="text-xs text-av-muted">Recording feedback doesn't approve or publish any policy. Each policy still needs its own legal approval and publication.</p>
          <div className="grid gap-2 sm:grid-cols-3">
            <Input placeholder="Attorney name" value={f.reviewer_name} onChange={set("reviewer_name")} data-testid="attorney-name" />
            <Input placeholder="Law firm (optional)" value={f.reviewer_firm} onChange={set("reviewer_firm")} data-testid="attorney-firm" />
            <label className="text-xs">Received on<Input type="date" value={f.received_on} onChange={set("received_on")} data-testid="attorney-received" /></label>
          </div>
          <Textarea placeholder="Comments" value={f.comments} onChange={set("comments")} data-testid="attorney-comments" />
          <Textarea placeholder="Recommendations" value={f.recommendations} onChange={set("recommendations")} data-testid="attorney-recommendations" />
          <Textarea placeholder="Requested changes" value={f.requested_changes} onChange={set("requested_changes")} data-testid="attorney-requested" />
          <input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => setFile(e.target.files?.[0] || null)} className="text-xs" data-testid="attorney-file-input" />
          <div className="flex gap-2"><Button size="sm" onClick={save} data-testid="attorney-save">Save record</Button><Button size="sm" variant="outline" onClick={() => setOpen(false)} data-testid="attorney-cancel">Cancel</Button></div>
        </div>
      )}
    </div>
  );
}
