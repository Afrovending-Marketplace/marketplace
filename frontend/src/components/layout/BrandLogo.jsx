import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

// Official AfroVending logo (Africa + cart mark). Assets in /public/brand.
export const BrandMark = ({ className, inverted = false }) => (
  <img src={inverted ? "/brand/logo-mark-white.png" : "/brand/logo-mark.png"} alt="" aria-hidden="true"
    width="40" height="40" className={cn("h-10 w-10 object-contain", className)} />
);

export const BrandLogo = ({ testId, inverted = false }) => (
  <Link to="/" data-testid={testId} aria-label="AfroVending home" className="flex items-center gap-2 group">
    <BrandMark inverted={inverted} className="transition-transform duration-300 group-hover:-rotate-6" />
    <span className={cn("font-brand text-2xl font-bold uppercase leading-none tracking-wide", inverted ? "text-white" : "text-av-brand")}>
      Afrovending
    </span>
  </Link>
);
