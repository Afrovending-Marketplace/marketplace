import { useState } from "react";
import { cn } from "@/lib/utils";

export const ProductGallery = ({ images, title }) => {
  const [active, setActive] = useState(0);
  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-[1.5rem] bg-av-sand aspect-[4/5]">
        <img data-testid="pdp-main-image" src={images[active]} alt={`${title}, image ${active + 1} of ${images.length}`} className="h-full w-full object-cover" />
      </div>
      {images.length > 1 && (
        <div className="flex gap-3" role="group" aria-label="Product images">
          {images.map((src, i) => (
            <button key={src} type="button" onClick={() => setActive(i)} aria-label={`Show image ${i + 1}`} aria-pressed={i === active}
              data-testid={`pdp-thumb-${i}`}
              className={cn("h-20 w-20 overflow-hidden rounded-xl border-2 transition-colors", i === active ? "border-av-clay" : "border-transparent hover:border-av-line")}>
              <img src={src} alt="" className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
