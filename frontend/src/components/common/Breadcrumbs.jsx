import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

export const Breadcrumbs = ({ items }) => (
  <nav aria-label="Breadcrumb" data-testid="breadcrumbs">
    <ol className="flex flex-wrap items-center gap-1 text-sm text-av-muted">
      {items.map((it, i) => (
        <li key={it.label} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />}
          {it.to ? (
            <Link to={it.to} className="hover:text-av-ink hover:underline underline-offset-4">{it.label}</Link>
          ) : (
            <span aria-current="page" className="text-av-ink">{it.label}</span>
          )}
        </li>
      ))}
    </ol>
  </nav>
);
