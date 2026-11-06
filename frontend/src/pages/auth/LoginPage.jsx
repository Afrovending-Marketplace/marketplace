import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { AuthCard, Field, FormError } from "@/components/auth/AuthCard";
import { useAuth } from "@/context/AuthContext";
import { getErrorMessage } from "@/lib/api";

const safeNext = (n) => (n && n.startsWith("/") && !n.startsWith("//") ? n : "/account");

export default function LoginPage() {
  const { user, login } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const next = safeNext(params.get("next"));
  if (user) return <Navigate to={next} replace />;

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(form.email, form.password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard testId="login-page" title="Welcome back" description="Sign in to your AfroVending account."
      footer={<>New to AfroVending? <Link to="/register" data-testid="login-register-link" className="font-semibold text-av-clay hover:underline">Create an account</Link></>}>
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <FormError message={error} testId="login-error" />
        {params.get("activated") && <p className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800" data-testid="login-activated-notice">Your account is activated. Sign in with your new password.</p>}
        <Field id="login-email" label="Email" type="email" autoComplete="email" required value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })} testId="login-email-input" />
        <Field id="login-password" label="Password" type="password" autoComplete="current-password" required value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} testId="login-password-input" />
        <div className="flex flex-wrap justify-between gap-2">
          <Link to="/activate" data-testid="login-activate-link" className="text-sm text-av-clay hover:underline">From the old AfroVending site? Activate account</Link>
          <Link to="/forgot-password" data-testid="login-forgot-password-link" className="text-sm text-av-clay hover:underline">Forgot password?</Link>
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={busy} data-testid="login-submit-button">{busy ? "Signing in…" : "Sign in"}</Button>
      </form>
    </AuthCard>
  );
}
