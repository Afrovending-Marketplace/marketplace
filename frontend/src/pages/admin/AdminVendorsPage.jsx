import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";

const TONE = { submitted: "gold", changes_requested: "clay", approved: "success", rejected: "danger" };

const download = async (doc) => {
  const r = await api.get(`/admin/vendor-documents/${doc.id}`, { responseType: "blob" });
  const url = URL.createObjectURL(r.data);
  const a = Object.assign(document.createElement("a"), { href: url, download: doc.filename });
  a.click();
  URL.revokeObjectURL(url);
};

const Review = ({ id, onDone }) => {
  const [d, setD] = useState(null);
  const [note, setNote] = useState("");
  const [docs, setDocs] = useState(false);
  useEffect(() => {
    if (id) {
      api.get(`/admin/vendor-applications/${id}`).then((r) => setD(r.data));
    }
  }, [id]);
  const decide = async (decision) => {
    try {
      await api.post(`/admin/vendor-applications/${id}/decision`, { decision, note, require_documents: docs });
      toast.success(`Application ${{ approve: "approved", reject: "rejected", request_info: "returned for more information" }[decision]}`);
      onDone();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  const a = d?.application;
  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && onDone()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto rounded-2xl bg-av-linen" data-testid="admin-application-dialog">
        <DialogHeader><DialogTitle className="font-serif text-2xl">{a?.business_name || "Application"}</DialogTitle>
          <DialogDescription>Review details and record a decision. The applicant is emailed automatically.</DialogDescription></DialogHeader>
        {a && (
          <div className="space-y-4 text-sm">
            <p><b>Contact:</b> {a.contact_email} {a.contact_phone}</p>
            <p><b>Location:</b> {a.city}, {a.region} {a.country} · <b>Store URL:</b> /store/{a.desired_slug}</p>
            <p><b>Categories:</b> {a.categories.join(", ")}</p>
            <p className="whitespace-pre-line rounded-xl bg-white p-3">{a.description}</p>
            <p><b>Verification:</b> {a.verification_status} · <b>Policy:</b> {d.policy_acceptance ? `${d.policy_acceptance.version} at ${new Date(d.policy_acceptance.accepted_at).toLocaleString()}` : "—"}</p>
            {d.documents.map((doc) => <Button key={doc.id} size="sm" variant="outline" onClick={() => download(doc)} data-testid={`admin-doc-download-${doc.id}`}>Download {doc.filename}</Button>)}
            {["submitted", "under_review"].includes(a.status) ? (
              <>
                <Textarea aria-label="Note to applicant" placeholder="Note to applicant (required for reject / request info)" value={note} onChange={(e) => setNote(e.target.value)} className="bg-white" data-testid="admin-decision-note" />
                <label className="flex items-center gap-2"><Checkbox checked={docs} onCheckedChange={(v) => setDocs(!!v)} data-testid="admin-require-docs" /> Require a verification document</label>
                <div className="flex flex-wrap gap-2">
                  <Button variant="indigo" onClick={() => decide("approve")} data-testid="admin-approve-button">Approve</Button>
                  <Button variant="outline" onClick={() => decide("request_info")} data-testid="admin-request-info-button">Request info</Button>
                  <Button variant="destructive" onClick={() => decide("reject")} data-testid="admin-reject-button">Reject</Button>
                </div>
              </>
            ) : <StatusBadge tone="neutral">{a.status}</StatusBadge>}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default function AdminVendorsPage() {
  const [apps, setApps] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [open, setOpen] = useState(null);
  const load = useCallback(async () => {
    setApps((await api.get("/admin/vendor-applications")).data.data);
    setVendors((await api.get("/admin/vendors")).data.data);
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  const setStatus = async (v, action) => {
    const reason = window.prompt(`Reason to ${action} ${v.name}:`);
    if (!reason) return;
    try {
      await api.post(`/admin/vendors/${v.id}/${action}`, { reason });
      load();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <div data-testid="admin-vendors-page" className="av-container py-12 space-y-10">
      <h1 className="text-4xl font-bold tracking-tight text-av-ink">Vendor management</h1>
      <section><h2 className="mb-4 text-xl font-semibold">Applications</h2>
        <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white" data-testid="admin-application-list">
          {apps.length === 0 && <li className="p-5 text-sm text-av-muted">No applications yet.</li>}
          {apps.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
              <span><b>{a.business_name}</b> <span className="text-sm text-av-muted">/{a.desired_slug}</span></span>
              <span className="flex items-center gap-3"><StatusBadge tone={TONE[a.status] || "gold"}>{a.status.replace("_", " ")}</StatusBadge>
                <Button size="sm" variant="outline" onClick={() => setOpen(a.id)} data-testid={`admin-review-${a.id}`}>Review</Button></span>
            </li>))}
        </ul>
      </section>
      <section><h2 className="mb-4 text-xl font-semibold">Vendors</h2>
        <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white" data-testid="admin-vendor-list">
          {vendors.length === 0 && <li className="p-5 text-sm text-av-muted">No vendors yet.</li>}
          {vendors.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
              <span><b>{v.name}</b> <span className="text-sm text-av-muted">/store/{v.slug}</span></span>
              <span className="flex items-center gap-3"><StatusBadge tone={v.status === "active" ? "success" : "danger"}>{v.status}</StatusBadge>
                <Button size="sm" variant="outline" onClick={() => setStatus(v, v.status === "active" ? "suspend" : "reactivate")} data-testid={`admin-vendor-toggle-${v.id}`}>
                  {v.status === "active" ? "Suspend" : "Reactivate"}</Button></span>
            </li>))}
        </ul>
      </section>
      <Review id={open} onDone={() => { setOpen(null); load(); }} />
    </div>
  );
}
