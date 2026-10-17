# AfroVending — Design System (permanent)

Source of truth: `design_guidelines.json`, `frontend/tailwind.config.js` (`av.*` colors, fonts), `frontend/src/index.css` (CSS variables, utilities), live showcase at **`/design-system`** (noindex).

## Identity
Organic, earthy luxury with African textile accents ("kente strip" utility). Warm linen base, terracotta primary, gold accent, deep indigo structure, savanna emerald for success/verified.

## Tokens
| Token | Hex | Use |
|---|---|---|
| `av-clay` / `-hover` / `-active` / `-bright` / `-light` | #B24B25 / #963A17 / #7E2F12 / #C85A32 / #FBEBE4 | Primary actions, links, brand emphasis. `-bright` (original terracotta) is decorative only — it fails 4.5:1 for small text (Phase 01 a11y fix, D-012) |
| `av-gold` / `-hover` / `-deep` / `-light` | #D9822B / #C0701F / #9A5412 / #FEF3E2 | Secondary CTA, eyebrows, ratings, warnings |
| `av-indigo` / `-hover` / `-line` / `-light` | #1E2A38 / #141C27 / #2A394B / #EAEFF5 | Footer, dark panels, info |
| `av-emerald` / `-hover` / `-light` | #2D5A44 / #214433 / #E9F2ED | Success, verified vendor |
| `av-ink` `av-muted` `av-line` `av-sand` `av-linen` | #1A1613 #6E675F #E6DFD3 #F3EDE4 #FAF7F2 | Text, muted text, borders, subtle bg, page bg |

shadcn CSS variables (`--primary`, `--ring`, …) are mapped to these, so stock shadcn components inherit the brand.

## Typography
- Headings: **Playfair Display** (`font-serif`). Body/UI: **Plus Jakarta Sans** (`font-sans`, default). Codes/SKUs: **JetBrains Mono**.
- H1 `text-4xl sm:text-5xl lg:text-6xl` (hero up to 7xl); H2 `text-3xl sm:text-4xl`; body `text-base`; eyebrow `.av-eyebrow`.

## Spacing & layout
4px scale. Container `.av-container` (max-w-7xl, px-4/6/8). Sections `py-20 lg:py-28`. Cards `p-6 md:p-8`, `rounded-2xl`. Inputs `rounded-md`, 44px. Buttons and badges pill (`rounded-full`).

## Components (reuse, do not restyle)
- `Button` (`components/ui/button.jsx`): variants `default` (clay), `gold`, `indigo`, `outline`, `ghost`, `destructive`, `link`; sizes `sm`, `default` (44px), `lg`, `icon`.
- `StatusAlert` tones `info|success|warning|error` (icon + title, `role=alert` for errors).
- `StatusBadge` tones `neutral|clay|gold|indigo|success|danger`.
- `SectionHeading` (eyebrow + H2 + description).
- Cards: product, vendor, feature (see showcase). Forms: Label above, inline error below with `aria-invalid`/`aria-describedby`. Tables: shadcn Table in `overflow-x-auto` wrapper. Modal: shadcn Dialog.
- Shell: `AppShell` (skip link, sticky blurred header with kente strip, mobile Sheet nav, indigo footer with API status).

## Accessibility
Visible focus ring (clay), skip-to-content link, aria-labels on icon buttons, 44px touch targets, `prefers-reduced-motion` respected, every interactive element has a `data-testid` (registry in `constants/testIds/`).
