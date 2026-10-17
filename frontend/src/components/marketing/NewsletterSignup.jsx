import { useState } from "react";
import { Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SHELL } from "@/constants/testIds";

const EMAIL_RE = /^\S+@\S+\.\S+$/;

export const NewsletterSignup = () => {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const onSubmit = (e) => {
    e.preventDefault();
    if (!EMAIL_RE.test(email)) {
      setError("Enter a valid email address.");
      return;
    }
    setError("");
    setSubmitted(true);
  };

  return (
    <div className="grid gap-6 md:grid-cols-2 md:items-center">
      <div>
        <h2 className="text-2xl sm:text-3xl font-semibold text-av-linen">Stories, makers and new arrivals.</h2>
        <p className="mt-2 text-sm text-av-linen/70">Newsletter preview — sign-up is not connected to an email service yet.</p>
      </div>
      <form onSubmit={onSubmit} noValidate className="space-y-2">
        <div className="flex flex-col gap-2 sm:flex-row">
          <label htmlFor="newsletter-email" className="sr-only">Email address</label>
          <div className="relative flex-1">
            <Mail className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-av-muted" />
            <Input id="newsletter-email" type="email" value={email} onChange={(e) => { setEmail(e.target.value); setSubmitted(false); }}
              placeholder="you@example.com" aria-invalid={!!error} aria-describedby="newsletter-msg"
              className="h-12 rounded-full bg-white pl-11 text-av-ink" data-testid={SHELL.newsletterEmail} />
          </div>
          <Button type="submit" size="lg" variant="gold" data-testid={SHELL.newsletterSubmit}>Notify me</Button>
        </div>
        <div id="newsletter-msg" aria-live="polite" className="min-h-5 text-sm">
          {error && <p data-testid={SHELL.newsletterError} className="text-red-300">{error}</p>}
          {submitted && (
            <p data-testid={SHELL.newsletterResult} className="text-av-gold">
              Thanks! Email sign-up isn't live yet, so nothing was saved or sent.
            </p>
          )}
        </div>
      </form>
    </div>
  );
};
