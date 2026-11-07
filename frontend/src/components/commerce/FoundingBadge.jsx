import { Award } from "lucide-react";

export const FoundingBadge = ({ className = "", testId = "founding-vendor-badge" }) => (
  <span role="img" aria-label="Founding Vendor: one of the first stores approved after AfroVending's launch" title="Founding Vendor — one of AfroVending's first approved stores"
    data-testid={testId}
    className={`inline-flex items-center gap-1 rounded-full border border-av-gold/60 bg-gradient-to-r from-amber-50 to-yellow-100 px-2.5 py-0.5 text-xs font-semibold text-amber-900 shadow-sm ${className}`}>
    <Award className="h-3.5 w-3.5 text-amber-600" aria-hidden="true" /> Founding Vendor
  </span>
);
