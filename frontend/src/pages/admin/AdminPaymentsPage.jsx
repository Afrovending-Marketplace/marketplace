import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";
import { Statements } from "@/components/vendor/Statements";

const useList = (url) => {
  const [rows, setRows] = useState(null);
  const load = useCallback(() => api.get(url).then((r) => setRows(r.data.data ?? r.data)).catch(() => setRows([])), [url]);
  useEffect(() => {
    load();
  }, [load]);
  return [rows, load];
};
const act = async (fn, msg, after) => {
  try {
    await fn();
    if (msg) toast.success(msg);
    after?.();
  } catch (err) {
    toast.error(getErrorMessage(err));
  }
};
const Card = ({ title, children, testId }) => <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid={testId}><h2 className="text-xl font-semibold">{title}</h2>{children}</section>;

const Overview = () => {
  const [r, load] = useList("/admin/payments/reconciliation");
  if (!r) return null;
  const s = r.summary;
  return (
    <Card title="Reconciliation" testId="admin-pay-reconciliation">
      <StatusBadge tone={r.ok ? "success" : "danger"} testId="admin-pay-recon-status">{r.ok ? "Ledger reconciles" : `${r.issues.length} issue(s)`}</StatusBadge>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 text-sm">
        {[["Charged", s.gross_charged_minor], ["Stripe fees", s.processing_fees_minor], ["Net commission", s.commission_net_minor], ["Refunds", s.refunds_minor],
          ["Transfers", s.transfers_minor], ["Tax held", s.tax_held_minor], ["Vendor balances", s.vendor_balances_held_minor]].map(([l, v]) =>
          <div key={l} className="rounded-xl bg-av-sand p-3"><p className="text-xs text-av-muted">{l}</p><p className="font-bold" data-testid={`admin-pay-sum-${l.toLowerCase().replace(/ /g, "-")}`}>{formatPrice(v)}</p></div>)}
        <div className="rounded-xl bg-av-sand p-3"><p className="text-xs text-av-muted">Open disputes / webhook failures</p><p className="font-bold">{s.open_disputes} / {s.webhook_failures}</p></div>
      </div>
      {r.issues.map((i) => <p key={JSON.stringify(i)} className="text-xs text-red-700">{i.payment_id && `${i.payment_id}: `}{i.issue}</p>)}
      <Button size="sm" variant="outline" onClick={load} data-testid="admin-pay-recon-refresh">Refresh</Button>
    </Card>
  );
};

const Settings = () => {
  const [cfg, setCfg] = useState(null);
  const [rules, loadRules] = useList("/admin/payments/commission-rules");
  const [f, setF] = useState({ scope: "category", target: "", rate: "" });
  const [days, setDays] = useState("");
  useEffect(() => {
    api.get("/admin/payments/config").then((r) => { setCfg(r.data); setDays(String(r.data.hold_days)); });
  }, []);
  if (!cfg || !rules) return null;
  const active = rules.filter((x) => x.status === "active");
  const save = (scope, target, rate) => act(() => api.post("/admin/payments/commission-rules", { scope, target: target || null, rate_bps: Math.round(Number(rate) * 100) }), "Commission rule saved", loadRules);
  return (
    <div className="space-y-6">
      <Card title="Payout timing" testId="admin-pay-config">
        <p className="text-sm text-av-muted">Mode: <b data-testid="admin-pay-mode">{cfg.mode.toUpperCase()}</b> · Live payments: <b>{cfg.live_payments_enabled ? "enabled" : "disabled"}</b> · Countries: {cfg.allowed_countries.join(", ")} · {cfg.currencies.join(", ")}</p>
        <div className="flex gap-2"><Input className="h-9 w-32" value={days} onChange={(e) => setDays(e.target.value)} aria-label="Hold days" data-testid="admin-pay-hold-days" />
          <Button size="sm" onClick={() => act(() => api.put("/admin/payments/config", { hold_days: Number(days) }), "Hold period saved")} data-testid="admin-pay-hold-save">Save hold days</Button></div>
      </Card>
      <Card title="Commission rules" testId="admin-pay-commission">
        <p className="text-xs text-av-muted">Priority: vendor → category → marketplace default. Applies to items after discounts; never to shipping or tax. Changes don't alter past orders.</p>
        <ul className="divide-y divide-av-line text-sm">{active.map((x) => (
          <li key={x.id} className="flex items-center justify-between gap-3 py-2" data-testid={`admin-pay-rule-${x.scope}-${x.label}`}><span><b>{x.label}</b> ({x.scope}) · {x.rate_bps / 100}%</span>
            {x.scope !== "default" && <Button size="sm" variant="ghost" onClick={() => act(() => api.delete(`/admin/payments/commission-rules/${x.id}`), "Rule removed", loadRules)} data-testid={`admin-pay-rule-end-${x.id}`}>Remove</Button>}</li>))}</ul>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); save(f.scope, f.target, f.rate); }}>
          <select className="h-9 rounded-md border border-av-line bg-white px-2 text-sm" value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value })} data-testid="admin-pay-rule-scope">
            <option value="default">Marketplace default</option><option value="category">Category</option><option value="vendor">Vendor</option></select>
          {f.scope !== "default" && <Input className="h-9 w-48" placeholder={f.scope === "category" ? "Category slug" : "Vendor store slug"} value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} data-testid="admin-pay-rule-target" />}
          <Input className="h-9 w-28" placeholder="Rate %" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value })} data-testid="admin-pay-rule-rate" />
          <Button size="sm" type="submit" disabled={f.rate === ""} data-testid="admin-pay-rule-save">Save rule</Button>
        </form>
        <details className="text-xs text-av-muted"><summary>History</summary>{rules.filter((x) => x.status !== "active").map((x) => <p key={x.id}>{x.label} · {x.rate_bps / 100}% · {x.status} · {x.created_at?.slice(0, 10)}</p>)}</details>
      </Card>
    </div>
  );
};

