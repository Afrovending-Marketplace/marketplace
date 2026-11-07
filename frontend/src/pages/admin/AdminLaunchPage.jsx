import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FoundingBadge } from "@/components/commerce/FoundingBadge";
import { api, getErrorMessage } from "@/lib/api";

const TONE = { verified: "success", blocked: "danger", in_progress: "gold", not_started: "neutral" };
const LABEL = { verified: "Verified", blocked: "Blocked", in_progress: "In progress", not_started: "Not started" };
const when = (s) => (s ? new Date(s).toLocaleString() : "—");

function Item({ it, canEdit, onSaved }) {
  const [status, setStatus] = useState(it.status);
  const [evidence, setEvidence] = useState(it.evidence);
  const [busy, setBusy] = useState(false);
  const act = async (fn) => {
    setBusy(true);
    try { onSaved((await fn()).data); toast.success("Checklist updated"); } catch (e) { toast.error(getErrorMessage(e)); } finally { setBusy(false); }
  };
  const statuses = Object.keys(LABEL).filter((s) => it.mode !== "auto" || s !== "verified");
  return (
    <li className="space-y-2 rounded-2xl border border-av-line bg-white p-4" data-testid={`launch-item-${it.key}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold text-av-ink">{it.label}</p>
        <StatusBadge tone={TONE[it.status]} testId={`launch-status-${it.key}`}>{LABEL[it.status]}</StatusBadge>
      </div>
      <p className="text-xs text-av-muted">{it.mode === "auto" ? "Automatic check" : it.mode === "final" ? "Super Admin only, after every item is verified" : "Manual verification with evidence"}
        {it.verified_at && ` · Verified ${when(it.verified_at)} by ${it.verified_by}`}{!it.verified_at && it.updated_at && ` · Updated ${when(it.updated_at)} by ${it.updated_by}`}</p>
      {it.evidence && <p className="break-words rounded-lg bg-av-sand p-2 text-xs" data-testid={`launch-evidence-${it.key}`}>{it.evidence}</p>}
      {it.note && <p className="text-xs text-av-clay">{it.note}</p>}
      {canEdit && (
        <div className="flex flex-wrap items-end gap-2">
          {it.mode === "auto" && <Button size="sm" disabled={busy} onClick={() => act(() => api.post(`/admin/launch/checklist/${it.key}/check`))} data-testid={`launch-check-${it.key}`}>Run check</Button>}
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 rounded-md border border-av-line px-2 text-sm" aria-label={`Status for ${it.label}`} data-testid={`launch-select-${it.key}`}>
            {statuses.map((s) => <option key={s} value={s}>{LABEL[s]}</option>)}
          </select>
          <Textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="Evidence: link, screenshot reference, test report, ticket…" className="min-h-[38px] flex-1 min-w-[220px] text-sm" aria-label={`Evidence for ${it.label}`} data-testid={`launch-evidence-input-${it.key}`} />
          <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => api.put(`/admin/launch/checklist/${it.key}`, { status, evidence }))} data-testid={`launch-save-${it.key}`}>Save</Button>
        </div>
      )}
    </li>
  );
}

function LaunchRecord({ data, reload }) {
  const [confirm, setConfirm] = useState("");
  const [reason, setReason] = useState("");
  const save = () => api.post("/admin/launch/public-launch", { confirm, reason }).then(() => { toast.success("Public launch recorded"); reload(); }).catch((e) => toast.error(getErrorMessage(e)));
  return (
    <section className="space-y-2 rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid="launch-record">
      <h2 className="font-semibold">Official public launch date</h2>
      <p className="text-av-muted">{data.public_launch ? `Recorded: ${when(data.public_launch.launched_at)} by ${data.public_launch.recorded_by}` : "Not recorded. Record it only after the approved cutover; it starts the 30-day Founding Vendor window and changes nothing else."}</p>
      {data.is_super_admin && (
        <div className="flex flex-wrap gap-2">
          <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Type RECORD PUBLIC LAUNCH" className="max-w-xs" data-testid="launch-record-confirm" />
          {data.public_launch && <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason for correction" className="max-w-xs" data-testid="launch-record-reason" />}
          <Button size="sm" onClick={save} data-testid="launch-record-button">Record launch (now)</Button>
        </div>
      )}
    </section>
  );
}

function FoundingReview() {
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/admin/founding-vendors").then((r) => setD(r.data)).catch(() => setD(null)), []);
  useEffect(() => { load(); }, [load]);
  if (!d) return null;
  const fix = (v, value) => {
    const reason = window.prompt("Reason for this correction (logged):");
    if (reason) api.put(`/admin/founding-vendors/${v.vendor_id}`, { value, reason }).then(load).catch((e) => toast.error(getErrorMessage(e)));
  };
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid="founding-review">
      <div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold">Founding Vendor review</h2><FoundingBadge testId="founding-review-badge" /></div>
      <p className="text-xs text-av-muted">Approved and active vendors approved within 30 days after the recorded launch ({d.launched_at ? `${when(d.launched_at)} → ${when(d.window_ends_at)}` : "launch not recorded"}). Badge only: no fee, ranking or placement benefit.</p>
      {d.vendors.length === 0 ? <p data-testid="founding-empty">No vendors yet.</p> : (
        <ul className="divide-y divide-av-line">{d.vendors.map((v) => (
          <li key={v.vendor_id} className="flex flex-wrap items-center justify-between gap-2 py-2" data-testid={`founding-row-${v.slug}`}>
            <span><b>{v.name}</b> · {v.status} · approved {when(v.approved_at)}<br /><span className="text-xs text-av-muted">{v.eligible ? "Eligible" : "Not eligible"}: {v.reason}</span></span>
            <span className="flex gap-1">
              <Button size="sm" variant="outline" onClick={() => fix(v, true)} data-testid={`founding-grant-${v.slug}`}>Grant</Button>
              <Button size="sm" variant="outline" onClick={() => fix(v, false)} data-testid={`founding-revoke-${v.slug}`}>Remove</Button>
              {v.override && <Button size="sm" variant="ghost" onClick={() => fix(v, null)} data-testid={`founding-reset-${v.slug}`}>Clear</Button>}
            </span>
          </li>))}</ul>)}
    </section>
  );
}

export default function AdminLaunchPage() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.get("/admin/launch/checklist").then((r) => setD(r.data)).catch((e) => setErr(getErrorMessage(e))), []);
  useEffect(() => { load(); }, [load]);
  if (err) return <p className="av-container py-12" data-testid="launch-error">{err}</p>;
  if (!d) return null;
  return (
    <div className="av-container max-w-5xl space-y-6 py-12" data-testid="admin-launch-page">
      <div><p className="av-eyebrow">Phase 14 · clean launch</p><h1 className="mt-2 text-4xl font-bold text-av-ink">Launch readiness</h1>
        <p className="mt-1 text-sm text-av-muted" data-testid="launch-progress">{d.verified} of {d.total} verified. {d.safety} Cutover and live payments need separate explicit approval.</p></div>
      <ol className="space-y-3">{d.items.map((it) => <Item key={`${it.key}-${it.updated_at}`} it={it} canEdit={d.can_edit.includes(it.key)} onSaved={() => load()} />)}</ol>
      <LaunchRecord data={d} reload={load} />
      {d.is_super_admin && <FoundingReview />}
    </div>
  );
}
