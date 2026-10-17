import { useState } from "react";
import { Mail, Building2, Globe, MapPin } from "lucide-react";
import { PageHero } from "@/components/common/PageHero";
import { StatusAlert } from "@/components/common/StatusAlert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/auth/AuthCard";
import { BRAND } from "@/config/site";
import { api, getErrorMessage } from "@/lib/api";

const EMAIL_RE = /^\S+@\S+\.\S+$/;
const EMPTY = { name: "", email: "", subject: "", message: "" };

const validate = (f) => ({
  ...(f.name.trim() ? {} : { name: "Enter your name." }),
  ...(EMAIL_RE.test(f.email) ? {} : { email: "Enter a valid email address." }),
  ...(f.subject.trim() ? {} : { subject: "Enter a subject." }),
  ...(f.message.trim().length >= 10 ? {} : { message: "Message must be at least 10 characters." }),
});

const INFO = [
  [Building2, "Company", BRAND.legalName],
  [Globe, "Website", <a key="w" href={BRAND.website} className="hover:underline">www.afrovending.com</a>],
  [MapPin, "Location", BRAND.location],
  [Mail, "Support email", <a key="e" href={`mailto:${BRAND.email}`} data-testid="contact-support-email" className="font-semibold text-av-clay hover:underline">{BRAND.email}</a>],
];

export default function ContactPage() {
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const onSubmit = async (e) => {
    e.preventDefault();
    const errs = validate(form);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      await api.post("/contact", form);
      setResult({ tone: "success", title: "Message sent", text: `Thanks — your message was delivered to ${BRAND.email}. We'll reply by email.` });
      setForm(EMPTY);
    } catch (err) {
      setResult({ tone: "error", title: "Message not sent", text: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div data-testid="contact-page">
      <PageHero eyebrow="Contact us" title="We'd love to hear from you." crumbs={[{ label: "Home", to: "/" }, { label: "Contact" }]}
        description="Questions about shopping, selling or partnerships? Send us a message." />
      <div className="av-container grid gap-10 py-14 lg:grid-cols-12 lg:py-20">
        <aside className="lg:col-span-4 space-y-3">
          {INFO.map(([Icon, label, value]) => (
            <div key={label} className="flex gap-3 rounded-2xl border border-av-line bg-white p-5">
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-av-clay" />
              <div><p className="text-xs uppercase tracking-wider text-av-muted">{label}</p><p className="text-sm text-av-ink">{value}</p></div>
            </div>
          ))}
        </aside>
        <form onSubmit={onSubmit} noValidate data-testid="contact-form" className="lg:col-span-8 grid gap-5 rounded-2xl border border-av-line bg-white p-6 md:p-8 sm:grid-cols-2">
          <Field id="c-name" label="Name" value={form.name} onChange={set("name")} error={errors.name} testId="contact-name-input" />
          <Field id="c-email" label="Email" type="email" value={form.email} onChange={set("email")} error={errors.email} testId="contact-email-input" />
          <div className="sm:col-span-2"><Field id="c-subject" label="Subject" value={form.subject} onChange={set("subject")} error={errors.subject} testId="contact-subject-input" /></div>
          <div className="space-y-2 sm:col-span-2"><Label htmlFor="c-message">Message</Label>
            <Textarea id="c-message" rows={6} className="bg-white" value={form.message} onChange={set("message")} aria-invalid={!!errors.message}
              aria-describedby={errors.message ? "c-message-error" : undefined} data-testid="contact-message-input" />
            {errors.message && <p id="c-message-error" data-testid="contact-error-message" className="text-xs text-red-700">{errors.message}</p>}</div>
          <div className="sm:col-span-2 space-y-4">
            <Button type="submit" disabled={busy} data-testid="contact-submit-button">{busy ? "Sending…" : "Send message"}</Button>
            {result && <StatusAlert tone={result.tone} title={result.title} testId="contact-result">{result.text}</StatusAlert>}
          </div>
        </form>
      </div>
    </div>
  );
}