const RefundForm = ({ vo, done }) => {
  const [qty, setQty] = useState({});
  const [ship, setShip] = useState(false);
  const [reason, setReason] = useState("");
  const submit = () => act(() => api.post(`/admin/payments/vendor-orders/${vo.id}/refunds`, {
    lines: Object.entries(qty).filter(([, q]) => Number(q) > 0).map(([order_item_id, q]) => ({ order_item_id, quantity: Number(q) })), include_shipping: ship, reason,
  }, { headers: { "Idempotency-Key": `rf-${crypto.randomUUID()}` } }), "Refund submitted", done);
  return (
    <div className="space-y-2 rounded-xl bg-av-sand p-3 text-xs" data-testid={`admin-refund-form-${vo.order_number}-${vo.vendor_slug}`}>
      {vo.items.map((i) => <label key={i.id} className="flex items-center gap-2">{i.title} ({i.quantity - i.refunded_qty} refundable)
        <Input className="h-8 w-16 bg-white" disabled={i.quantity === i.refunded_qty} value={qty[i.id] || ""} onChange={(e) => setQty({ ...qty, [i.id]: e.target.value })} data-testid={`admin-refund-qty-${i.sku}`} /></label>)}
      <label className="flex items-center gap-2"><input type="checkbox" checked={ship} onChange={(e) => setShip(e.target.checked)} data-testid="admin-refund-shipping" /> Refund shipping</label>
      <Input className="h-8 bg-white" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="admin-refund-reason" />
      <Button size="sm" onClick={submit} disabled={reason.trim().length < 3} data-testid="admin-refund-submit">Issue refund</Button>
    </div>
  );
};

const VendorOrders = () => {
  const [rows, load] = useList("/admin/payments/vendor-orders");
  const [open, setOpen] = useState(null);
  if (!rows) return null;
  return (
    <Card title="Vendor orders, refunds & holds" testId="admin-pay-vendor-orders">
      {rows.length === 0 && <p className="text-sm text-av-muted">No paid orders yet.</p>}
      <ul className="divide-y divide-av-line text-sm">{rows.map((v) => {
        const holds = v.holds.filter((h) => h.active);
        return (
          <li key={v.id} className="space-y-2 py-3" data-testid={`admin-vo-${v.order_number}-${v.vendor_slug}`}>
            <div className="flex flex-wrap items-center gap-2"><b>{v.order_number}</b> · {v.vendor_name} · charged {formatPrice(v.charged_minor)} · commission {formatPrice(v.commission_minor)} ·
              fee {v.fee_minor == null ? "pending" : formatPrice(v.fee_minor)} · refunded {formatPrice(v.refunded_minor)}
              <StatusBadge tone={holds.length ? "danger" : "neutral"}>{holds.length ? "on hold" : v.earning_status}</StatusBadge></div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={v.refunded_minor >= v.charged_minor} onClick={() => setOpen(open === v.id ? null : v.id)} data-testid={`admin-vo-refund-toggle-${v.id}`}>Refund</Button>
              {["pending", "releasing"].includes(v.earning_status) && <Button size="sm" variant="outline" onClick={() => act(() => api.post(`/admin/payments/vendor-orders/${v.id}/holds`, { type: "admin", reason: "Admin review" }), "Hold placed", load)} data-testid={`admin-vo-hold-${v.id}`}>Place hold</Button>}
              {holds.map((h) => <Button key={h.id} size="sm" variant="ghost" onClick={() => act(() => api.post(`/admin/payments/vendor-orders/${v.id}/holds/${h.id}/release`), "Hold released", load)} data-testid={`admin-vo-release-hold-${h.id}`}>Release {h.type} hold</Button>)}
            </div>
            {open === v.id && <RefundForm vo={v} done={() => { setOpen(null); load(); }} />}
          </li>
        );
      })}</ul>
    </Card>
  );
};

