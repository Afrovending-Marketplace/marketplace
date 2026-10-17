import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { AuthCard, Field, FormError } from "@/components/auth/AuthCard";
import { useAuth } from "@/context/AuthContext";
import { getErrorMessage } from "@/lib/api";

const pwProblem = (p) => (p.length < 10 || !/[A-Za-z]/.test(p) || !/\d/.test(p) ? "At least 10 characters with a letter and a number." : "");

export default function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "" });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/account" replace />;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    const errs = {};
    if (!form.name.trim()) errs.name = "Enter your name.";
    if (!/^\S+@\S+\.\S+$/.test(form.email)) errs.email = "Enter a valid email address.";
    if (pwProblem(form.password)) errs.password = pwProblem(form.password);
    if (form.confirm !== form.password) errs.confirm = "Passwords don't match.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setError("");
    try {
      const data = await register({ name: form.name, email: form.email, password: form.password });
      toast.success(data.verification_email_sent ? "Account created — check your inbox to verify your email." : "Account created. We couldn't send the verification email yet; you can resend it from your account.");
      navigate("/account", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard testId="register-page" title="Create your account" description="One account to shop, save addresses and — later — apply to sell."
      footer={<>Already have an account? <Link to="/login" data-testid="register-login-link" className="font-semibold text-av-clay hover:underline">Sign in</Link></>}>
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <FormError message={error} testId="register-error" />
        <Field id="reg-name" label="Full name" autoComplete="name" value={form.name} onChange={set("name")} error={errors.name} testId="register-name-input" />
        <Field id="reg-email" label="Email" type="email" autoComplete="email" value={form.email} onChange={set("email")} error={errors.email} testId="register-email-input" />
        <Field id="reg-password" label="Password" type="password" autoComplete="new-password" value={form.password} onChange={set("password")}
          error={errors.password} testId="register-password-input" />
        <Field id="reg-confirm" label="Confirm password" type="password" autoComplete="new-password" value={form.confirm} onChange={set("confirm")}
          error={errors.confirm} testId="register-password-confirm-input" />
        <p className="text-xs text-av-muted">By creating an account you agree to our <Link to="/terms" className="underline">Terms</Link> and <Link to="/privacy" className="underline">Privacy Policy</Link> (drafts pending legal review).</p>
        <Button type="submit" size="lg" className="w-full" disabled={busy} data-testid="register-submit-button">{busy ? "Creating account…" : "Create account"}</Button>
      </form>
    </AuthCard>
  );
}
