import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, getErrorMessage } from "@/lib/api";

const money = (m) => `$${((m || 0) / 100).toFixed(2)}`;
const pct = (x) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);

const Stat = ({ l, v, id }) => <div className="rounded-xl bg-white p-4"><p className="text-xs text-av-muted">{l}</p><p className="text-xl font-bold" data-testid={id}>{v}</p></div>;

const Report = () => {
  const [a, setA] = useState(null);
  const [r, setR] = useState(null);
  const [c, setC] = useState(null);
  const [range, setRange] = useState({ from: "", to: "" });
  const load = useCallback(() => {
    const params = range.from && range.to ? range : {};
    api.get("/admin/analytics", { params }).then((x) => setA(x.data)).catch(() => setA(false));
    api.get("/admin/referrals").then((x) => setR(x.data)).catch(() => {});
    api.get("/admin/cart-reminders/stats").then((x) => setC(x.data)).catch(() => {});
  }, [range]);
  useEffect(() => {
    load();
  }, [load]);
  if (a === false) return null;
  return (
    <section className="space-y-3" data-testid="mk-analytics">
      <div className="flex flex-wrap items-end gap-2"><h2 className="mr-auto text-lg font-semibold">Analytics {a && <span className="text-xs font-normal text-av-muted">{a.range.from} – {a.range.to} · {a.range.timezone}</span>}</h2>
        <Input type="date" className="w-40" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} data-testid="mk-from" />
        <Input type="date" className="w-40" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} data-testid="mk-to" /></div>
      {a && <div className="grid gap-3 sm:grid-cols-4">
        <Stat l="Visitors" v={a.visitors} id="mk-visitors" /><Stat l="Page views" v={a.events.page_view} id="mk-pageviews" /><Stat l="Product views" v={a.events.product_view} id="mk-productviews" />
        <Stat l="Searches" v={a.events.search} id="mk-searches" /><Stat l="Add to cart" v={a.events.add_to_cart} id="mk-atc" /><Stat l="Checkout starts" v={a.events.begin_checkout} id="mk-checkouts" />
        <Stat l="Purchases · revenue" v={`${a.purchases} · ${money(a.revenue_minor)}`} id="mk-purchases" /><Stat l="Checkout conversion" v={pct(a.checkout_conversion)} id="mk-conversion" /></div>}
      {a && <div className="grid gap-3 md:grid-cols-2 text-sm">
        <div className="rounded-xl bg-white p-4"><p className="font-semibold">Popular products</p>{a.top_products.length === 0 ? <p className="text-av-muted">No data yet.</p> : <ol className="list-decimal pl-5">{a.top_products.map((p) => <li key={p.slug}>{p.title} · {p.views}</li>)}</ol>}</div>
        <div className="rounded-xl bg-white p-4"><p className="font-semibold">Top searches</p>{a.top_searches.length === 0 ? <p className="text-av-muted">No data yet.</p> : <ol className="list-decimal pl-5">{a.top_searches.map((s) => <li key={s.query}>{s.query} · {s.count}</li>)}</ol>}</div></div>}
      {r && <div className="grid gap-3 sm:grid-cols-4" data-testid="mk-referrals"><Stat l="Referral visits" v={r.visits} id="mk-ref-visits" /><Stat l="Referred sign-ups" v={r.signups} id="mk-ref-signups" />
        <Stat l="First paid orders" v={`${r.first_orders} (${pct(r.signup_to_order)})`} id="mk-ref-orders" /><Stat l="Referral sales" v={money(r.sales_minor)} id="mk-ref-sales" /></div>}
      {c && <p className="text-sm" data-testid="mk-cart-stats">Cart reminders: {c.enabled ? "on" : "off"} · sent {c.sent} · clicked {c.clicked} · recovered carts {c.recovered_carts} · cancelled {c.cancelled}</p>}
      {a && <p className="text-xs text-av-muted">{a.source_note}</p>}
    </section>
  );
};

