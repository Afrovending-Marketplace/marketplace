import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export const CategoryTile = ({ category, className, size = "md" }) => (
  <Link to={`/categories/${category.slug}`} data-testid={`category-tile-${category.slug}`}
    className={cn("group relative block overflow-hidden rounded-2xl bg-av-sand", size === "sm" ? "aspect-square" : "min-h-[220px]", className)}>
    <img src={category.image} alt="" loading="lazy"
      className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
    <div className="absolute inset-0 bg-gradient-to-t from-av-ink/85 via-av-ink/20 to-transparent" />
    <div className="absolute inset-x-0 bottom-0 p-4 sm:p-5">
      <h3 className={cn("font-serif text-av-linen", size === "sm" ? "text-base sm:text-lg" : "text-xl sm:text-2xl")}>{category.name}</h3>
      {size !== "sm" && <p className="mt-1 text-xs text-av-linen/80 line-clamp-2">{category.blurb}</p>}
    </div>
  </Link>
);
