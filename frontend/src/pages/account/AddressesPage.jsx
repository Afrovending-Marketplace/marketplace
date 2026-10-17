import { useCallback, useEffect, useState } from "react";
import { Plus, Star, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FormError } from "@/components/auth/AuthCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";

const EMPTY = { label: "", full_name: "", line1: "", line2: "", city: "", region: "", postal_code: "", country: "US", phone: "", is_default: false };
const FIELDS = [["label", "Label (e.g. Home)"], ["full_name", "Full name"], ["line1", "Address line 1"], ["line2", "Address line 2"],
  ["city", "City"], ["region", "State / region"], ["postal_code", "Postal code"], ["country", "Country code (2 letters)"], ["phone", "Phone"]];

const AddressDialog = ({ open, onClose, initial, onSaved }) => {
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  useEffect(() => {
    setForm(initial || EMPTY);
    setError("");
  }, [initial, open]);
  const save = async (e) => {
    e.preventDefault();
    try {
      const payload = Object.fromEntries(Object.keys(EMPTY).map((k) => [k, form[k]]));
      if (initial?.id) await api.patch(`/account/addresses/${initial.id}`, payload);
      else await api.post("/account/addresses", payload);
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto rounded-2xl bg-av-linen" data-testid="address-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-2xl">{initial?.id ? "Edit address" : "Add address"}</DialogTitle>
          <DialogDescription>Used for delivery once checkout opens.</DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2"><FormError message={error} testId="address-error" /></div>
          {FIELDS.map(([k, label]) => (
            <Field key={k} id={`addr-${k}`} label={label} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} testId={`address-${k.replace("_", "-")}-input`} />
          ))}
          <label className="flex items-center gap-2 text-sm sm:col-span-2">
            <Checkbox checked={form.is_default} onCheckedChange={(v) => setForm({ ...form, is_default: !!v })} data-testid="address-default-checkbox" /> Make this my default address
          </label>
          <Button type="submit" className="sm:col-span-2" data-testid="address-save-button">Save address</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default function AddressesPage() {
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const load = useCallback(async () => setItems((await api.get("/account/addresses")).data.data), []);
  useEffect(() => {
    load();
  }, [load]);
  const remove = async (id) => {
    if (!window.confirm("Delete this address?")) return;
    await api.delete(`/account/addresses/${id}`);
    toast.success("Address removed");
    load();
  };
  const makeDefault = async (a) => {
    await api.patch(`/account/addresses/${a.id}`, { ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, a[k]])), is_default: true });
    load();
  };
  return (
    <div data-testid="addresses-page" className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="font-sans text-xl font-semibold text-av-ink">Address book</h2>
        <Button onClick={() => { setEditing(null); setOpen(true); }} data-testid="add-address-button"><Plus /> Add address</Button>
      </div>
      {items.length === 0 && <p data-testid="addresses-empty" className="rounded-2xl border border-dashed border-av-line p-8 text-center text-av-muted">No saved addresses yet.</p>}
      <div className="grid gap-4 md:grid-cols-2">
        {items.map((a) => (
          <article key={a.id} data-testid={`address-card-${a.id}`} className="rounded-2xl border border-av-line bg-white p-5">
            <div className="flex items-center justify-between gap-2">
              <p className="font-semibold text-av-ink">{a.label || "Address"}</p>
              {a.is_default && <StatusBadge tone="success" testId="address-default-badge">Default</StatusBadge>}
            </div>
            <p className="mt-2 text-sm text-av-ink/80">{a.full_name}<br />{a.line1}{a.line2 && <>, {a.line2}</>}<br />{a.city}{a.region && `, ${a.region}`} {a.postal_code}<br />{a.country}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => { setEditing(a); setOpen(true); }} data-testid={`address-edit-${a.id}`}><Pencil /> Edit</Button>
              {!a.is_default && <Button size="sm" variant="ghost" onClick={() => makeDefault(a)} data-testid={`address-make-default-${a.id}`}><Star /> Make default</Button>}
              <Button size="sm" variant="ghost" onClick={() => remove(a.id)} data-testid={`address-delete-${a.id}`} className="text-red-700"><Trash2 /> Delete</Button>
            </div>
          </article>
        ))}
      </div>
      <AddressDialog open={open} initial={editing} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); toast.success("Address saved"); load(); }} />
    </div>
  );
}
