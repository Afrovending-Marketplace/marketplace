import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, getErrorMessage } from "@/lib/api";

const money = (m) => (m == null ? "—" : `$${(m / 100).toFixed(2)}`);
const EMPTY = { code: "", type: "percent", value: 1000, min_subtotal_minor: 0, max_redemptions: null, status: "active" };

const Coupons = () => {
  const [rows, setRows] = useState([]);
  const [f, setF] = useState(EMPTY);
  const load = useCallback(() => api.get("/vendor/coupons").then((r) => setRows(r.data.data)).catch(() => {}), []);
  useEffect(() => {
    load();
  }, [load]);
  const save = async () => {
    try {
      await api.post("/vendor/coupons", f);
      toast.success("Coupon created");
      setF(EMPTY);
      load();
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  };
  const pause = (c) => api.put(`/vendor/coupons/${c.id}`, { ...c, status: c.status === "active" ? "paused" : "active" }).then(load).catch((e) => toast.error(getErrorMessage(e)));
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="vendor-coupons">
      <h2 className="font-semibold">Store coupons</h2>
      <p className="text-xs text-av-muted">You fund your own coupons. They only apply to your products and reduce your sales before commission is calculated.</p>
      <div className="flex flex-wrap gap-2">
        <Input className="w-36" placeholder="CODE" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} data-testid="vcoupon-code" />
        <select className="rounded-md border px-2 text-sm" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })} data-testid="vcoupon-type"><option value="percent">% off</option><option value="fixed">$ off</option></select>
        <Input className="w-28" type="number" min={1} value={f.type === "percent" ? f.value / 100 : f.value / 100} onChange={(e) => setF({ ...f, value: Math.round(Number(e.target.value) * 100) })} data-testid="vcoupon-value" />
        <Input className="w-36" type="number" min={0} placeholder="Min spend $" onChange={(e) => setF({ ...f, min_subtotal_minor: Math.round(Number(e.target.value || 0) * 100) })} data-testid="vcoupon-min" />
        <Button onClick={save} disabled={f.code.length < 3} data-testid="vcoupon-create">Create</Button>
      </div>
      <ul className="divide-y divide-av-line text-sm">{rows.map((c) => <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2" data-testid={`vcoupon-${c.code}`}>
        <span><b>{c.code}</b> · {c.type === "percent" ? `${c.value / 100}% off` : `${money(c.value)} off`} · used {c.redemptions}× · {c.status}</span>
        <Button size="sm" variant="outline" onClick={() => pause(c)} data-testid={`vcoupon-toggle-${c.code}`}>{c.status === "active" ? "Pause" : "Activate"}</Button></li>)}</ul>
    </section>
  );
};

const Plan = () => {
  const [p, setP] = useState(null);
  const [plans, setPlans] = useState([]);
  const load = useCallback(() => {
    api.get("/vendor/subscription").then((r) => setP(r.data)).catch(() => {});
    api.get("/plans").then((r) => setPlans(r.data.plans));
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  if (!p) return null;
  const ask = (plan) => api.post("/vendor/subscription/request", { plan }).then((r) => {
    toast.success(r.data.message);
    load();
  }).catch((e) => toast.error(getErrorMessage(e)));
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="vendor-plan">
      <h2 className="font-semibold">Subscription plan</h2>
      <p className="text-xs text-av-muted" data-testid="vendor-plan-note">Paid plans can't be purchased yet — nothing is charged. You can register interest and we'll contact you when billing opens.</p>
      <div className="grid gap-3 md:grid-cols-3">{plans.map((pl) => <div key={pl.key} className={`rounded-xl border p-4 text-sm ${pl.key === p.plan ? "border-av-clay" : "border-av-line"}`} data-testid={`plan-${pl.key}`}>
        <p className="font-semibold">{pl.name}</p><p>{pl.monthly_fee_minor ? `${money(pl.monthly_fee_minor)}/month` : "Free"} · {pl.rate_bps / 100}% commission</p>
        <ul className="my-2 list-disc pl-4 text-xs">{pl.features.map((x) => <li key={x}>{x}</li>)}</ul>
        {pl.key === p.plan ? <span className="text-xs font-semibold">Current plan</span> : <Button size="sm" variant="outline" onClick={() => ask(pl.key)} data-testid={`plan-request-${pl.key}`}>{p.pending_request?.plan === pl.key ? "Interest noted" : "Register interest"}</Button>}</div>)}</div>
    </section>
  );
};

const Analytics = () => {
  const [a, setA] = useState(null);
  useEffect(() => {
    api.get("/vendor/analytics").then((r) => setA(r.data)).catch(() => {});
  }, []);
  if (!a) return null;
  return (
    <section className="rounded-2xl border border-av-line bg-white p-5" data-testid="vendor-analytics">
      <h2 className="font-semibold">Store analytics <span className="text-xs font-normal text-av-muted">({a.range.from} – {a.range.to}, {a.range.timezone})</span></h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-4 text-sm">{[["Product views", a.product_views, "views"], ["Add to cart", a.add_to_cart, "atc"], ["Orders", a.orders, "orders"], ["Net item sales", money(a.net_item_sales_minor), "sales"]].map(([l, v, k]) =>
        <div key={k}><p className="text-xs text-av-muted">{l}</p><p className="text-xl font-bold" data-testid={`vendor-analytics-${k}`}>{v}</p></div>)}</div>
      <p className="mt-2 text-xs text-av-muted">Views count only shoppers who accepted analytics cookies; orders and sales come from paid orders.</p>
    </section>
  );
};

export default function VendorMarketingPage() {
  return (
    <div className="av-container space-y-6 py-8" data-testid="vendor-marketing-page">
      <h1 className="text-3xl font-bold tracking-tight text-av-ink">Marketing</h1>
      <Analytics />
      <Coupons />
      <Plan />
    </div>
  );
}
