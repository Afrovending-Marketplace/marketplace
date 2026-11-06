import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Field, FormError } from "@/components/auth/AuthCard";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ImageUpload } from "@/components/vendor/FileUpload";
import { Alerts, Breakdown, Card, InventoryCard, OrdersCard, PayoutsCard, Reports, ReviewsCard, SalesChart, SalesKpis, TopProducts } from "@/components/vendor/DashboardCards";
import { api, getErrorMessage } from "@/lib/api";

const KEYS = ["display_name", "tagline", "description", "slug", "logo_file_id", "banner_file_id"];
const etToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
const shift = (iso, days) => { const d = new Date(`${iso}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10); };
const PRESETS = [["7 days", 6], ["30 days", 29], ["90 days", 89]];

const StoreSettings = ({ store, vendor, onSaved }) => {
  const [form, setForm] = useState(Object.fromEntries(KEYS.map((k) => [k, store[k] ?? ""])));
  const [error, setError] = useState("");
  const suspended = vendor.status !== "active";
  const save = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const r = await api.patch("/vendor/store", { ...form, logo_file_id: form.logo_file_id || null, banner_file_id: form.banner_file_id || null });
      onSaved(r.data.store);
      toast.success("Store saved");
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  const toggle = async () => {
    try {
      onSaved((await api.post(`/vendor/store/${store.status === "published" ? "unpublish" : "publish"}`)).data.store);
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <Card title="Store branding & settings" testId="vendor-store-settings">
      <div className="flex flex-wrap gap-3">
        <Button onClick={toggle} disabled={suspended} variant={store.status === "published" ? "outline" : "default"} data-testid="vendor-publish-toggle">{store.status === "published" ? "Unpublish store" : "Publish store"}</Button>
        {store.status === "published" && <Button asChild variant="outline" data-testid="vendor-view-store"><Link to={`/store/${store.slug}`}>View live store</Link></Button>}
        <Button asChild variant="outline" data-testid="vendor-shipping-settings"><Link to="/vendor/orders">Shipping & pickup options</Link></Button>
        <Button asChild variant="outline" data-testid="vendor-reviews-link"><Link to="/vendor/reviews">Reviews & ratings</Link></Button>
      </div>
      <form onSubmit={save} className="grid gap-5 sm:grid-cols-2" data-testid="vendor-store-form">
        <div className="sm:col-span-2"><FormError message={error} testId="vendor-store-error" /></div>
        <Field id="vs-name" label="Store name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} disabled={suspended} testId="store-name-input" />
        <Field id="vs-slug" label="Store URL slug" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} disabled={suspended} testId="store-slug-input" />
        <div className="sm:col-span-2"><Field id="vs-tag" label="Tagline" value={form.tagline} onChange={(e) => setForm({ ...form, tagline: e.target.value })} disabled={suspended} testId="store-tagline-input" /></div>
        <div className="space-y-2 sm:col-span-2"><Label htmlFor="vs-desc">About the store</Label>
          <Textarea id="vs-desc" rows={5} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} disabled={suspended} className="bg-white" data-testid="store-description-input" /></div>
        <ImageUpload label="Logo" purpose="logo" fileId={form.logo_file_id} onChange={(f) => setForm({ ...form, logo_file_id: f.id })} testId="store-logo-upload" />
        <ImageUpload label="Banner" purpose="banner" fileId={form.banner_file_id} onChange={(f) => setForm({ ...form, banner_file_id: f.id })} testId="store-banner-upload" />
        <Button type="submit" className="sm:col-span-2" disabled={suspended} data-testid="store-save-button">Save store</Button>
      </form>
    </Card>
  );
};

const RangePicker = ({ range, setRange }) => {
  const today = etToday();
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="dash-range">
      {PRESETS.map(([n, d]) => <Button key={n} size="sm" variant={range.to === today && range.from === shift(today, -d) ? "default" : "outline"} onClick={() => setRange({ from: shift(today, -d), to: today })} data-testid={`range-${d + 1}`}>{n}</Button>)}
      <Button size="sm" variant="outline" onClick={() => setRange({ from: `${today.slice(0, 7)}-01`, to: today })} data-testid="range-month">This month</Button>
      <input type="date" className="h-8 rounded border border-av-line px-1" value={range.from} max={range.to} onChange={(e) => e.target.value && setRange({ ...range, from: e.target.value })} data-testid="range-from" />→
      <input type="date" className="h-8 rounded border border-av-line px-1" value={range.to} min={range.from} max={today} onChange={(e) => e.target.value && setRange({ ...range, to: e.target.value })} data-testid="range-to" />
      <span className="text-av-muted" data-testid="range-tz">US Eastern time</span>
    </div>
  );
};

export default function VendorDashboardPage() {
  const [store, setStore] = useState(null);
  const [d, setD] = useState(null);
  const [range, setRange] = useState(() => ({ from: shift(etToday(), -29), to: etToday() }));
  const load = useCallback(() => api.get("/vendor/dashboard", { params: range }).then((r) => setD(r.data)).catch((err) => toast.error(getErrorMessage(err))), [range]);
  useEffect(() => {
    api.get("/vendor/store").then((r) => setStore(r.data));
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  if (!store) return null;
  return (
    <div data-testid="vendor-dashboard-page" className="av-container max-w-6xl space-y-6 py-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="av-eyebrow">Vendor control center</p><h1 className="mt-2 text-4xl font-bold tracking-tight text-av-ink">{store.store.display_name}</h1></div>
        <StatusBadge tone={store.store.status === "published" ? "success" : "gold"} testId="vendor-store-status">{store.store.status}</StatusBadge>
      </div>
      {store.vendor.status !== "active" && <StatusAlert tone="error" title="Vendor account suspended" testId="vendor-suspended-alert">{store.vendor.status_reason || "Contact info@afrovending.com."}</StatusAlert>}
      <Tabs defaultValue="overview">
        <TabsList className="grid h-auto w-full grid-cols-2 gap-1 sm:flex sm:w-auto sm:justify-start">
          <TabsTrigger value="overview" data-testid="dash-tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="operations" data-testid="dash-tab-operations">Orders & stock</TabsTrigger>
          <TabsTrigger value="money" data-testid="dash-tab-money">Earnings & payouts</TabsTrigger>
          <TabsTrigger value="store" data-testid="dash-tab-store">Store settings</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="space-y-5 pt-4">
          <RangePicker range={range} setRange={setRange} />
          {d && <><SalesKpis s={d.sales} /><Card title="Daily net item sales" testId="dash-chart-card"><SalesChart series={d.sales.series} /></Card>
            <div className="grid gap-5 lg:grid-cols-2"><Alerts items={d.alerts} /><OrdersCard ops={d.operations} /><TopProducts rows={d.top_products} /><ReviewsCard r={d.reviews} /></div>
            <Reports range={range} /></>}
        </TabsContent>
        <TabsContent value="operations" className="grid gap-5 pt-4 lg:grid-cols-2">{d && <><OrdersCard ops={d.operations} /><InventoryCard inv={d.inventory} /></>}</TabsContent>
        <TabsContent value="money" className="space-y-5 pt-4">
          <RangePicker range={range} setRange={setRange} />
          {d && <div className="grid gap-5 lg:grid-cols-2"><Breakdown s={d.sales} plan={d.plan} /><PayoutsCard pay={d.payouts} /></div>}
          {d && <Reports range={range} />}
        </TabsContent>
        <TabsContent value="store" className="pt-4"><StoreSettings store={store.store} vendor={store.vendor} onSaved={(s) => { setStore({ ...store, store: s }); load(); }} /></TabsContent>
      </Tabs>
    </div>
  );
}
