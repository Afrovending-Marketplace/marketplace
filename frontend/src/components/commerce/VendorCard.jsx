import { Link } from "react-router-dom";
import { MapPin, ShieldCheck } from "lucide-react";
import { StatusBadge } from "@/components/common/StatusBadge";
import { DevBadge } from "@/components/common/DevDataNotice";
import { isDevData } from "@/lib/catalog";
import { FoundingBadge } from "@/components/commerce/FoundingBadge";

export const VendorCard = ({ vendor }) => (
  <Link to={`/vendors/${vendor.slug}`} data-testid={`vendor-card-${vendor.slug}`}
    className="group block overflow-hidden rounded-2xl border border-av-line bg-white transition-shadow duration-300 hover:shadow-xl">
    <div className="relative h-28 overflow-hidden">
      <img src={vendor.banner} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
      {isDevData() && <DevBadge className="absolute right-3 top-3" />}
    </div>
    <div className="relative px-5 pb-6">
      <img src={vendor.logo} alt={`${vendor.name} logo`} loading="lazy"
        className="-mt-8 h-16 w-16 rounded-full border-4 border-white object-cover shadow" />
      <h3 className="mt-3 font-sans text-lg font-semibold text-av-ink">{vendor.name}</h3>
      <p className="mt-1 flex items-center gap-1 text-xs text-av-muted"><MapPin className="h-3.5 w-3.5" />{vendor.location}</p>
      <p className="mt-3 text-sm text-av-ink/75 line-clamp-2">{vendor.tagline}</p>
      {vendor.verified && (
        <StatusBadge tone="success" className="mt-4"><ShieldCheck className="h-3 w-3" /> {isDevData() ? "Verified (sample)" : "Verified"}</StatusBadge>
      )}
      {vendor.founding_vendor && <FoundingBadge className="ml-2 mt-4" testId={`founding-badge-${vendor.slug}`} />}
    </div>
  </Link>
);
