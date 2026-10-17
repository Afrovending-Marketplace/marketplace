import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HOME } from "@/constants/testIds";

export const VendorCta = () => (
  <section className="av-container py-20 lg:py-28">
    <div className="grain relative grid overflow-hidden rounded-[2rem] bg-av-indigo md:grid-cols-12">
      <div className="relative z-10 space-y-6 p-8 sm:p-12 lg:p-16 md:col-span-7">
        <p className="av-eyebrow text-av-gold">For entrepreneurs</p>
        <h2 className="text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-tight text-av-linen">
          Ready to share your craft with the world?
        </h2>
        <p className="max-w-lg text-av-linen/75 leading-relaxed">
          AfroVending is being built for continental, Caribbean and diaspora businesses. Vendor applications open soon.
        </p>
        <Button asChild size="lg" variant="gold" data-testid={HOME.vendorCtaButton}>
          <Link to="/become-vendor">Start selling <ArrowRight /></Link>
        </Button>
      </div>
      <div className="relative md:col-span-5 min-h-[260px]">
        <img src="/images/vendor.jpg" alt="An artisan vendor at work" loading="lazy"
          className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-y-0 left-0 w-3 kente-strip [background-size:auto] rotate-0" aria-hidden="true" />
      </div>
    </div>
  </section>
);
