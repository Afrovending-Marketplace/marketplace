import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

export default function AdminMfaPage() {
  const [s, setS] = useState(null);
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");
  const { reload } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const done = async () => {
    await reload();
    nav(params.get("next") || "/admin", { replace: true });
  };
  useEffect(() => {
    api.get("/auth/mfa").then((r) => setS(r.data));
  }, []);
  const submit = async () => {
    try {
      await api.post(s.enrolled ? "/auth/mfa/verify" : "/auth/mfa/enable", { code });
      toast.success("Verified");
      done();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  if (!s) return null;
  return (
    <div className="av-container max-w-md space-y-5 py-16" data-testid="admin-mfa-page">
      <h1 className="text-3xl font-bold text-av-ink">Two-step sign-in</h1>
      {!s.enrolled && !setup && <><p className="text-sm text-av-muted">Admin tools need an authenticator app (Google Authenticator, 1Password, Authy…).</p>
        <Button onClick={async () => setSetup((await api.post("/auth/mfa/setup")).data)} data-testid="mfa-start">Set up authenticator</Button></>}
      {setup && <div className="space-y-2 rounded-xl bg-av-sand p-4 text-sm" data-testid="mfa-setup">
        <p>Add this key to your authenticator app, then enter the 6-digit code it shows.</p>
        <code className="block break-all rounded bg-white p-2 font-mono" data-testid="mfa-secret">{setup.secret}</code>
        <a className="text-xs underline" href={setup.otpauth_uri} data-testid="mfa-uri">Open in authenticator app</a></div>}
      {(s.enrolled || setup) && <div className="flex gap-2">
        <Input inputMode="numeric" maxLength={6} placeholder="123456" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} data-testid="mfa-code" />
        <Button disabled={code.length !== 6} onClick={submit} data-testid="mfa-submit">Verify</Button></div>}
    </div>
  );
}
