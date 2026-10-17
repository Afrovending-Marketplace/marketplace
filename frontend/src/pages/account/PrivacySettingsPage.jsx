import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Field, FormError } from "@/components/auth/AuthCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAuth, isAdmin } from "@/context/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

const TYPES = [["data_export", "Export a copy of my data"], ["data_deletion", "Delete my data"], ["data_correction", "Correct my data"]];

const PrivacyRequests = () => {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ request_type: "data_export", details: "" });
  const [error, setError] = useState("");
  const load = useCallback(async () => setItems((await api.get("/account/privacy-requests")).data.data), []);
  useEffect(() => {
    load();
  }, [load]);
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/account/privacy-requests", form);
      toast.success("Request submitted. Our team will follow up by email.");
      setForm({ ...form, details: "" });
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <section className="rounded-2xl border border-av-line bg-white p-6 md:p-8">
      <h2 className="font-sans text-xl font-semibold text-av-ink">Privacy requests</h2>
      <p className="mt-1 text-sm text-av-muted">Ask us to export, delete or correct your personal data. Requests are reviewed by our team.</p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <FormError message={error} testId="privacy-request-error" />
        <Select value={form.request_type} onValueChange={(v) => setForm({ ...form, request_type: v })}>
          <SelectTrigger aria-label="Request type" className="h-11 bg-white" data-testid="privacy-request-type-select"><SelectValue /></SelectTrigger>
          <SelectContent>{TYPES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
        </Select>
        <Textarea aria-label="Details" placeholder="Details (optional)" value={form.details} onChange={(e) => setForm({ ...form, details: e.target.value })} className="bg-white" data-testid="privacy-request-details-input" />
        <Button type="submit" data-testid="privacy-request-submit-button">Submit request</Button>
      </form>
      <ul className="mt-6 divide-y divide-av-line" data-testid="privacy-request-list">
        {items.map((r) => (
          <li key={r.id} className="flex items-center justify-between py-3 text-sm">
            <span>{TYPES.find(([v]) => v === r.request_type)?.[1]}</span>
            <StatusBadge tone={r.status === "completed" ? "success" : "gold"}>{r.status.replace("_", " ")}</StatusBadge>
          </li>
        ))}
      </ul>
    </section>
  );
};

const Deactivate = () => {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  if (isAdmin(user)) return null;
  const confirm = async (e) => {
    e.preventDefault();
    try {
      await api.post("/account/deactivate", { password });
      setUser(false);
      toast.success("Your account was deactivated.");
      navigate("/", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <section className="rounded-2xl border border-red-200 bg-red-50/40 p-6 md:p-8">
      <h2 className="font-sans text-xl font-semibold text-av-ink">Deactivate account</h2>
      <p className="mt-1 text-sm text-av-muted">You'll be signed out everywhere and won't be able to sign in. Contact support to restore it.</p>
      <AlertDialog>
        <AlertDialogTrigger asChild><Button variant="destructive" className="mt-5" data-testid="deactivate-account-button">Deactivate my account</Button></AlertDialogTrigger>
        <AlertDialogContent className="rounded-2xl bg-av-linen">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-serif text-2xl">Deactivate your account?</AlertDialogTitle>
            <AlertDialogDescription>Enter your password to confirm.</AlertDialogDescription>
          </AlertDialogHeader>
          <form onSubmit={confirm} className="space-y-4">
            <FormError message={error} testId="deactivate-error" />
            <Field id="deact-pw" label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} testId="deactivate-password-input" />
            <AlertDialogFooter className="gap-2">
              <AlertDialogCancel data-testid="deactivate-cancel-button">Cancel</AlertDialogCancel>
              <Button type="submit" variant="destructive" data-testid="deactivate-confirm-button">Deactivate</Button>
            </AlertDialogFooter>
          </form>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
};

export default function PrivacySettingsPage() {
  return <div className="space-y-6" data-testid="privacy-settings-page"><PrivacyRequests /><Deactivate /></div>;
}
