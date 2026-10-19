import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { downloadBlob } from "@/components/vendor/products/productUtils";
import { api, getErrorMessage } from "@/lib/api";

const Preview = ({ preview, onCommit, busy }) => (
  <section className="space-y-5" data-testid="import-preview">
    <div className="flex flex-wrap gap-3 text-sm">
      <StatusBadge tone="success" testId="import-valid-count">{preview.valid_count} ready to import</StatusBadge>
      <StatusBadge tone={preview.invalid_count ? "danger" : "neutral"} testId="import-invalid-count">{preview.invalid_count} with errors</StatusBadge>
    </div>
    {preview.errors.length > 0 && (
      <div className="overflow-x-auto rounded-xl border border-red-200 bg-white">
        <table className="w-full min-w-[480px] text-sm" data-testid="import-error-table">
          <thead className="bg-red-50 text-left text-xs uppercase tracking-wider text-red-800"><tr><th className="p-3">Row</th><th className="p-3">Field</th><th className="p-3">Problem</th></tr></thead>
          <tbody>{preview.errors.map((e, i) => <tr key={i} className="border-t border-av-line" data-testid={`import-error-${i}`}><td className="p-3">{e.row}</td><td className="p-3">{e.field}</td><td className="p-3">{e.message}</td></tr>)}</tbody>
        </table>
      </div>
    )}
    <ul className="divide-y divide-av-line rounded-xl border border-av-line bg-white text-sm" data-testid="import-product-list">
      {preview.products.map((p) => (
        <li key={p.handle} className="flex items-center justify-between gap-3 p-3" data-testid={`import-product-${p.handle}`}>
          <span><b>{p.title || p.handle}</b> <span className="text-av-muted">· {p.variant_count} row{p.variant_count === 1 ? "" : "s"} (rows {p.rows.join(", ")})</span></span>
          <StatusBadge tone={p.valid ? "success" : "danger"}>{p.valid ? "Valid" : "Skipped"}</StatusBadge>
        </li>
      ))}
    </ul>
    <Button onClick={onCommit} disabled={busy || !preview.valid_count} data-testid="import-commit-button">
      {busy && <Loader2 className="animate-spin" />} Import {preview.valid_count} product{preview.valid_count === 1 ? "" : "s"} as drafts
    </Button>
  </section>
);

export default function ProductImportPage() {
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const template = async () => downloadBlob((await api.get("/vendor/products/import/template", { responseType: "blob" })).data, "afrovending-products-template.csv");
  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true); setError(""); setResult(null); setPreview(null);
    const form = new FormData();
    form.append("file", file);
    try {
      setPreview((await api.post("/vendor/products/import/preview", form)).data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const commit = async () => {
    setBusy(true);
    try {
      const r = (await api.post(`/vendor/products/import/${preview.batch_id}/commit`)).data;
      setResult(r); setPreview(null);
      toast.success(`${r.created.length} product${r.created.length === 1 ? "" : "s"} imported as drafts`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div data-testid="product-import-page" className="av-container max-w-4xl space-y-6 py-12">
      <div><p className="av-eyebrow"><Link to="/vendor/products" className="hover:underline">← Products</Link></p><h1 className="mt-2 text-4xl font-bold tracking-tight text-av-ink">Import products</h1>
        <p className="mt-3 text-av-muted">One row per variant. Rows with the same <code>handle</code> become one product. Products are created as drafts — add images, then submit for review.</p></div>
      <div className="flex flex-wrap gap-3">
        <Button variant="outline" onClick={template} data-testid="import-template-button"><Download /> Download template</Button>
        <label className={`inline-flex h-10 cursor-pointer items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground ${busy ? "opacity-50" : ""}`}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload CSV
          <input type="file" accept=".csv,text/csv" className="sr-only" onChange={onFile} disabled={busy} data-testid="import-file-input" aria-label="Upload CSV" />
        </label>
      </div>
      {error && <StatusAlert tone="error" title={error} testId="import-error" />}
      {preview && <Preview preview={preview} onCommit={commit} busy={busy} />}
      {result && (
        <StatusAlert tone="success" title={`Imported ${result.created.length} product(s)`} testId="import-result">
          {result.created.map((c) => <Link key={c.id} to={`/vendor/products/${c.id}`} className="mr-3 underline">{c.title}</Link>)}
          {result.failed.length > 0 && <span className="block text-red-700">Failed: {result.failed.map((f) => `${f.handle} (${f.message})`).join("; ")}</span>}
        </StatusAlert>
      )}
    </div>
  );
}
