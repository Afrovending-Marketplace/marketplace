import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";

const SECTIONS = [
  { path: "shipping-methods", title: "Shipping options", hint: "No options = checkout shows \"rate to be confirmed\". Amounts in USD.",
    fields: [["name", "Name"], ["amount", "Amount ($)"], ["eta", "Delivery estimate"], ["free_over", "Free over ($, optional)"], ["vendor_slug", "Vendor store slug (optional)"]],
    toBody: (f) => ({ name: f.name, amount_minor: Math.round(Number(f.amount) * 100), eta: f.eta, free_over_minor: f.free_over ? Math.round(Number(f.free_over) * 100) : null, vendor_slug: f.vendor_slug || null }),
    show: (d) => `${d.name} · $${(d.amount_minor / 100).toFixed(2)}${d.free_over_minor != null ? ` · free over $${(d.free_over_minor / 100).toFixed(2)}` : ""}` },
  { path: "coupons", title: "Coupons", hint: "Percent value is in %, fixed value in $.",
    fields: [["code", "Code"], ["type", "percent or fixed"], ["value", "Value"], ["min", "Min subtotal ($)"], ["max", "Max uses (optional)"]],
    toBody: (f) => ({ code: f.code, type: f.type, value: f.type === "percent" ? Math.round(Number(f.value) * 100) : Math.round(Number(f.value) * 100), min_subtotal_minor: Math.round(Number(f.min || 0) * 100), max_redemptions: f.max ? Number(f.max) : null }),
    show: (d) => `${d.code} · ${d.type === "percent" ? `${d.value / 100}%` : `$${(d.value / 100).toFixed(2)}`} off${d.min_subtotal_minor ? ` · min $${(d.min_subtotal_minor / 100).toFixed(2)}` : ""}` },
  { path: "tax-rates", title: "Estimated tax rates", hint: "Enter only rates confirmed by your accountant. Without a rate, tax shows as not calculated.",
    fields: [["country", "Country (2 letters)"], ["region", "Region/state code (optional)"], ["rate", "Rate (%)"], ["label", "Label"]],
    toBody: (f) => ({ country: f.country, region: f.region, rate_bps: Math.round(Number(f.rate) * 100), label: f.label }),
    show: (d) => `${d.country}${d.region ? `-${d.region}` : ""} · ${d.rate_bps / 100}% · ${d.label}` },
];

const Section = ({ s }) => {
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({});
  const load = useCallback(async () => setRows((await api.get(`/admin/commerce/${s.path}`)).data.data), [s.path]);
  useEffect(() => {
    load();
  }, [load]);
  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/admin/commerce/${s.path}`, s.toBody(f));
      setF({});
      toast.success("Saved");
      load();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  const toggle = async (d) => {
    const { id, created_at, updated_at, created_by, vendor_id, redemptions, ...rest } = d;
    try {
      await api.put(`/admin/commerce/${s.path}/${id}`, { ...rest, status: d.status === "active" ? (s.path === "coupons" ? "paused" : "inactive") : "active" });
      load();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid={`commerce-${s.path}`}>
      <h2 className="text-xl font-semibold">{s.title}</h2><p className="text-xs text-av-muted">{s.hint}</p>
      <ul className="divide-y divide-av-line text-sm">
        {rows.length === 0 && <li className="py-2 text-av-muted">None yet.</li>}
        {rows.map((d) => <li key={d.id} className="flex items-center justify-between gap-3 py-2"><span>{s.show(d)}</span>
          <span className="flex items-center gap-2"><StatusBadge tone={d.status === "active" ? "success" : "neutral"}>{d.status}</StatusBadge>
            <Button size="sm" variant="outline" onClick={() => toggle(d)} data-testid={`commerce-toggle-${d.id}`}>{d.status === "active" ? "Disable" : "Enable"}</Button></span></li>)}
      </ul>
      <form onSubmit={create} className="flex flex-wrap gap-2">
        {s.fields.map(([k, label]) => <Input key={k} aria-label={label} placeholder={label} value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} className="h-9 w-44" data-testid={`commerce-${s.path}-${k}`} />)}
        <Button type="submit" size="sm" data-testid={`commerce-${s.path}-create`}>Add</Button>
      </form>
    </section>
  );
};

export default function AdminCommercePage() {
  return (
    <div data-testid="admin-commerce-page" className="av-container max-w-5xl space-y-6 py-12">
      <h1 className="text-4xl font-bold tracking-tight text-av-ink">Checkout settings</h1>
      <p className="text-sm text-av-muted">Nothing is pre-filled: AfroVending doesn't invent delivery charges or tax rates. Totals stay marked as estimates until payment (Phase 07).</p>
      {SECTIONS.map((s) => <Section key={s.path} s={s} />)}
    </div>
  );
}
