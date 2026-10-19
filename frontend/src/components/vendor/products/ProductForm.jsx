import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field, FormError } from "@/components/auth/AuthCard";
import { flatCategories, fromMinor, toMinor } from "@/components/vendor/products/productUtils";

const init = (p) => ({
  title: p?.title || "", description: p?.description || "", category_slug: p?.category_slug || "", tags: (p?.tags || []).join(", "),
  sku: p?.sku || "", price: fromMinor(p?.price_minor), low_stock_threshold: String(p?.low_stock_threshold ?? 5), initial_stock: "0",
});

export const ProductForm = ({ product, categories, onSubmit, isNew, disabled, error }) => {
  const [f, setF] = useState(() => init(product));
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = (e) => {
    e.preventDefault();
    onSubmit({
      title: f.title.trim(), description: f.description.trim(), category_slug: f.category_slug, sku: f.sku.trim(),
      tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean), price_minor: toMinor(f.price) || 0, currency: "USD",
      option_names: product?.option_names || [], low_stock_threshold: parseInt(f.low_stock_threshold, 10) || 0,
      ...(isNew ? { initial_stock: parseInt(f.initial_stock, 10) || 0 } : {}),
    });
  };
  return (
    <form onSubmit={submit} className="grid gap-5 sm:grid-cols-2" data-testid="product-form">
      <div className="sm:col-span-2"><FormError message={error} testId="product-form-error" /></div>
      <div className="sm:col-span-2"><Field id="pf-title" label="Product title" value={f.title} onChange={set("title")} disabled={disabled} required testId="product-title-input" /></div>
      <div className="sm:col-span-2 space-y-2">
        <Label htmlFor="pf-desc">Description</Label>
        <Textarea id="pf-desc" rows={6} value={f.description} onChange={set("description")} disabled={disabled} className="bg-white" data-testid="product-description-input"
          placeholder="Materials, size, origin, care — at least 20 characters before review." />
      </div>
      <div className="space-y-2">
        <Label>Category</Label>
        <Select value={f.category_slug} onValueChange={(v) => setF({ ...f, category_slug: v })} disabled={disabled}>
          <SelectTrigger className="h-11 bg-white" data-testid="product-category-select"><SelectValue placeholder="Choose a category" /></SelectTrigger>
          <SelectContent>{flatCategories(categories).map((c) => <SelectItem key={c.slug} value={c.slug} data-testid={`product-category-${c.slug}`}>{c.name}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <Field id="pf-tags" label="Tags (comma separated)" value={f.tags} onChange={set("tags")} disabled={disabled} testId="product-tags-input" />
      <Field id="pf-sku" label="Product SKU" value={f.sku} onChange={set("sku")} disabled={disabled} required testId="product-sku-input" />
      <Field id="pf-price" label={isNew || !product?.option_names?.length ? "Price (USD)" : "Default price for new variants (USD)"} inputMode="decimal" value={f.price} onChange={set("price")} disabled={disabled} required testId="product-price-input" />
      <Field id="pf-low" label="Low-stock alert at" type="number" min="0" value={f.low_stock_threshold} onChange={set("low_stock_threshold")} disabled={disabled} testId="product-low-stock-input" />
      {isNew && <Field id="pf-stock" label="Opening stock" type="number" min="0" value={f.initial_stock} onChange={set("initial_stock")} testId="product-initial-stock-input" />}
      <Button type="submit" className="sm:col-span-2" disabled={disabled} data-testid="product-save-button">{isNew ? "Create draft" : "Save details"}</Button>
    </form>
  );
};
