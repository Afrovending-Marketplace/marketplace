import { FlaskConical } from "lucide-react";
import { PAGES } from "@/constants/testIds";
import { cn } from "@/lib/utils";

export const DevDataNotice = ({ className }) => (
  <div data-testid={PAGES.devDataNotice} role="note"
    className={cn("flex items-start gap-2 rounded-xl border border-dashed border-av-gold/60 bg-av-gold-light px-4 py-3 text-sm text-av-gold-deep", className)}>
    <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" />
    <p><strong>Development data.</strong> Products, vendors and prices on this page are fictional samples for layout only. Nothing can be purchased yet.</p>
  </div>
);

export const DevBadge = ({ className }) => (
  <span className={cn("rounded-full bg-av-ink/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-av-linen backdrop-blur", className)}>
    Sample
  </span>
);