const Flags = () => {
  const [f, setF] = useState(null);
  useEffect(() => {
    api.get("/admin/marketing/flags").then((r) => setF(r.data)).catch(() => setF(false));
  }, []);
  if (!f) return null;
  const ac = f.abandoned_cart;
  const save = () => api.put("/admin/marketing/flags", { abandoned_cart_enabled: ac.enabled, first_delay_min: ac.first_delay_min, second_delay_min: ac.second_delay_min,
    max_per_7_days: ac.max_per_7_days, ga4_enabled: !!f.ga4_enabled, analytics_retention_days: f.analytics_retention_days,
    wishlist_alerts_enabled: f.wishlist_alerts.enabled, wishlist_threshold_bps: f.wishlist_alerts.threshold_bps, wishlist_max_items: f.wishlist_alerts.max_items }).then((r) => {
    setF({ ...f, ...r.data });
    toast.success("Settings saved");
  }).catch((e) => toast.error(getErrorMessage(e)));
  const setAc = (k, v) => setF({ ...f, abandoned_cart: { ...ac, [k]: v } });
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid="mk-flags">
      <h2 className="font-semibold">Marketing switches</h2>
      <label className="flex items-center justify-between">Abandoned cart reminders (opted-in customers only)<Switch checked={ac.enabled} onCheckedChange={(v) => setAc("enabled", v)} data-testid="mk-flag-cart" /></label>
      <div className="flex flex-wrap gap-2">
        <label className="text-xs">1st reminder (min)<Input type="number" className="w-24" value={ac.first_delay_min} onChange={(e) => setAc("first_delay_min", Number(e.target.value))} data-testid="mk-cart-first" /></label>
        <label className="text-xs">2nd reminder (min)<Input type="number" className="w-24" value={ac.second_delay_min} onChange={(e) => setAc("second_delay_min", Number(e.target.value))} data-testid="mk-cart-second" /></label>
        <label className="text-xs">Max per 7 days<Input type="number" className="w-20" value={ac.max_per_7_days} onChange={(e) => setAc("max_per_7_days", Number(e.target.value))} data-testid="mk-cart-max" /></label></div>
      <label className="flex items-center justify-between">Wishlist daily summary (9:00 AM ET, opted-in shoppers only)<Switch checked={f.wishlist_alerts.enabled} onCheckedChange={(v) => setF({ ...f, wishlist_alerts: { ...f.wishlist_alerts, enabled: v } })} data-testid="mk-flag-wishlist" /></label>
      <label className="text-xs">Price-drop threshold (%)<Input type="number" min={1} max={90} className="w-24" value={f.wishlist_alerts.threshold_bps / 100} onChange={(e) => setF({ ...f, wishlist_alerts: { ...f.wishlist_alerts, threshold_bps: Math.round(Number(e.target.value) * 100) } })} data-testid="mk-wishlist-threshold" /></label>
      <label className="flex items-center justify-between">Google Analytics 4 {f.ga4_configured ? "" : "(no Measurement ID configured)"}<Switch checked={!!f.ga4_enabled} disabled={!f.ga4_configured} onCheckedChange={(v) => setF({ ...f, ga4_enabled: v })} data-testid="mk-flag-ga4" /></label>
      <p className="rounded-lg bg-av-sand p-2 text-xs" data-testid="mk-locked">Locked off until pricing and billing are approved: paid vendor subscriptions, sponsored listings, referral rewards.</p>
      <Button size="sm" onClick={save} data-testid="mk-flags-save">Save</Button>
    </section>
  );
};

const CEMPTY = { name: "", headline: "", subtext: "", cta_label: "Shop now", cta_url: "/shop", coupon_code: "", product_slugs: [], placement: "homepage_strip", status: "draft" };

const Campaigns = () => {
  const [rows, setRows] = useState(null);
  const [f, setF] = useState(CEMPTY);
  const load = useCallback(() => api.get("/admin/campaigns").then((r) => setRows(r.data.data)).catch(() => setRows(false)), []);
  useEffect(() => {
    load();
  }, [load]);
  if (rows === false) return null;
  const save = () => api.post("/admin/campaigns", f).then(() => {
    toast.success("Campaign saved");
    setF(CEMPTY);
    load();
  }).catch((e) => toast.error(getErrorMessage(e)));
  const toggle = (c) => api.put(`/admin/campaigns/${c.id}`, { ...c, status: c.status === "active" ? "paused" : "active", coupon_code: c.coupon_code || "" }).then(load).catch((e) => toast.error(getErrorMessage(e)));
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid="mk-campaigns">
      <h2 className="font-semibold">Homepage campaigns</h2>
      <div className="grid gap-2 md:grid-cols-3">
        {[["name", "Internal name"], ["headline", "Headline"], ["subtext", "Supporting text"], ["cta_label", "Button label"], ["cta_url", "Button link (/path or https://)"], ["coupon_code", "Marketplace coupon (optional)"]].map(([k, l]) =>
          <Input key={k} placeholder={l} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`mk-camp-${k}`} />)}
        <select className="rounded-md border px-2" value={f.placement} onChange={(e) => setF({ ...f, placement: e.target.value })} data-testid="mk-camp-placement"><option value="homepage_strip">Homepage strip</option><option value="homepage_hero">Homepage hero</option></select>
        <select className="rounded-md border px-2" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} data-testid="mk-camp-status"><option value="draft">Draft</option><option value="active">Active</option></select>
      </div>
      <Button size="sm" disabled={f.name.length < 2 || f.headline.length < 2} onClick={save} data-testid="mk-camp-save">Save campaign</Button>
      <ul className="divide-y divide-av-line">{(rows || []).map((c) => <li key={c.id} className="flex items-center justify-between gap-2 py-2" data-testid={`mk-camp-${c.id}`}><span><b>{c.name}</b> · {c.headline} · {c.placement} · {c.status}</span>
        <Button size="sm" variant="outline" onClick={() => toggle(c)} data-testid={`mk-camp-toggle-${c.id}`}>{c.status === "active" ? "Pause" : "Activate"}</Button></li>)}</ul>
    </section>
  );
};

const CouponReport = () => {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.get("/admin/coupons/report").then((r) => setD(r.data)).catch(() => {});
  }, []);
  if (!d) return null;
  return (
    <section className="rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid="mk-coupon-report">
      <h2 className="font-semibold">Coupon funding</h2>
      <p>Marketplace promotional expense: <b data-testid="mk-promo-expense">{money(d.promotional_expense_minor)}</b></p>
      <ul className="mt-2 divide-y divide-av-line">{d.coupons.map((c) => <li key={c.coupon_id} className="py-1">{c.code}: {c.orders} orders · AfroVending funded {money(c.platform_funded_minor)} · vendor funded {money(c.vendor_funded_minor)}</li>)}</ul>
    </section>
  );
};

export default function AdminMarketingPage() {
  return (
    <div className="av-container space-y-6 py-8" data-testid="admin-marketing-page">
      <p className="text-sm"><Link to="/admin" className="underline">← Admin</Link></p>
      <h1 className="text-3xl font-bold tracking-tight text-av-ink">Marketing</h1>
      <Report />
      <Campaigns />
      <CouponReport />
      <Flags />
    </div>
  );
}
