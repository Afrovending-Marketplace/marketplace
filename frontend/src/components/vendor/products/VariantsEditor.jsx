import { useState } from "react";
import { Plus, Trash2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FormError } from "@/components/auth/AuthCard";
import { fromMinor, toMinor } from "@/components/vendor/products/productUtils";
import { api, getErrorMessage } from "@/lib/api";

const toRow = (v) => ({ key: v.id, id: v.id, sku: v.sku, options: v.options || {}, price: fromMinor(v.price_minor), stock: "0" });
const cartesian = (lists) => lists.reduce((acc, l) => acc.flatMap((a) => l.map((x) => [...a, x])), [[]]);

export const VariantsEditor = ({ product, variants, onSaved, disabled }) => {
  const [names, setNames] = useState((product.option_names || []).join(", "));
  const [values, setValues] = useState("");
  const [rows, setRows] = useState(() => variants.filter((v) => v.status === "active").map(toRow));
  const [error, setError] = useState("");
  const optionNames = names.split(",").map((n) => n.trim()).filter(Boolean).slice(0, 3);
  const update = (i, patch) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const blank = (opts = {}) => ({ key: Math.random().toString(36).slice(2), sku: "", options: opts, price: fromMinor(product.price_minor), stock: "0" });
  const generate = () => {
    const lists = values.split("|").map((g) => g.split(",").map((x) => x.trim()).filter(Boolean));
    if (lists.length !== optionNames.length || lists.some((l) => !l.length)) return toast.error("Enter values for each option, separated by | (e.g. S, M, L | Red, Blue).");
    const fresh = cartesian(lists).map((combo) => ({ ...blank(Object.fromEntries(optionNames.map((n, i) => [n, combo[i]]))), sku: `${product.sku}-${combo.join("-")}`.toUpperCase().replace(/[^A-Z0-9._-]/g, "") }));
    setRows(fresh);
  };
  const save = async () => {
    setError("");
    try {
      const body = { option_names: optionNames, variants: rows.map((r) => ({ id: r.id, sku: r.sku, price_minor: toMinor(r.price) || 0, initial_stock: r.id ? 0 : parseInt(r.stock, 10) || 0,
        options: Object.fromEntries(optionNames.map((n) => [n, r.options[n] || ""])) })) };
      const res = await api.put(`/vendor/products/${product.id}/variants`, body);
      toast.success(res.data.requeued_for_review ? "Variants saved — product sent back for review" : "Variants saved");
      onSaved(res.data);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <div className="space-y-5" data-testid="variants-editor">
      <FormError message={error} testId="variants-error" />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="ve-names" label="Options (up to 3, comma separated)" placeholder="Size, Color, Material" value={names} onChange={(e) => setNames(e.target.value)} disabled={disabled} testId="variant-option-names-input" />
        {optionNames.length > 0 && <div className="flex items-end gap-2">
          <div className="flex-1"><Field id="ve-values" label="Values to combine (| between options)" placeholder="S, M, L | Red, Blue" value={values} onChange={(e) => setValues(e.target.value)} disabled={disabled} testId="variant-values-input" /></div>
          <Button type="button" variant="outline" onClick={generate} disabled={disabled} data-testid="variant-generate-button"><Wand2 /> Generate</Button>
        </div>}
      </div>
      <div className="overflow-x-auto rounded-xl border border-av-line bg-white">
        <table className="w-full min-w-[560px] text-sm">
          <thead className="bg-av-sand text-left text-xs uppercase tracking-wider text-av-muted">
            <tr>{optionNames.map((n) => <th key={n} className="p-3">{n}</th>)}<th className="p-3">SKU</th><th className="p-3">Price</th><th className="p-3">Opening stock</th><th className="p-3" /></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.key} className="border-t border-av-line" data-testid={`variant-row-${i}`}>
                {optionNames.map((n) => <td key={n} className="p-2"><Input aria-label={`${n} value`} value={r.options[n] || ""} onChange={(e) => update(i, { options: { ...r.options, [n]: e.target.value } })} disabled={disabled} data-testid={`variant-${i}-option-${n.toLowerCase()}`} /></td>)}
                <td className="p-2"><Input aria-label="SKU" value={r.sku} onChange={(e) => update(i, { sku: e.target.value })} disabled={disabled} data-testid={`variant-${i}-sku`} /></td>
                <td className="p-2"><Input aria-label="Price" inputMode="decimal" value={r.price} onChange={(e) => update(i, { price: e.target.value })} disabled={disabled} data-testid={`variant-${i}-price`} /></td>
                <td className="p-2">{r.id ? <span className="text-xs text-av-muted">Use Inventory tab</span> : <Input aria-label="Opening stock" type="number" min="0" value={r.stock} onChange={(e) => update(i, { stock: e.target.value })} disabled={disabled} data-testid={`variant-${i}-stock`} />}</td>
                <td className="p-2"><Button type="button" size="icon" variant="ghost" aria-label="Remove variant" onClick={() => setRows(rows.filter((_, j) => j !== i))} disabled={disabled || rows.length === 1} data-testid={`variant-${i}-remove`}><Trash2 /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-av-muted">Removed variants are deactivated, not erased, so their SKU and stock history are kept. Price-only changes keep a live product live; adding or removing variants sends it back for review.</p>
      <div className="flex flex-wrap gap-3">
        <Button type="button" variant="outline" onClick={() => setRows([...rows, blank()])} disabled={disabled || (!optionNames.length && rows.length >= 1)} data-testid="variant-add-button"><Plus /> Add variant</Button>
        <Button type="button" onClick={save} disabled={disabled} data-testid="variants-save-button">Save variants</Button>
      </div>
    </div>
  );
};
