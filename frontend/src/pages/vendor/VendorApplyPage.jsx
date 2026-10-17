import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Field, FormError } from "@/components/auth/AuthCard";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ImageUpload, uploadFile } from "@/components/vendor/FileUpload";
import { getCategories } from "@/lib/catalog";
import { useAuth } from "@/context/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

const EMPTY = { business_name: "", contact_email: "", contact_phone: "", country: "US", region: "", city: "", categories: [], description: "", desired_slug: "", logo_file_id: null, banner_file_id: null };
const TONE = { draft: "neutral", submitted: "gold", under_review: "gold", changes_requested: "clay", approved: "success", rejected: "danger" };
const TEXT = [["business_name", "Business name"], ["contact_email", "Contact email"], ["contact_phone", "Contact phone"], ["country", "Country code (2 letters)"], ["region", "State / region"], ["city", "City"]];

const StatusPanel = ({ app }) => (
  <div className="space-y-3" data-testid="vendor-application-status">
    <StatusBadge tone={TONE[app.status]} testId="vendor-application-status-badge">{app.status.replace("_", " ")}</StatusBadge>
    {app.status === "submitted" && <StatusAlert tone="info" title="Application under review">We'll email you when a decision is made.</StatusAlert>}
    {app.status === "changes_requested" && <StatusAlert tone="warning" title="More information requested">{app.admin_note}</StatusAlert>}
    {app.status === "rejected" && <StatusAlert tone="error" title="Application not approved">{app.admin_note}</StatusAlert>}
    {app.status === "approved" && <Button asChild data-testid="go-vendor-dashboard"><Link to="/vendor/dashboard">Open vendor dashboard</Link></Button>}
  </div>
);

const DocUpload = ({ docs, reload }) => (
  <div className="space-y-2 rounded-xl border border-av-gold/40 bg-av-gold-light p-4">
    <p className="text-sm font-semibold text-av-gold-deep">Verification document requested</p>
    <p className="text-xs text-av-gold-deep">Upload a business registration or ID (PDF/JPG/PNG, max 10 MB). Only authorised administrators can view it.</p>
    <input type="file" accept="application/pdf,image/png,image/jpeg" data-testid="vendor-doc-upload" aria-label="Verification document"
      onChange={async (e) => { try { await uploadFile(e.target.files[0], "verification_doc"); toast.success("Document uploaded"); reload(); } catch (err) { toast.error(getErrorMessage(err)); } }} />
    <ul className="text-xs text-av-ink" data-testid="vendor-doc-list">{docs.map((d) => <li key={d.id}>{d.filename}</li>)}</ul>
  </div>
);

export default function VendorApplyPage() {
  const { user } = useAuth();
  const [state, setState] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [accept, setAccept] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const { data } = await api.get("/vendor/application");
    setState(data);
    if (data.application) setForm(Object.fromEntries(Object.keys(EMPTY).map((k) => [k, data.application[k] ?? EMPTY[k]])));
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  if (!state) return null;
  const app = state.application;
  const editable = !app || ["draft", "changes_requested"].includes(app.status);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const toggleCat = (slug) => setForm({ ...form, categories: form.categories.includes(slug) ? form.categories.filter((c) => c !== slug) : [...form.categories, slug] });
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.put("/vendor/application", form);
      await api.post("/vendor/application/submit", { accept_policy: accept, policy_version: state.policy_version });
      toast.success("Application submitted");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <div data-testid="vendor-apply-page" className="av-container max-w-3xl py-12 space-y-8">
      <div><p className="av-eyebrow">Become a vendor</p><h1 className="mt-2 text-4xl sm:text-5xl font-bold tracking-tight text-av-ink">Vendor application</h1></div>
      {!user.email_verified && <StatusAlert tone="warning" title="Verify your email first" testId="vendor-apply-unverified">Check your inbox, or resend the link from your account.</StatusAlert>}
      {app && <StatusPanel app={app} />}
      {app?.verification_status === "requested" && <DocUpload docs={state.documents} reload={load} />}
      {editable && (
        <form onSubmit={submit} className="grid gap-5 rounded-2xl border border-av-line bg-white p-6 md:p-8 sm:grid-cols-2" data-testid="vendor-application-form">
          <div className="sm:col-span-2"><FormError message={error} testId="vendor-application-error" /></div>
          {TEXT.map(([k, l]) => <Field key={k} id={`va-${k}`} label={l} value={form[k]} onChange={set(k)} testId={`vendor-${k.replace("_", "-")}-input`} />)}
          <div className="sm:col-span-2 space-y-2">
            <Label htmlFor="va-slug">Store URL</Label>
            <div className="flex items-center gap-2 text-sm text-av-muted">afrovending.com/store/<input id="va-slug" value={form.desired_slug} onChange={set("desired_slug")} data-testid="vendor-slug-input" className="h-11 flex-1 rounded-md border border-av-line px-3 text-av-ink" /></div>
          </div>
          <fieldset className="sm:col-span-2"><legend className="mb-2 text-sm font-medium">Product categories</legend>
            <div className="flex flex-wrap gap-2">{getCategories().map((c) => (
              <button type="button" key={c.slug} onClick={() => toggleCat(c.slug)} aria-pressed={form.categories.includes(c.slug)} data-testid={`vendor-category-${c.slug}`}
                className={`rounded-full border px-3 py-1.5 text-sm ${form.categories.includes(c.slug) ? "border-av-ink bg-av-ink text-av-linen" : "border-av-line bg-white"}`}>{c.name}</button>))}</div>
          </fieldset>
          <div className="sm:col-span-2 space-y-2"><Label htmlFor="va-desc">Business description (min 30 characters)</Label>
            <Textarea id="va-desc" rows={5} value={form.description} onChange={set("description")} className="bg-white" data-testid="vendor-description-input" /></div>
          <ImageUpload label="Business logo" purpose="logo" fileId={form.logo_file_id} onChange={(f) => setForm({ ...form, logo_file_id: f.id })} testId="vendor-logo-upload" />
          <ImageUpload label="Store banner" purpose="banner" fileId={form.banner_file_id} onChange={(f) => setForm({ ...form, banner_file_id: f.id })} testId="vendor-banner-upload" />
          <label className="sm:col-span-2 flex items-start gap-2 text-sm">
            <Checkbox checked={accept} onCheckedChange={(v) => setAccept(!!v)} data-testid="vendor-policy-checkbox" className="mt-0.5" />
            <span>I accept the <Link to="/vendor-agreement" target="_blank" className="font-semibold text-av-clay underline">Vendor Agreement</Link> (version {state.policy_version}, draft pending legal review).</span>
          </label>
          <Button type="submit" size="lg" className="sm:col-span-2" disabled={!user.email_verified} data-testid="vendor-application-submit">Submit application</Button>
        </form>
      )}
    </div>
  );
}
