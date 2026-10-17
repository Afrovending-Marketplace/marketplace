import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, FormError } from "@/components/auth/AuthCard";
import { useAuth } from "@/context/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

const Card = ({ title, children }) => (
  <section className="rounded-2xl border border-av-line bg-white p-6 md:p-8">
    <h2 className="font-sans text-xl font-semibold text-av-ink">{title}</h2>
    <div className="mt-6">{children}</div>
  </section>
);

const ProfileForm = () => {
  const { user, setUser } = useAuth();
  const [form, setForm] = useState({ name: user.name, phone: user.phone || "" });
  const [error, setError] = useState("");
  const save = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setUser((await api.patch("/account/profile", form)).data.user);
      toast.success("Profile saved");
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <form onSubmit={save} className="grid gap-5 sm:grid-cols-2">
      <div className="sm:col-span-2"><FormError message={error} testId="profile-error" /></div>
      <Field id="pf-name" label="Full name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} testId="profile-name-input" />
      <Field id="pf-phone" label="Phone (optional)" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} testId="profile-phone-input" />
      <Field id="pf-email" label="Email" value={user.email} disabled testId="profile-email-input" />
      <div className="sm:col-span-2"><Button type="submit" data-testid="profile-save-button">Save profile</Button></div>
    </form>
  );
};

const PasswordForm = () => {
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [error, setError] = useState("");
  const save = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/change-password", form);
      setForm({ current_password: "", new_password: "" });
      toast.success("Password changed. Other devices were signed out.");
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <form onSubmit={save} className="grid gap-5 sm:grid-cols-2">
      <div className="sm:col-span-2"><FormError message={error} testId="password-change-error" /></div>
      <Field id="cp-current" label="Current password" type="password" autoComplete="current-password" value={form.current_password}
        onChange={(e) => setForm({ ...form, current_password: e.target.value })} testId="current-password-input" />
      <Field id="cp-new" label="New password" type="password" autoComplete="new-password" value={form.new_password}
        onChange={(e) => setForm({ ...form, new_password: e.target.value })} testId="new-password-input" />
      <div className="sm:col-span-2"><Button type="submit" variant="indigo" data-testid="change-password-button">Change password</Button></div>
    </form>
  );
};

export default function ProfilePage() {
  return (
    <div className="space-y-6" data-testid="profile-page">
      <Card title="Profile"><ProfileForm /></Card>
      <Card title="Password"><PasswordForm /></Card>
    </div>
  );
}