const Disputes = () => {
  const [rows, load] = useList("/admin/payments/disputes");
  const [vos] = useList("/admin/payments/vendor-orders");
  const [amt, setAmt] = useState({});
  if (!rows || !vos) return null;
  const attribute = (d) => act(() => api.post(`/admin/payments/disputes/${d.id}/attribute`, {
    attributions: vos.filter((v) => v.payment_id === d.payment_id).map((v) => ({ vendor_order_id: v.id, amount_minor: Math.round(Number(amt[v.id] || 0) * 100), vendor_liable: Number(amt[v.id] || 0) > 0 })),
  }), "Responsibility saved", load);
  return (
    <Card title="Disputes" testId="admin-pay-disputes">
      {rows.length === 0 && <p className="text-sm text-av-muted">No disputes.</p>}
      {rows.map((d) => (
        <div key={d.id} className="space-y-2 border-t border-av-line pt-3 text-sm" data-testid={`admin-dispute-${d.id}`}>
          <p><b>{formatPrice(d.amount_minor)}</b> · {d.reason} · <StatusBadge tone={d.status === "lost" ? "danger" : d.status === "won" ? "success" : "gold"}>{d.status}</StatusBadge>
            {d.applied && " · adjustments recorded"}</p>
          {d.vendor_evidence.map((e) => <p key={e.at} className="rounded bg-av-sand p-2 text-xs">Vendor evidence: {e.text}</p>)}
          {!d.applied && <div className="flex flex-wrap items-center gap-2">{vos.filter((v) => v.payment_id === d.payment_id).map((v) => (
            <label key={v.id} className="flex items-center gap-1 text-xs">{v.vendor_name} liable $<Input className="h-8 w-24" value={amt[v.id] || ""} onChange={(e) => setAmt({ ...amt, [v.id]: e.target.value })} data-testid={`admin-dispute-amount-${v.vendor_slug}`} /></label>))}
            <Button size="sm" onClick={() => attribute(d)} data-testid={`admin-dispute-attribute-${d.id}`}>Save responsibility</Button></div>}
        </div>
      ))}
    </Card>
  );
};

const Payouts = () => {
  const [rows, load] = useList("/admin/payments/payouts");
  if (!rows) return null;
  return (
    <Card title="Payouts" testId="admin-pay-payouts">
      <Button size="sm" onClick={() => act(() => api.post("/admin/payments/payouts/release", {}), "Release run complete", load)} data-testid="admin-pay-release-all">Release eligible earnings now</Button>
      <ul className="divide-y divide-av-line text-sm">{rows.map((p) => (
        <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2" data-testid={`admin-payout-${p.id}`}>
          <span>{p.order_number} · {formatPrice(p.amount_minor)} · {p.status}{p.simulated && " · SIMULATED"}</span>
          {p.simulated && p.status === "transferred" && <Button size="sm" variant="ghost" onClick={() => act(() => api.post(`/admin/payments/payouts/${p.id}/simulate-paid`), "Marked paid (simulated)", load)} data-testid={`admin-payout-sim-paid-${p.id}`}>Simulate bank payout</Button>}
        </li>))}</ul>
    </Card>
  );
};

export default function AdminPaymentsPage() {
  return (
    <div data-testid="admin-payments-page" className="av-container max-w-6xl space-y-6 py-12">
      <h1 className="text-4xl font-bold tracking-tight text-av-ink">Payments & commission</h1>
      <StatusAlert tone="info" title="Sandbox only" testId="admin-pay-sandbox">Stripe test mode. Live payments, transfers and dispute adjustments stay disabled until you approve go-live. Vendor payout accounts are simulated until Stripe Connect is enabled on the claimed account.</StatusAlert>
      <Tabs defaultValue="overview">
        <TabsList className="h-auto flex-wrap justify-start"><TabsTrigger value="overview" data-testid="admin-pay-tab-overview">Overview</TabsTrigger><TabsTrigger value="settings" data-testid="admin-pay-tab-settings">Commission & timing</TabsTrigger>
          <TabsTrigger value="orders" data-testid="admin-pay-tab-orders">Orders & refunds</TabsTrigger><TabsTrigger value="disputes" data-testid="admin-pay-tab-disputes">Disputes</TabsTrigger>
          <TabsTrigger value="payouts" data-testid="admin-pay-tab-payouts">Payouts</TabsTrigger><TabsTrigger value="statements" data-testid="admin-pay-tab-statements">Statements</TabsTrigger></TabsList>
        <TabsContent value="overview"><Overview /></TabsContent><TabsContent value="settings"><Settings /></TabsContent>
        <TabsContent value="orders"><VendorOrders /></TabsContent><TabsContent value="disputes"><Disputes /></TabsContent><TabsContent value="payouts"><Payouts /></TabsContent>
        <TabsContent value="statements"><Statements listUrl="/admin/payments/statements" fileUrl={(s) => `/admin/payments/statements/${s.vendor_id}/${s.period}`} testId="admin-statements" /></TabsContent>
      </Tabs>
    </div>
  );
}
