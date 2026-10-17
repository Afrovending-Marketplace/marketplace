import { Breadcrumbs } from "@/components/common/Breadcrumbs";

export const PageHero = ({ eyebrow, title, description, crumbs, children, testId }) => (
  <section data-testid={testId} className="mud-pattern border-b border-av-line">
    <div className="av-container py-12 lg:py-16 space-y-5">
      {crumbs && <Breadcrumbs items={crumbs} />}
      {eyebrow && <p className="av-eyebrow">{eyebrow}</p>}
      <h1 className="max-w-3xl text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-av-ink">{title}</h1>
      {description && <p className="max-w-2xl text-lg text-av-muted leading-relaxed">{description}</p>}
      {children}
    </div>
  </section>
);
