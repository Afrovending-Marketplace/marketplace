import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export const BrandMark = ({ className }) => (
  <svg viewBox="0 0 40 40" aria-hidden="true" className={cn("h-9 w-9", className)}>
    <rect width="40" height="40" rx="10" fill="#1E2A38" />
    <path d="M8 30 L20 9 L32 30 Z" fill="#C85A32" />
    <path d="M14 30 L20 19 L26 30 Z" fill="#D9822B" />
    <rect x="8" y="31.5" width="24" height="2.5" rx="1.25" fill="#2D5A44" />
  </svg>
);

export const BrandLogo = ({ testId, inverted = false }) => (
  <Link to="/" data-testid={testId} aria-label="AfroVending home" className="flex items-center gap-2.5 group">
    <BrandMark className="transition-transform duration-300 group-hover:-rotate-6" />
    <span className="font-serif text-xl font-bold tracking-tight">
      <span className={inverted ? "text-av-gold" : "text-av-clay"}>Afro</span>
      <span className={inverted ? "text-av-linen" : "text-av-indigo"}>Vending</span>
    </span>
  </Link>
);
