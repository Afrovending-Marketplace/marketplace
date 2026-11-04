import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, getErrorMessage } from "@/lib/api";

export const HomepageContent = () => {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.get("/content/homepage").then((r) => setD(r.data)).catch(() => setD(null));
  }, []);
  if (!d || (!d.banners.length && !d.featured_products.length && !d.featured_vendors.length)) return null;
  const Cta = ({ b }) => (b.cta_url && b.cta_label ? (b.cta_url.startsWith("/") ? <Link className="mt-2 inline-block underline" to={b.cta_url}>{b.cta_label}</Link> : <a className="mt-2 inline-block underline" href={b.cta_url} rel="noopener noreferrer">{b.cta_label}</a>) : null);
  return (
    <section className="av-container space-y-4 py-8" data-testid="homepage-content">
      {d.banners.map((b) => <div key={b.id} className={`rounded-2xl p-6 ${b.placement === "home_hero" ? "bg-av-ink text-white" : "bg-av-sand"}`} data-testid={`banner-${b.id}`}>
        <p className="text-xl font-bold">{b.title}</p>{b.body && <p className="mt-1 text-sm opacity-80">{b.body}</p>}<Cta b={b} /></div>)}
      {d.featured_products.length > 0 && <div data-testid="featured-products"><p className="av-eyebrow">Featured products</p><div className="mt-2 flex flex-wrap gap-2">
        {d.featured_products.map((p) => <Link key={p.id} to={`/products/${p.slug}`} className="rounded-full border border-av-line px-3 py-1 text-sm hover:bg-av-sand">{p.title}</Link>)}</div></div>}
      {d.featured_vendors.length > 0 && <div data-testid="featured-vendors"><p className="av-eyebrow">Featured vendors</p><div className="mt-2 flex flex-wrap gap-2">
        {d.featured_vendors.map((v) => <Link key={v.id} to={`/store/${v.slug}`} className="rounded-full border border-av-line px-3 py-1 text-sm hover:bg-av-sand">{v.name}</Link>)}</div></div>}
    </section>
  );
};

export default function AdminContentPage() {
  const [d, setD] = useState(null);
  const [f, setF] = useState({ placement: "home_strip" });
  const [feat, setFeat] = useState({ products: "", vendors: "" });
  const load = useCallback(() => api.get("/admin/content").then((r) => {
    setD(r.data);
    setFeat({ products: r.data.featured.product_ids.join(", "), vendors: r.data.featured.vendor_ids.join(", ") });
  }), []);
  useEffect(() => {
    load();
  }, [load]);
  const run = (fn, msg) => fn().then(() => { toast.success(msg); load(); }).catch((e) => toast.error(getErrorMessage(e)));
  const ids = (s) => s.split(/[\s,]+/).filter(Boolean);
  if (!d) return null;
  return (
    <div className="av-container max-w-5xl space-y-6 py-12" data-testid="admin-content">
      <h1 className="text-3xl font-bold text-av-ink">Homepage & banners</h1>
      <section className="flex flex-wrap gap-2 rounded-2xl border border-av-line bg-white p-5">
        {["title", "body", "cta_label", "cta_url"].map((k) => <Input key={k} className="w-56" placeholder={k.replace("_", " ")} value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`banner-${k}`} />)}
        <select className="h-10 rounded border border-av-line px-2 text-sm" value={f.placement} onChange={(e) => setF({ ...f, placement: e.target.value })} data-testid="banner-placement"><option value="home_hero">Hero</option><option value="home_strip">Strip</option></select>
        <Button onClick={() => run(() => api.post("/admin/content/banners", f), "Banner added")} data-testid="banner-add">Add banner</Button>
      </section>
      <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white px-5 text-sm">{d.banners.map((b) => <li key={b.id} className="flex flex-wrap items-center gap-2 py-2" data-testid={`admin-banner-${b.id}`}>
        <b>{b.title}</b> · {b.placement} · {b.status}
        <Button size="sm" variant="ghost" onClick={() => run(() => api.put(`/admin/content/banners/${b.id}`, { ...b, status: b.status === "active" ? "inactive" : "active" }), "Updated")} data-testid={`banner-toggle-${b.id}`}>{b.status === "active" ? "Hide" : "Show"}</Button>
        <Button size="sm" variant="ghost" onClick={() => run(() => api.delete(`/admin/content/banners/${b.id}`), "Deleted")} data-testid={`banner-delete-${b.id}`}>Delete</Button></li>)}</ul>
      <section className="space-y-2 rounded-2xl border border-av-line bg-white p-5" data-testid="featured-form"><h2 className="font-semibold">Featured on the homepage</h2>
        <p className="text-xs text-av-muted">Paste product or vendor IDs (comma separated). Only published products and active vendors are accepted.</p>
        <Input placeholder="Product IDs" value={feat.products} onChange={(e) => setFeat({ ...feat, products: e.target.value })} data-testid="featured-products-input" />
        <Input placeholder="Vendor IDs" value={feat.vendors} onChange={(e) => setFeat({ ...feat, vendors: e.target.value })} data-testid="featured-vendors-input" />
        <Button onClick={() => run(() => api.put("/admin/content/featured", { product_ids: ids(feat.products), vendor_ids: ids(feat.vendors) }), "Featured saved")} data-testid="featured-save">Save featured</Button></section>
    </div>
  );
}
