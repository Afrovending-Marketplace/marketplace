import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/common/StatusBadge";
import { download } from "@/components/vendor/Statements";
import { api, getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

const LINKS = [["vendors.manage", "/admin/vendors", "Vendors & applications"], ["catalog.moderate", "/admin/products", "Product moderation"],
  ["catalog.moderate", "/admin/categories", "Categories"], ["commerce.manage", "/admin/commerce", "Shipping & tax"], ["orders.manage", "/admin/fulfillment", "Orders, cancellations & returns"],
  ["finance.view", "/admin/payments", "Payments, refunds, disputes & payouts"], ["tickets.manage", "/admin/tickets", "Support tickets"], ["content.manage", "/admin/content", "Homepage & banners"],
  ["admins.manage", "/admin/team", "Admin team & invites"], ["catalog.moderate", "/admin/search-insights", "Search insights"]];
const EXPORTS = [["orders", "finance.export"], ["ledger", "finance.export"], ["payouts", "finance.export"], ["refunds", "finance.export"], ["vendors", "ops.export"], ["tickets", "tickets.manage"], ["customers", "customers.export"]];

export default function AdminHomePage() {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.get("/admin/overview").then((r) => setD(r.data)).catch((e) => toast.error(getErrorMessage(e)));
  }, []);
  if (!d) return null;
  const has = (p) => d.permissions.includes(p);
  const Stat = ({ k, v }) => <div className="rounded-xl bg-av-sand p-3" data-testid={`ov-${k}`}><p className="text-xs text-av-muted">{k.replace(/_/g, " ")}</p><p className="text-xl font-bold">{k.endsWith("_minor") ? formatPrice(v) : v}</p></div>;
  return (
    <div className="av-container max-w-6xl space-y-6 py-12" data-testid="admin-home">
      <div><p className="av-eyebrow">Marketplace administration</p><h1 className="mt-2 text-4xl font-bold text-av-ink">Admin dashboard</h1>
        <p className="mt-1 text-xs text-av-muted" data-testid="admin-roles">Signed in as: {d.roles.join(", ").replace(/_/g, " ")}</p></div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">{LINKS.filter(([p]) => has(p)).map(([, to, n]) => <Button key={to} asChild variant="outline" className="justify-start"><Link to={to} data-testid={`admin-link-${to.split("/").pop()}`}>{n}</Link></Button>)}</div>
      {d.operations && <section className="grid grid-cols-2 gap-2 lg:grid-cols-4" data-testid="ov-operations">{Object.entries(d.operations).map(([k, v]) => <Stat key={k} k={k} v={v} />)}</section>}
      {d.tickets && <section className="grid grid-cols-3 gap-2" data-testid="ov-tickets">{Object.entries(d.tickets).map(([k, v]) => <Stat key={k} k={`${k}_tickets_open`} v={v} />)}</section>}
      {d.finance && <section className="space-y-2" data-testid="ov-finance"><p className="text-xs text-av-muted">Finance · {d.finance.period}</p>
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-5"><Stat k="gross_payments_minor" v={d.finance.gross_payments_minor} /><Stat k="payments" v={d.finance.payments} />
          <Stat k="refunds_pending" v={d.finance.refunds_pending} /><Stat k="disputes_open" v={d.finance.disputes_open} /><Stat k="approvals_pending" v={d.finance.approvals_pending} /></div></section>}
      <section className="space-y-2 rounded-2xl border border-av-line bg-white p-5" data-testid="admin-exports"><h2 className="font-semibold">Exports (CSV, last 30 days, US Eastern)</h2>
        <div className="flex flex-wrap gap-2">{EXPORTS.filter(([, p]) => has(p)).map(([k]) => <Button key={k} size="sm" variant="outline" onClick={() => download(`/admin/exports/${k}.csv`, `afrovending-${k}.csv`)} data-testid={`export-${k}`}>{k}</Button>)}</div></section>
      {d.recent_audit && <section className="rounded-2xl border border-av-line bg-white p-5 text-xs" data-testid="admin-audit"><h2 className="mb-2 text-sm font-semibold">Recent audit log (read-only)</h2>
        {d.recent_audit.map((a, i) => <p key={i}>{new Date(a.created_at).toLocaleString()} · {a.actor_role} · {a.action}</p>)}</section>}
    </div>
  );
}

