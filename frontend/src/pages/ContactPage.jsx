import { useState } from "react";
import { Mail, MessageCircle } from "lucide-react";
import { PageHero } from "@/components/common/PageHero";
import { StatusAlert } from "@/components/common/StatusAlert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const EMAIL_RE = /^\S+@\S+\.\S+$/;
const field = "h-11 bg-white";

const validate = (f) => ({
  ...(f.name.trim() ? {} : { name: "Enter your name." }),
  ...(EMAIL_RE.test(f.email) ? {} : { email: "Enter a valid email address." }),
  ...(f.message.trim().length >= 10 ? {} : { message: "Message must be at least 10 characters." }),
});

const Err = ({ id, msg }) => (msg ? <p id={id} data-testid={id} className="text-xs text-red-700">{msg}</p> : null);

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", message: "" });
  const [errors, setErrors] = useState({});
  const [done, setDone] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const onSubmit = (e) => {
    e.preventDefault();
    const errs = validate(form);
    setErrors(errs);
    setDone(Object.keys(errs).length === 0);
  };
  return (
    <div data-testid="contact-page">
      <PageHero eyebrow="Contact" title="We'd love to hear from you." crumbs={[{ label: "Home", to: "/" }, { label: "Contact" }]}
        description="Questions about shopping, selling or partnerships." />
      <div className="av-container grid gap-10 py-14 lg:grid-cols-12 lg:py-20">
        <aside className="lg:col-span-4 space-y-4">
          <div className="rounded-2xl border border-av-line bg-white p-6">
            <Mail className="h-5 w-5 text-av-clay" />
            <p className="mt-3 font-semibold text-av-ink">Email</p>
            <p data-testid="contact-email-placeholder" className="text-sm text-av-muted">[Support email — to be provided]</p>
          </div>
          <div className="rounded-2xl border border-av-line bg-white p-6">
            <MessageCircle className="h-5 w-5 text-av-clay" />
            <p className="mt-3 font-semibold text-av-ink">Help center</p>
            <p className="text-sm text-av-muted">Ticketed support arrives in Phase 11.</p>
          </div>
        </aside>
        <form onSubmit={onSubmit} noValidate data-testid="contact-form" className="lg:col-span-8 grid gap-5 rounded-2xl border border-av-line bg-white p-6 md:p-8 sm:grid-cols-2">
          <div className="space-y-2"><Label htmlFor="c-name">Name</Label>
            <Input id="c-name" className={field} value={form.name} onChange={set("name")} aria-invalid={!!errors.name} aria-describedby="contact-error-name" data-testid="contact-name-input" />
            <Err id="contact-error-name" msg={errors.name} /></div>
          <div className="space-y-2"><Label htmlFor="c-email">Email</Label>
            <Input id="c-email" type="email" className={field} value={form.email} onChange={set("email")} aria-invalid={!!errors.email} aria-describedby="contact-error-email" data-testid="contact-email-input" />
            <Err id="contact-error-email" msg={errors.email} /></div>
          <div className="space-y-2 sm:col-span-2"><Label htmlFor="c-message">Message</Label>
            <Textarea id="c-message" rows={5} className="bg-white" value={form.message} onChange={set("message")} aria-invalid={!!errors.message} aria-describedby="contact-error-message" data-testid="contact-message-input" />
            <Err id="contact-error-message" msg={errors.message} /></div>
          <div className="sm:col-span-2 space-y-4">
            <Button type="submit" data-testid="contact-submit-button">Send message</Button>
            {done && <StatusAlert tone="info" title="Form preview only" testId="contact-result">Messaging isn't connected yet, so nothing was sent or stored.</StatusAlert>}
          </div>
        </form>
      </div>
    </div>
  );
}
