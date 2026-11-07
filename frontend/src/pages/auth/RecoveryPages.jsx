import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { AuthCard, Field, FormError } from "@/components/auth/AuthCard";
import { StatusAlert } from "@/components/common/StatusAlert";
import { useAuth } from "@/context/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

export const ForgotPasswordPage = () => {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setDone((await api.post("/auth/forgot-password", { email })).data.message);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <AuthCard testId="forgot-password-page" title="Reset your password" description="Enter your account email and we'll send a secure reset link."
      footer={<Link to="/login" data-testid="forgot-back-login-link" className="font-semibold text-av-clay hover:underline">Back to sign in</Link>}>
      {done ? <StatusAlert tone="success" title="Check your inbox" testId="forgot-password-result">{done}</StatusAlert> : (
        <form onSubmit={onSubmit} className="space-y-5">
          <FormError message={error} testId="forgot-password-error" />
          <Field id="fp-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} testId="forgot-password-email-input" />
          <Button type="submit" size="lg" className="w-full" data-testid="forgot-password-submit-button">Send reset link</Button>
        </form>
      )}
    </AuthCard>
  );
};

export const ResetPasswordPage = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [pw, setPw] = useState({ password: "", confirm: "" });
  const [error, setError] = useState("");
  const token = params.get("token");
  if (!token) {
    return (
      <AuthCard testId="reset-password-page" title="Reset link missing">
        <StatusAlert tone="error" title="This reset link is invalid or incomplete." testId="reset-password-missing-token">Request a new link from the sign-in page.</StatusAlert>
        <Button asChild className="mt-6"><Link to="/forgot-password">Request a new link</Link></Button>
      </AuthCard>
    );
  }
  const onSubmit = async (e) => {
    e.preventDefault();
    if (pw.password !== pw.confirm) return setError("Passwords don't match.");
    setError("");
    try {
      await api.post("/auth/reset-password", { token, password: pw.password });
      setUser(false);
      navigate("/login?reset=1", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  return (
    <AuthCard testId="reset-password-page" title="Choose a new password" description="Use at least 10 characters with a letter and a number. All devices will be signed out.">
      <form onSubmit={onSubmit} className="space-y-5">
        <FormError message={error} testId="reset-password-error" />
        <Field id="rp-pw" label="New password" type="password" autoComplete="new-password" value={pw.password} onChange={(e) => setPw({ ...pw, password: e.target.value })} testId="reset-password-input" />
        <Field id="rp-confirm" label="Confirm new password" type="password" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} testId="reset-password-confirm-input" />
        <Button type="submit" size="lg" className="w-full" data-testid="reset-password-submit-button">Update password</Button>
      </form>
    </AuthCard>
  );
};

export const VerifyEmailPage = () => {
  const [params] = useSearchParams();
  const { reload } = useAuth();
  const [state, setState] = useState({ status: "loading", message: "" });
  const ran = useRef(false);
  useEffect(() => {
    if (ran.current) {
      return;
    }
    ran.current = true;
    api.post("/auth/verify-email", { token: params.get("token") || "" })
      .then(() => { setState({ status: "ok", message: "" }); reload(); })
      .catch((err) => setState({ status: "error", message: getErrorMessage(err) }));
  }, [params, reload]);
  return (
    <AuthCard testId="verify-email-page" title="Email verification">
      {state.status === "loading" && <p className="text-av-muted">Verifying…</p>}
      {state.status === "ok" && <StatusAlert tone="success" title="Your email is verified" testId="verify-email-success">You're all set.</StatusAlert>}
      {state.status === "error" && <StatusAlert tone="error" title={state.message} testId="verify-email-error">Sign in and resend the verification email from your account.</StatusAlert>}
      <Button asChild className="mt-6" data-testid="verify-email-continue"><Link to="/account">Go to my account</Link></Button>
    </AuthCard>
  );
};
