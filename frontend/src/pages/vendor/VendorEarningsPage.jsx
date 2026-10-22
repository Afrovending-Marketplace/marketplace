import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

const BUCKETS = [["pending_minor", "Pending"], ["eligible_minor", "Eligible"], ["held_minor", "On hold"], ["transferred_minor", "Transferred"],
  ["paid_minor", "Paid to bank"], ["owed_minor", "Owed to AfroVending"]];

const PayoutAccount = ({ account, reload }) => {
  const run = async (fn) => {
    try {
      const r = await fn();
      if (r.data.url) window.location.assign(r.data.url);
      reload();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  const ready = account?.transfers_enabled && account?.payouts_enabled;
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="vendor-payout-account">
      <div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-semibold">Payout account</h2>
        {account?.simulated && <StatusBadge tone="neutral" testId="payout-account-simulated">SIMULATED</StatusBadge>}
        <StatusBadge tone={ready ? "success" : "gold"} testId="payout-account-status">{ready ? "Ready for payouts" : account ? "Verification incomplete" : "Not set up"}</StatusBadge></div>
      <p className="text-sm text-av-muted">Payouts go through Stripe Connect (US vendors, USD). {account?.simulated && "Stripe Connect isn't enabled on AfroVending's test account yet, so this is a simulated test account — no real money moves."}</p>
      {!account && <Button onClick={() => run(() => api.post("/vendor/payments/onboarding", { country: "US" }))} data-testid="payout-onboard-button">Set up payouts (US)</Button>}
      {account && !ready && account.simulated && <Button onClick={() => run(() => api.post("/vendor/payments/onboarding/simulate-complete"))} data-testid="payout-simulate-verify">Complete simulated verification</Button>}
      {account && !ready && !account.simulated && <Button onClick={() => run(() => api.post("/vendor/payments/onboarding", { country: "US" }))} data-testid="payout-continue-onboarding">Continue Stripe onboarding</Button>}
    </section>
  );
};

const Evidence = ({ d, reload }) => {
  const [text, setText] = useState("");
  const send = async () => {
    try {
      await api.post(`/vendor/payments/disputes/${d.id}/evidence`, { text });
      setText("");
      toast.success("Evidence submitted");
      reload();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <li className="space-y-2 py-3 text-sm" data-testid={`vendor-dispute-${d.id}`}>
      <p><b>{formatPrice(d.amount_minor)}</b> · {d.reason} · <StatusBadge tone={d.status === "won" ? "success" : d.status === "lost" ? "danger" : "gold"}>{d.status}</StatusBadge>
        {d.evidence_due_by && ` · evidence due ${new Date(d.evidence_due_by * 1000).toLocaleDateString()}`}</p>
      {d.my_evidence.map((e) => <p key={e} className="rounded bg-av-sand p-2 text-xs">{e}</p>)}
      {!["won", "lost"].includes(d.status) && <div className="flex gap-2"><Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Tracking number, delivery proof, customer messages…" className="bg-white" data-testid={`vendor-dispute-evidence-${d.id}`} />
        <Button size="sm" onClick={send} disabled={text.trim().length < 10} data-testid={`vendor-dispute-submit-${d.id}`}>Submit</Button></div>}
    </li>
  );
};

const Breakdown = ({ v }) => (
  <tr className="border-t border-av-line" data-testid={`vendor-earning-row-${v.order_number}`}>
    <td className="py-2 pr-3 font-semibold">{v.order_number}</td>
    <td className="pr-3">{formatPrice(v.items_net_minor)}</td><td className="pr-3">{formatPrice(v.shipping_minor)}</td>
    <td className="pr-3">−{formatPrice(v.commission_minor - v.commission_refunded_minor)}</td>
    <td className="pr-3">{v.fee_minor == null ? "pending" : `−${formatPrice(v.fee_minor)}`}</td>
    <td className="pr-3">{v.refunded_minor ? `−${formatPrice(v.items_refunded_minor + v.shipping_refunded_minor)}` : "—"}</td>
    <td className="pr-3 font-semibold" data-testid={`vendor-earning-net-${v.order_number}`}>{formatPrice(v.earned_net_minor)}</td>
    <td><StatusBadge tone={v.on_hold ? "danger" : v.earning_status === "pending" ? "gold" : "success"}>{v.on_hold ? "on hold" : v.earning_status}</StatusBadge></td>
  </tr>
);

export default function VendorEarningsPage() {
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/vendor/payments/summary").then((r) => setD(r.data)), []);
  useEffect(() => {
    load();
  }, [load]);
  if (!d) return null;
  return (
    <div data-testid="vendor-earnings-page" className="av-container max-w-6xl space-y-6 py-12">
      <div><p className="av-eyebrow">Vendor dashboard</p><h1 className="mt-2 text-4xl font-bold tracking-tight text-av-ink">Earnings & payouts</h1></div>
      {d.mode === "test" && <StatusAlert tone="info" title="Test mode" testId="vendor-earnings-test-mode">All payments are Stripe test payments. Earnings become eligible {d.hold_days} days after confirmed payment; a transfer to your Stripe account is separate from the bank deposit.</StatusAlert>}
      <PayoutAccount account={d.account} reload={load} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {BUCKETS.map(([k, label]) => <div key={k} className="rounded-2xl border border-av-line bg-white p-4"><p className="text-xs text-av-muted">{label}</p>
          <p className="text-xl font-bold" data-testid={`vendor-balance-${k}`}>{formatPrice(d.balances[k])}</p></div>)}
      </div>
      <section className="overflow-x-auto rounded-2xl border border-av-line bg-white p-5" data-testid="vendor-order-earnings">
        <h2 className="mb-3 text-xl font-semibold">Order earnings</h2>
        {d.vendor_orders.length === 0 ? <p className="text-sm text-av-muted" data-testid="vendor-earnings-empty">No paid orders yet.</p> : (
          <table className="w-full min-w-[720px] text-left text-sm"><thead className="text-xs text-av-muted"><tr><th>Order</th><th>Items</th><th>Shipping</th><th>Commission</th><th>Card fee share</th><th>Refunds</th><th>Your net</th><th>Status</th></tr></thead>
            <tbody>{d.vendor_orders.map((v) => <Breakdown key={v.id} v={v} />)}</tbody></table>)}
        <p className="mt-3 text-xs text-av-muted">Commission is on items after discounts (not shipping or tax). Card fees are Stripe's actual fee, shared across sellers in the same payment by amount.</p>
      </section>
      {d.payouts.length > 0 && <section className="rounded-2xl border border-av-line bg-white p-5"><h2 className="mb-2 text-xl font-semibold">Transfers</h2>
        <ul className="divide-y divide-av-line text-sm">{d.payouts.map((p) => <li key={p.id} className="flex justify-between py-2" data-testid={`vendor-payout-${p.id}`}>
          <span>{p.order_number}{p.simulated && " · simulated"}</span><span>{formatPrice(p.amount_minor)} · {p.status}</span></li>)}</ul></section>}
      {d.disputes.length > 0 && <section className="rounded-2xl border border-av-line bg-white p-5"><h2 className="text-xl font-semibold">Disputes</h2>
        <ul className="divide-y divide-av-line">{d.disputes.map((x) => <Evidence key={x.id} d={x} reload={load} />)}</ul></section>}
    </div>
  );
}
