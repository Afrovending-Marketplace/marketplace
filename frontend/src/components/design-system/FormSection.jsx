import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DsSection } from "@/components/design-system/DsSection";
import { DS } from "@/constants/testIds";

const fieldCls = "h-11 rounded-md bg-white border-av-line focus-visible:ring-av-clay";

export const FormSection = () => {
  const [email, setEmail] = useState("");
  const [touched, setTouched] = useState(false);
  const emailError = touched && !/^\S+@\S+\.\S+$/.test(email) ? "Enter a valid email address." : "";

  const onSubmit = (e) => {
    e.preventDefault();
    setTouched(true);
    if (/^\S+@\S+\.\S+$/.test(email)) toast.success("Demo form is valid (nothing was sent)");
  };

  return (
    <DsSection id="forms" title="Forms" description="Label above field, inline error below, 44px controls. Demo only — nothing is submitted.">
      <form onSubmit={onSubmit} noValidate className="grid max-w-2xl gap-5 rounded-2xl border border-av-line bg-white p-6 md:p-8 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="ds-name">Full name</Label>
          <Input id="ds-name" placeholder="Ama Mensah" className={fieldCls} data-testid={DS.formName} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ds-email">Email</Label>
          <Input id="ds-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} onBlur={() => setTouched(true)}
            aria-invalid={!!emailError} aria-describedby="ds-email-error" className={`${fieldCls} aria-[invalid=true]:border-red-500`} data-testid={DS.formEmail} />
          {emailError && <p id="ds-email-error" data-testid="ds-form-email-error" className="text-xs text-red-700">{emailError}</p>}
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label>Category</Label>
          <Select>
            <SelectTrigger aria-label="Category" className={fieldCls} data-testid={DS.formCategory}><SelectValue placeholder="Select a category" /></SelectTrigger>
            <SelectContent>
              {["Fashion & Textiles", "Home & Ceramics", "Spices & Teas"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="ds-message">Message</Label>
          <Textarea id="ds-message" rows={3} className="bg-white border-av-line" data-testid={DS.formMessage} />
        </div>
        <label className="flex items-center gap-2 text-sm"><Checkbox data-testid={DS.formTerms} /> I agree to the terms</label>
        <label className="flex items-center gap-2 text-sm sm:justify-end"><Switch data-testid={DS.formNotify} /> Email me updates</label>
        <Button type="submit" className="sm:col-span-2 sm:justify-self-start" data-testid={DS.formSubmit}>Validate form</Button>
      </form>
    </DsSection>
  );
};