export function AdminTeamPage() {
  const [d, setD] = useState(null);
  const [f, setF] = useState({ role: "support_admin" });
  const load = useCallback(() => api.get("/admin/team").then((r) => setD(r.data)), []);
  useEffect(() => {
    load();
  }, [load]);
  const act = async (fn, msg) => {
    try {
      const r = await fn();
      toast.success(msg);
      if (r?.data?.invite_link) window.prompt("Email couldn't be sent. Copy this one-time invite link:", r.data.invite_link);
      load();
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  };
  const confirm = (label) => {
    const password = window.prompt(`Confirm your password to ${label}`);
    return password ? { password, reason: window.prompt("Reason (recorded in the audit log)") || "No reason given" } : null;
  };
  if (!d) return null;
  const ROLES = ["super_admin", "marketplace_admin", "finance_admin", "support_admin", "content_admin"];
  return (
    <div className="av-container max-w-5xl space-y-6 py-12" data-testid="admin-team">
      <h1 className="text-3xl font-bold text-av-ink">Admin team</h1>
      <section className="flex flex-wrap gap-2 rounded-2xl border border-av-line bg-white p-5">
        <Input className="w-64" placeholder="Email" value={f.email || ""} onChange={(e) => setF({ ...f, email: e.target.value })} data-testid="invite-email" />
        <select className="h-10 rounded border border-av-line px-2 text-sm" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} data-testid="invite-role">{ROLES.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}</select>
        <Button onClick={() => act(() => api.post("/admin/team/invites", f), "Invite sent")} data-testid="invite-send">Send invite</Button>
      </section>
      <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white px-5 text-sm">{d.admins.map((a) => (
        <li key={a.id} className="flex flex-wrap items-center gap-2 py-3" data-testid={`team-${a.id}`}><b>{a.name}</b> {a.email} · {a.roles.join(", ")}
          <StatusBadge tone={a.status === "active" ? "success" : "danger"}>{a.status}</StatusBadge>{!a.mfa_enrolled && <StatusBadge tone="gold">no MFA yet</StatusBadge>}
          <select className="h-8 rounded border border-av-line px-1 text-xs" value="" onChange={(e) => { const c = confirm("change this role"); if (c) act(() => api.put(`/admin/team/${a.id}/role`, { role: e.target.value, ...c }), "Role changed"); }} data-testid={`team-role-${a.id}`}>
            <option value="">Change role…</option>{ROLES.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}</select>
          {["suspend", "reactivate", "revoke"].map((x) => <Button key={x} size="sm" variant="ghost" onClick={() => { const c = confirm(x); if (c) act(() => api.post(`/admin/team/${a.id}/${x}`, c), `Access ${x}d`); }} data-testid={`team-${x}-${a.id}`}>{x}</Button>)}</li>))}</ul>
      {d.invites.length > 0 && <ul className="text-sm" data-testid="team-invites">{d.invites.map((i) => <li key={i.id}>{i.email} · {i.role} · expires {new Date(i.expires_at).toLocaleString()}
        <Button size="sm" variant="ghost" onClick={() => act(() => api.delete(`/admin/team/invites/${i.id}`), "Invite revoked")} data-testid={`invite-revoke-${i.id}`}>Revoke</Button></li>)}</ul>}
    </div>
  );
}

export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const [f, setF] = useState({});
  const [done, setDone] = useState(null);
  const go = async () => {
    try {
      setDone((await api.post("/auth/admin-invite/accept", { token: params.get("token"), ...f })).data);
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  };
  return (
    <div className="av-container max-w-md space-y-4 py-16" data-testid="accept-invite">
      <h1 className="text-3xl font-bold text-av-ink">Join the AfroVending admin team</h1>
      {done ? <p data-testid="invite-accepted">You're now a {done.role.replace(/_/g, " ")}. <Link className="underline" to="/login?next=/admin">Sign in</Link> and set up two-step sign-in.</p> : <>
        <p className="text-sm text-av-muted">New to AfroVending? Choose your name and a strong password. Already have an account? Sign in first, then open the invite link again.</p>
        <Input placeholder="Your name" value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="invite-name" />
        <Input type="password" placeholder="Password (12+ characters)" value={f.password || ""} onChange={(e) => setF({ ...f, password: e.target.value })} data-testid="invite-password" />
        <Button onClick={go} data-testid="invite-accept">Accept invite</Button></>}
    </div>
  );
}
