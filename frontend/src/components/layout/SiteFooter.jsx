import { Link } from "react-router-dom";
import { BrandLogo } from "@/components/layout/BrandLogo";
import { ApiStatus } from "@/components/layout/ApiStatus";
import { NewsletterSignup } from "@/components/marketing/NewsletterSignup";
import { BRAND, FOOTER_COLUMNS } from "@/config/site";
import { SHELL } from "@/constants/testIds";

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

export const SiteFooter = () => (
  <footer data-testid={SHELL.footer} className="bg-av-indigo text-av-linen">
    <div className="kente-strip h-1.5" aria-hidden="true" />
    <div className="av-container border-b border-av-indigo-line py-12"><NewsletterSignup /></div>
    <div className="av-container grid gap-10 py-14 md:grid-cols-12">
      <div className="md:col-span-4 space-y-5">
        <BrandLogo testId="footer-brand-logo" inverted />
        <p className="max-w-sm text-sm leading-relaxed text-av-linen/70">
          Connecting African, Caribbean, diaspora and global entrepreneurs with customers through a secure,
          culturally relevant marketplace.
        </p>
        <p className="font-serif italic text-av-gold text-lg">{BRAND.tagline}.</p>
      </div>
      <div className="md:col-span-8 grid grid-cols-2 gap-8 sm:grid-cols-4">
        {FOOTER_COLUMNS.map((col) => (
          <div key={col.title}>
            <h3 className="font-sans text-xs uppercase tracking-[0.2em] text-av-gold mb-4">{col.title}</h3>
            <ul className="space-y-3">
              {col.links.map((l) => (
                <li key={l.label}>
                  <Link to={l.path} data-testid={`footer-link-${slug(col.title)}-${slug(l.label)}`}
                    className="text-sm text-av-linen/80 hover:text-av-linen transition-colors">{l.label}</Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
    <div className="border-t border-av-indigo-line">
      <div className="av-container flex flex-col gap-3 py-6 sm:flex-row sm:items-center sm:justify-between">
        <p data-testid={SHELL.copyright} className="text-xs text-av-linen/60">
          © {new Date().getFullYear()} {BRAND.legalName}. All rights reserved.
        </p>
        <div className="flex items-center gap-5">
          <ApiStatus />
          <Link to="/design-system" data-testid={SHELL.footerDesignSystemLink}
            className="text-xs text-av-linen/60 hover:text-av-linen underline-offset-4 hover:underline">Design system</Link>
        </div>
      </div>
    </div>
  </footer>
);
