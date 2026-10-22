import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Field, FormError } from "@/components/auth/AuthCard";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ImageUpload } from "@/components/vendor/FileUpload";
import { api, getErrorMessage } from "@/lib/api";

const KEYS = ["display_name", "tagline", "description", "slug", "logo_file_id", "banner_file_id"];

export default function VendorDashboardPage() {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const apply = (d) => { setData(d); setForm(Object.fromEntries(KEYS.map((k) => [k, d.store[k] ?? ""]))); };
  useEffect(() => {
    api.get("/vendor/store").then((r) => apply(r.data));
  }, []);
  if (!data) return null;
  const suspended = data.vendor.status !== "active";
  const save = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const r = await api.patch("/vendor/store", { ...form, logo_file_id: form.logo_file_id || null, banner_file_id: form.banner_file_id || null });
      apply({ ...data, store: r.data.store });
      toast.success("Store saved");
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  const toggle = async () => {
    try {
      const r = await api.post(`/vendor/store/${data.store.status === "published" ? "unpublish" : "publish"}`);
      apply({ ...data, store: r.data.store });
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <div data-testid="vendor-dashboard-page" className="av-container max-w-3xl py-12 space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="av-eyebrow">Vendor dashboard</p><h1 className="mt-2 text-4xl font-bold tracking-tight text-av-ink">{data.store.display_name}</h1></div>
        <StatusBadge tone={data.store.status === "published" ? "success" : "gold"} testId="vendor-store-status">{data.store.status}</StatusBadge>
      </div>
      {suspended && <StatusAlert tone="error" title="Vendor account suspended" testId="vendor-suspended-alert">{data.vendor.status_reason || "Contact info@afrovending.com."}</StatusAlert>}
      <div className="flex flex-wrap gap-3">
        <Button onClick={toggle} disabled={suspended} variant={data.store.status === "published" ? "outline" : "default"} data-testid="vendor-publish-toggle">{data.store.status === "published" ? "Unpublish store" : "Publish store"}</Button>
        {data.store.status === "published" && <Button asChild variant="outline" data-testid="vendor-view-store"><Link to={`/store/${data.store.slug}`}>View live store</Link></Button>}
        <Button asChild variant="outline" data-testid="vendor-manage-products"><Link to="/vendor/products">Manage products</Link></Button>
        <Button asChild variant="outline" data-testid="vendor-earnings-link"><Link to="/vendor/earnings">Earnings & payouts</Link></Button>
        <Button asChild variant="outline" data-testid="vendor-orders-link"><Link to="/vendor/orders">Orders</Link></Button>
      </div>
      <form onSubmit={save} className="grid gap-5 rounded-2xl border border-av-line bg-white p-6 md:p-8 sm:grid-cols-2" data-testid="vendor-store-form">
        <div className="sm:col-span-2"><FormError message={error} testId="vendor-store-error" /></div>
        <Field id="vs-name" label="Store name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} disabled={suspended} testId="store-name-input" />
        <Field id="vs-slug" label="Store URL slug" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} disabled={suspended} testId="store-slug-input" />
        <div className="sm:col-span-2"><Field id="vs-tag" label="Tagline" value={form.tagline} onChange={(e) => setForm({ ...form, tagline: e.target.value })} disabled={suspended} testId="store-tagline-input" /></div>
        <div className="sm:col-span-2 space-y-2"><Label htmlFor="vs-desc">About the store</Label>
          <Textarea id="vs-desc" rows={5} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} disabled={suspended} className="bg-white" data-testid="store-description-input" /></div>
        <ImageUpload label="Logo" purpose="logo" fileId={form.logo_file_id} onChange={(f) => setForm({ ...form, logo_file_id: f.id })} testId="store-logo-upload" />
        <ImageUpload label="Banner" purpose="banner" fileId={form.banner_file_id} onChange={(f) => setForm({ ...form, banner_file_id: f.id })} testId="store-banner-upload" />
        <Button type="submit" className="sm:col-span-2" disabled={suspended} data-testid="store-save-button">Save store</Button>
      </form>
      <p className="text-xs text-av-muted">Order fulfilment and shipping arrive in Phase 08.</p>
    </div>
  );
}
