import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";

const NY = (s) => (s ? new Date(s).toLocaleString("en-US", { timeZone: "America/New_York", dateStyle: "medium", timeStyle: "short" }) + " ET" : "—");
const TONE = { ok: "success", degraded: "gold", down: "danger", open: "danger", acknowledged: "gold", resolved: "success", critical: "danger", error: "gold", warning: "neutral" };

function Health({ h, reload }) {
  const run = () => api.post("/admin/ops/health/run").then(() => { toast.success("Health check complete"); reload(); }).catch((e) => toast.error(getErrorMessage(e)));
  const comps = h.latest?.components || {};
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="ops-health">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Application health {h.latest && <StatusBadge tone={TONE[h.latest.status]} testId="ops-health-status">{h.latest.status}</StatusBadge>}</h2>
        <Button size="sm" onClick={run} data-testid="ops-health-run">Run check now</Button>
      </div>
      <p className="text-xs text-av-muted">Last check: {NY(h.latest?.at)} · automatic every 15 minutes · alerts go to {h.alert_email}</p>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(comps).map(([k, c]) => (
        <li key={k} className="rounded-xl bg-av-sand p-3 text-sm" data-testid={`ops-comp-${k}`}>
          <div className="flex items-center justify-between gap-2"><b>{k.replace(/_/g, " ")}</b><StatusBadge tone={TONE[c.status]}>{c.status}</StatusBadge></div>
          <p className="mt-1 break-words text-xs text-av-muted">{Object.entries(c).filter(([x]) => x !== "status").map(([x, v]) => `${x.replace(/_/g, " ")}: ${Array.isArray(v) ? v.join(", ") || "none" : v}`).join(" · ")}</p>
        </li>))}</ul>
      <h3 className="pt-2 text-sm font-semibold">Recent incidents</h3>
      {h.incidents.length === 0 ? <p className="text-sm text-av-muted" data-testid="ops-incidents-empty">No incidents recorded.</p> : (
        <ul className="divide-y divide-av-line text-sm">{h.incidents.map((i) => (
          <li key={i.id} className="flex flex-wrap justify-between gap-2 py-2" data-testid={`ops-incident-${i.id}`}>
            <span><b>{i.component.replace(/_/g, " ")}</b> · {i.severity} · opened {NY(i.opened_at)}{i.resolved_at && ` · recovered ${NY(i.resolved_at)} (${Math.round(i.duration_s / 60)} min)`}</span>
            <StatusBadge tone={TONE[i.status]}>{i.status}</StatusBadge>
          </li>))}</ul>)}
    </section>
  );
}

function ErrorRow({ e, reload }) {
  const set = (status) => api.put(`/admin/ops/errors/${e.id}`, { status }).then(() => { toast.success(`Marked ${status}`); reload(); }).catch((x) => toast.error(getErrorMessage(x)));
  return (
    <li className="space-y-1 py-3 text-sm" data-testid={`ops-error-${e.id}`}>
      <div className="flex flex-wrap items-center gap-2"><StatusBadge tone={TONE[e.severity]}>{e.severity}</StatusBadge><b>{e.service}</b><span className="break-all">{e.kind}</span><StatusBadge tone={TONE[e.status]} testId={`ops-error-status-${e.id}`}>{e.status}</StatusBadge></div>
      <p className="break-words text-av-ink">{e.message}</p>
      <p className="text-xs text-av-muted">{e.count}× · first {NY(e.first_at)} · last {NY(e.last_at)}{e.last_request_id && ` · request ${e.last_request_id}`}</p>
      <div className="flex gap-2">
        {e.status !== "acknowledged" && e.status !== "resolved" && <Button size="sm" variant="outline" onClick={() => set("acknowledged")} data-testid={`ops-error-ack-${e.id}`}>Acknowledge</Button>}
        {e.status !== "resolved" && <Button size="sm" variant="outline" onClick={() => set("resolved")} data-testid={`ops-error-resolve-${e.id}`}>Resolve</Button>}
      </div>
    </li>
  );
}

const Sel = ({ value, onChange, options, label, testId }) => (
  <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label} className="h-9 rounded-md border border-av-line px-2 text-sm" data-testid={testId}>
    <option value="">All {label.toLowerCase()}</option>{options.map((o) => <option key={o} value={o}>{o}</option>)}
  </select>
);

