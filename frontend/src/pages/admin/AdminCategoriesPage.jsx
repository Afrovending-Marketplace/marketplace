import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";

const CategoryRow = ({ c, child, onChanged }) => {
  const [name, setName] = useState(c.name);
  const [sort, setSort] = useState(String(c.sort_order));
  const call = async (fn, msg) => {
    try {
      await fn();
      toast.success(msg);
      onChanged();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  const save = (status = c.status) => call(() => api.patch(`/admin/categories/${c.id}`, { name, blurb: c.blurb || "", sort_order: parseInt(sort, 10) || 0, status }), "Category saved");
  const remove = () => window.confirm(`Delete ${c.name}?`) && call(() => api.delete(`/admin/categories/${c.id}`), "Category deleted");
  return (
    <li className={`flex flex-wrap items-center gap-3 p-3 ${child ? "pl-10 bg-av-linen/40" : ""}`} data-testid={`admin-category-${c.slug}`}>
      <Input aria-label="Name" value={name} onChange={(e) => setName(e.target.value)} className="h-9 w-48" data-testid={`admin-category-name-${c.slug}`} />
      <Input aria-label="Sort order" type="number" value={sort} onChange={(e) => setSort(e.target.value)} className="h-9 w-20" data-testid={`admin-category-sort-${c.slug}`} />
      <span className="text-xs text-av-muted">/{c.slug} · {c.product_count} products</span>
      <StatusBadge tone={c.status === "active" ? "success" : "neutral"} testId={`admin-category-status-${c.slug}`}>{c.status}</StatusBadge>
      <span className="ml-auto flex gap-2">
        <Button size="sm" onClick={() => save()} data-testid={`admin-category-save-${c.slug}`}>Save</Button>
        <Button size="sm" variant="outline" onClick={() => save(c.status === "active" ? "hidden" : "active")} data-testid={`admin-category-toggle-${c.slug}`}>{c.status === "active" ? "Hide" : "Show"}</Button>
        <Button size="sm" variant="ghost" className="text-red-700" onClick={remove} data-testid={`admin-category-delete-${c.slug}`}>Delete</Button>
      </span>
    </li>
  );
};

const NewCategory = ({ tops, onCreated }) => {
  const [name, setName] = useState("");
  const [parent, setParent] = useState("none");
  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/admin/categories", { name, parent_slug: parent === "none" ? null : parent });
      setName("");
      toast.success("Category created");
      onCreated();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <form onSubmit={create} className="flex flex-wrap items-end gap-3 rounded-2xl border border-av-line bg-white p-4" data-testid="admin-category-create-form">
      <Input aria-label="New category name" placeholder="New category name" value={name} onChange={(e) => setName(e.target.value)} className="h-10 w-56" required data-testid="admin-category-new-name" />
      <Select value={parent} onValueChange={setParent}>
        <SelectTrigger className="h-10 w-56 bg-white" data-testid="admin-category-new-parent"><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value="none">Top-level category</SelectItem>{tops.map((t) => <SelectItem key={t.slug} value={t.slug}>Under {t.name}</SelectItem>)}</SelectContent>
      </Select>
      <Button type="submit" data-testid="admin-category-create-button">Add category</Button>
    </form>
  );
};

export default function AdminCategoriesPage() {
  const [cats, setCats] = useState([]);
  const load = useCallback(async () => {
    setCats((await api.get("/admin/categories")).data.data);
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  const tops = cats.filter((c) => !c.parent_id);
  return (
    <div data-testid="admin-categories-page" className="av-container max-w-5xl space-y-6 py-12">
      <h1 className="text-4xl font-bold tracking-tight text-av-ink">Categories</h1>
      <p className="text-sm text-av-muted">URLs (slugs) are permanent. Hide a category instead of deleting it once products use it; categories with live products can't be hidden.</p>
      <NewCategory tops={tops} onCreated={load} />
      <ul className="divide-y divide-av-line overflow-hidden rounded-2xl border border-av-line bg-white" data-testid="admin-category-list">
        {tops.map((t) => [
          <CategoryRow key={`${t.id}-${t.updated_at}`} c={t} onChanged={load} />,
          ...cats.filter((k) => k.parent_id === t.id).map((k) => <CategoryRow key={`${k.id}-${k.updated_at}`} c={k} child onChanged={load} />),
        ])}
      </ul>
    </div>
  );
}
