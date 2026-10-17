import { cn } from "@/lib/utils";

const TONES = {
  neutral: "bg-av-sand text-av-ink",
  clay: "bg-av-clay-light text-av-clay-active",
  gold: "bg-av-gold-light text-av-gold-deep",
  indigo: "bg-av-indigo-light text-av-indigo",
  success: "bg-av-emerald-light text-av-emerald",
  danger: "bg-red-50 text-red-800",
};

export const StatusBadge = ({ tone = "neutral", children, className, testId }) => (
  <span data-testid={testId}
    className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold", TONES[tone], className)}>
    {children}
  </span>
);
