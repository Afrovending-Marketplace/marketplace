import { useEffect } from "react";
import { DS_SECTIONS } from "@/config/designTokens";
import { LogoSection, ColorSection, TypographySection, SpacingSection } from "@/components/design-system/FoundationSections";
import { ButtonSection, CardSection } from "@/components/design-system/ComponentSections";
import { FormSection } from "@/components/design-system/FormSection";
import { AlertSection, TableSection, ModalSection } from "@/components/design-system/DataSections";
import { DS } from "@/constants/testIds";

export default function DesignSystemPage() {
  useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex";
    document.head.appendChild(meta);
    return () => {
      meta.remove();
    };
  }, []);

  return (
    <div data-testid={DS.page} className="av-container py-14 lg:py-20">
      <header className="max-w-3xl space-y-4 pb-12">
        <p className="av-eyebrow">Internal · v0 · Phase 00</p>
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-av-ink">AfroVending design system</h1>
        <p className="text-lg text-av-muted">The permanent visual language for every phase. Reuse these tokens and components — never restyle per page.</p>
      </header>
      <div className="grid gap-10 lg:grid-cols-[200px_1fr]">
        <nav aria-label="Design system sections" className="hidden lg:block">
          <ul className="sticky top-28 space-y-1">
            {DS_SECTIONS.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} data-testid={`ds-nav-${id}`} className="block rounded-full px-3 py-1.5 text-sm text-av-muted hover:bg-av-sand hover:text-av-ink transition-colors">{label}</a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="min-w-0">
          <LogoSection /><ColorSection /><TypographySection /><SpacingSection /><ButtonSection /><CardSection />
          <FormSection /><AlertSection /><TableSection /><ModalSection />
        </div>
      </div>
    </div>
  );
}