function Errors() {
  const [f, setF] = useState({ service: "", severity: "", status: "", since: "" });
  const [d, setD] = useState(null);
  const load = useCallback(() => {
    const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v).map(([k, v]) => [k, k === "since" ? new Date(v).toISOString() : v]));
    api.get("/admin/ops/errors", { params }).then((r) => setD(r.data)).catch((e) => toast.error(getErrorMessage(e)));
  }, [f]);
  useEffect(() => { load(); }, [load]);
  const upd = (k) => (v) => setF((x) => ({ ...x, [k]: v }));
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="ops-errors">
      <h2 className="font-semibold">Production error monitoring</h2>
      <div className="flex flex-wrap gap-2">
        <Sel value={f.service} onChange={upd("service")} options={d?.services || []} label="Services" testId="ops-filter-service" />
        <Sel value={f.severity} onChange={upd("severity")} options={["critical", "error", "warning"]} label="Severities" testId="ops-filter-severity" />
        <Sel value={f.status} onChange={upd("status")} options={["open", "acknowledged", "resolved"]} label="Statuses" testId="ops-filter-status" />
        <Input type="date" value={f.since} onChange={(e) => upd("since")(e.target.value)} className="h-9 w-40" aria-label="Since date" data-testid="ops-filter-since" />
      </div>
      {!d ? null : d.data.length === 0 ? <p className="text-sm text-av-muted" data-testid="ops-errors-empty">No errors match.</p> : (
        <ul className="divide-y divide-av-line">{d.data.map((e) => <ErrorRow key={e.id} e={e} reload={load} />)}</ul>)}
    </section>
  );
}

function EmailLog() {
  const [status, setStatus] = useState("");
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/admin/ops/emails", { params: status ? { status } : {} }).then((r) => setD(r.data)).catch((e) => toast.error(getErrorMessage(e))); }, [status]);
  if (!d) return null;
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="ops-emails">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Email deliveries</h2>
        <Sel value={status} onChange={setStatus} options={["failed", "bounced", "complained", "delayed", "sent", "delivered"]} label="Statuses" testId="ops-emails-filter" />
      </div>
      <p className="text-xs text-av-muted" data-testid="ops-emails-state">Sending {d.sending_enabled ? "enabled" : "disabled"} · Resend key {d.provider_configured ? "configured" : "missing"}</p>
      {d.data.length === 0 ? <p className="text-sm text-av-muted" data-testid="ops-emails-empty">No email deliveries match.</p> : (
        <ul className="divide-y divide-av-line text-sm">{d.data.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2" data-testid={`ops-email-${m.id}`}>
            <span className="break-words"><b>{m.category}</b> · {m.subject} · {m.to_masked} · {m.attempts}× · {NY(m.updated_at)}{m.error && ` · ${m.error}`}</span>
            <StatusBadge tone={["sent", "delivered"].includes(m.status) ? "success" : m.status === "delayed" ? "gold" : "danger"}>{m.status}</StatusBadge>
          </li>))}</ul>)}
    </section>
  );
}

function AlertConfig() {
  const [c, setC] = useState(null);
  useEffect(() => { api.get("/admin/ops/config").then((r) => setC(r.data)).catch(() => {}); }, []);
  if (!c) return null;
  const save = () => api.put("/admin/ops/config", { error_threshold: Number(c.error_threshold), window_minutes: Number(c.window_minutes), cooldown_minutes: Number(c.cooldown_minutes) })
    .then((r) => { setC(r.data); toast.success("Alert settings saved"); }).catch((e) => toast.error(getErrorMessage(e)));
  const field = (k, label) => <label className="text-xs">{label}<Input type="number" value={c[k]} onChange={(e) => setC({ ...c, [k]: e.target.value })} className="mt-1 h-9 w-28" data-testid={`ops-config-${k}`} /></label>;
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="ops-config">
      <h2 className="font-semibold">Alert settings</h2>
      <div className="flex flex-wrap items-end gap-3">{field("error_threshold", "Server errors")}{field("window_minutes", "Within (minutes)")}{field("cooldown_minutes", "Repeat alert after (minutes)")}
        <Button size="sm" onClick={save} data-testid="ops-config-save">Save</Button></div>
    </section>
  );
}

export default function AdminOpsPage() {
  const [h, setH] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.get("/admin/ops/health").then((r) => setH(r.data)).catch((e) => setErr(getErrorMessage(e))), []);
  useEffect(() => { load(); }, [load]);
  if (err) return <p className="av-container py-12" data-testid="ops-error">{err}</p>;
  if (!h) return null;
  return (
    <div className="av-container max-w-5xl space-y-6 py-12" data-testid="admin-ops-page">
      <div><p className="av-eyebrow">Super Admin</p><h1 className="mt-2 text-4xl font-bold text-av-ink">Operations</h1>
        <p className="mt-1 text-sm text-av-muted">Times shown in US Eastern (America/New_York). Logs are kept 30 days.</p></div>
      <Health h={h} reload={load} />
      <Errors />
      <EmailLog />
      <AlertConfig />
    </div>
  );
}
