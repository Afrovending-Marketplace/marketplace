import { COLORS, TYPE_SCALE, SPACING } from "@/config/designTokens";
import { DsSection } from "@/components/design-system/DsSection";

export const LogoSection = () => (
  <DsSection id="logo" title="Logo" description="Official AfroVending logo (Africa + cart). Use /brand assets only; never redraw, recolour or stretch.">
    <div className="grid gap-4 sm:grid-cols-3">
      <div className="grid place-items-center rounded-2xl border border-av-line bg-white p-6"><img src="/brand/logo-full.png" alt="AfroVending logo" className="h-40 object-contain" data-testid="ds-logo-full" /></div>
      <div className="grid place-items-center rounded-2xl bg-av-indigo p-6"><img src="/brand/logo-full-white.png" alt="AfroVending logo on dark" className="h-40 object-contain" /></div>
      <div className="grid place-items-center rounded-2xl border border-av-line bg-white p-6"><img src="/brand/logo-mark.png" alt="AfroVending mark" className="h-24 object-contain" /><p className="mt-3 font-mono text-xs text-av-muted">av-brand #D40000</p></div>
    </div>
  </DsSection>
);

export const ColorSection = () => (
  <DsSection id="colors" title="Colors" description="Tailwind tokens under the `av-*` namespace. Primary actions are clay; indigo anchors structure.">
    <div className="space-y-8">
      {COLORS.map(({ group, swatches }) => (
        <div key={group}>
          <p className="mb-3 text-sm font-semibold text-av-ink">{group}</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
            {swatches.map(([token, hex]) => (
              <div key={token} data-testid={`ds-swatch-${token}`} className="overflow-hidden rounded-xl border border-av-line bg-white">
                <div className="h-16" style={{ backgroundColor: hex }} />
                <div className="p-3">
                  <p className="font-mono text-xs text-av-ink">{token}</p>
                  <p className="font-mono text-xs text-av-muted">{hex}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  </DsSection>
);

export const TypographySection = () => (
  <DsSection id="typography" title="Typography" description="Playfair Display for headings, Plus Jakarta Sans for UI and body, JetBrains Mono for codes.">
    <div className="divide-y divide-av-line rounded-2xl border border-av-line bg-white">
      {TYPE_SCALE.map((t) => (
        <div key={t.label} className="grid gap-2 p-5 sm:grid-cols-[160px_1fr] sm:items-baseline">
          <span className="font-mono text-xs text-av-muted">{t.label}</span>
          <span className={`${t.cls} text-av-ink`}>{t.sample}</span>
        </div>
      ))}
    </div>
  </DsSection>
);

export const SpacingSection = () => (
  <DsSection id="spacing" title="Spacing" description="4px base scale. Sections use py-20 / lg:py-28; cards p-6 / md:p-8.">
    <div className="space-y-3">
      {SPACING.map((s) => (
        <div key={s} className="flex items-center gap-4">
          <span className="w-12 font-mono text-xs text-av-muted">{s}</span>
          <div className="h-3 rounded-full bg-av-clay/80" style={{ width: `${s * 4}px` }} />
          <span className="font-mono text-xs text-av-muted">{s * 4}px</span>
        </div>
      ))}
    </div>
  </DsSection>
);
