import { cn } from "@/lib/utils";

export const SectionHeading = ({ eyebrow, title, description, className, id }) => (
  <div className={cn("max-w-2xl space-y-3", className)}>
    {eyebrow && <p className="av-eyebrow">{eyebrow}</p>}
    <h2 id={id} className="text-3xl sm:text-4xl font-semibold tracking-tight text-av-ink">{title}</h2>
    {description && <p className="text-base text-av-muted leading-relaxed">{description}</p>}
  </div>
);
