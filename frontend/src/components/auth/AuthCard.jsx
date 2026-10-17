import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusAlert } from "@/components/common/StatusAlert";

export const AuthCard = ({ title, description, children, footer, testId }) => (
  <section data-testid={testId} className="mud-pattern">
    <div className="av-container grid min-h-[70vh] place-items-center py-14">
      <div className="w-full max-w-md rounded-[1.5rem] border border-av-line bg-white p-6 shadow-xl shadow-av-indigo/5 sm:p-10">
        <div className="kente-strip mb-6 h-1 w-16 rounded-full" aria-hidden="true" />
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-av-ink">{title}</h1>
        {description && <p className="mt-2 text-sm text-av-muted">{description}</p>}
        <div className="mt-8">{children}</div>
        {footer && <div className="mt-6 border-t border-av-line pt-5 text-sm text-av-muted">{footer}</div>}
      </div>
    </div>
  </section>
);

export const Field = ({ id, label, error, testId, type = "text", ...props }) => {
  const [show, setShow] = useState(false);
  const isPw = type === "password";
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input id={id} type={isPw && show ? "text" : type} data-testid={testId} aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined} className="h-11 bg-white pr-11" {...props} />
        {isPw && (
          <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}
            data-testid={`${testId}-toggle`} className="absolute right-3 top-1/2 -translate-y-1/2 text-av-muted hover:text-av-ink">
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
      {error && <p id={`${id}-error`} className="text-xs text-red-700">{error}</p>}
    </div>
  );
};

export const FormError = ({ message, testId = "auth-error" }) =>
  message ? <StatusAlert tone="error" title={message} testId={testId} /> : null;
