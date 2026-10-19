import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ProductForm } from "@/components/vendor/products/ProductForm";
import { VariantsEditor } from "@/components/vendor/products/VariantsEditor";
import { ImagesManager } from "@/components/vendor/products/ImagesManager";
import { InventoryPanel } from "@/components/vendor/products/InventoryPanel";
import { STATUS_LABEL, STATUS_TONE, productFields } from "@/components/vendor/products/productUtils";
import { api, getErrorMessage } from "@/lib/api";

const useCategories = () => {
  const [cats, setCats] = useState([]);
  useEffect(() => {
    api.get("/catalog/categories").then((r) => setCats(r.data.data));
  }, []);
  return cats;
};

const Actions = ({ d, run }) => {
  const s = d.product.status;
  const deletable = !d.product.ever_active && ["draft", "rejected", "archived"].includes(s);
  return (
    <div className="flex flex-wrap gap-2">
      {["draft", "rejected"].includes(s) && <Button onClick={() => run("submit")} data-testid="product-submit-button">Submit for review</Button>}
      {s === "active" && <Button asChild variant="outline" data-testid="product-view-live"><Link to={`/products/${d.product.slug}`}>View live</Link></Button>}
      {s !== "archived" ? <Button variant="outline" onClick={() => run("archive")} data-testid="product-archive-button">Archive</Button>
        : <Button variant="outline" onClick={() => run("unarchive")} data-testid="product-restore-button">Restore to draft</Button>}
      {deletable && <Button variant="destructive" onClick={() => run("delete")} data-testid="product-delete-button">Delete</Button>}
    </div>
  );
};

const NewProduct = ({ categories, disabled }) => {
  const nav = useNavigate();
  const [error, setError] = useState("");
  const create = async ({ initial_stock, ...body }) => {
    setError("");
    try {
      const r = await api.post("/vendor/products", { ...body, variants: [{ sku: body.sku, price_minor: body.price_minor, initial_stock }] });
      toast.success("Draft created — add images and variants next");
      nav(`/vendor/products/${r.data.product.id}`, { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <div className="rounded-2xl border border-av-line bg-white p-6 md:p-8">
      {categories.length > 0 && <ProductForm isNew categories={categories} onSubmit={create} error={error} disabled={disabled} />}
    </div>
  );
};

export default function ProductEditorPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const categories = useCategories();
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [suspended, setSuspended] = useState(false);
  const load = useCallback(async () => {
    if (id === "new") return;
    try {
      setD((await api.get(`/vendor/products/${id}`)).data);
    } catch {
      setD(false);
    }
  }, [id]);
  useEffect(() => {
    load();
    api.get("/vendor/store").then((r) => setSuspended(r.data.vendor.status !== "active")).catch(() => {});
  }, [load]);
  const saveDetails = async (body) => {
    setError("");
    try {
      const r = await api.patch(`/vendor/products/${id}`, body);
      setD(r.data);
      toast.success(r.data.requeued_for_review ? "Saved — the product is back in review" : "Details saved");
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  const run = async (action) => {
    if (action === "delete" && !window.confirm("Delete this product permanently? This can't be undone.")) return;
    try {
      if (action === "delete") {
        await api.delete(`/vendor/products/${id}`);
        toast.success("Product deleted");
        return nav("/vendor/products");
      }
      setD((await api.post(`/vendor/products/${id}/${action}`)).data);
      toast.success({ submit: "Submitted for review", archive: "Archived", unarchive: "Restored to draft" }[action]);
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  const header = (title, badge) => (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="av-eyebrow"><Link to="/vendor/products" className="hover:underline" data-testid="product-back-link">← Products</Link></p>
        <h1 className="mt-2 text-3xl sm:text-4xl font-bold tracking-tight text-av-ink" data-testid="product-editor-title">{title}</h1></div>
      {badge}
    </div>
  );
  if (id === "new") return <div data-testid="product-editor-page" className="av-container max-w-4xl space-y-6 py-12">{header("New product")}
    {suspended && <StatusAlert tone="error" title="Vendor account suspended" testId="product-suspended-note">Creating products is disabled.</StatusAlert>}
    <NewProduct categories={categories} disabled={suspended} /></div>;
  if (d === false) return <div className="av-container py-24 text-center" data-testid="product-not-found">Product not found.</div>;
  if (!d || !categories.length) return null;
  const p = d.product;
  const locked = suspended || p.status === "archived";
  return (
    <div data-testid="product-editor-page" className="av-container max-w-5xl space-y-6 py-12">
      {header(p.title, <StatusBadge tone={STATUS_TONE[p.status]} testId="product-status-badge">{STATUS_LABEL[p.status]}</StatusBadge>)}
      {p.status === "rejected" && <StatusAlert tone="error" title="Changes requested by reviewer" testId="product-rejection-note">{p.moderation_note}</StatusAlert>}
      {p.status === "pending_review" && <StatusAlert tone="info" title="Waiting for review" testId="product-pending-note">An AfroVending admin will review this product. You can keep editing meanwhile.</StatusAlert>}
      {suspended && <StatusAlert tone="error" title="Vendor account suspended" testId="product-suspended-note">Editing is disabled.</StatusAlert>}
      {!suspended && <Actions d={d} run={run} />}
      <Tabs defaultValue="details">
        <TabsList className="h-auto flex-wrap justify-start gap-1 rounded-full bg-av-sand p-1">
          {[["details", "Details"], ["images", `Images (${d.images.length})`], ["variants", "Variants"], ["inventory", "Inventory"]].map(([v, l]) => (
            <TabsTrigger key={v} value={v} data-testid={`product-tab-${v}`} className="rounded-full px-4 py-2 data-[state=active]:bg-white">{l}</TabsTrigger>
          ))}
        </TabsList>
        <div className="mt-6 rounded-2xl border border-av-line bg-white p-6 md:p-8">
          <TabsContent value="details"><ProductForm key={p.updated_at} product={productFields(p)} categories={categories} onSubmit={saveDetails} disabled={locked} error={error} /></TabsContent>
          <TabsContent value="images"><ImagesManager productId={p.id} images={d.images} onChange={setD} disabled={locked} /></TabsContent>
          <TabsContent value="variants"><VariantsEditor key={p.updated_at} product={{ ...productFields(p), id: p.id }} variants={d.variants} onSaved={setD} disabled={locked} /></TabsContent>
          <TabsContent value="inventory"><InventoryPanel productId={p.id} variants={d.variants} threshold={p.low_stock_threshold} onChanged={load} disabled={locked} /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
