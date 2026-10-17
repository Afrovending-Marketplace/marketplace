import { PageHero } from "@/components/common/PageHero";
import { StatusAlert } from "@/components/common/StatusAlert";

export const LegalLayout = ({ title, sections, testId }) => (
  <div data-testid={testId}>
    <PageHero eyebrow="Legal" title={title} crumbs={[{ label: "Home", to: "/" }, { label: title }]} />
    <div className="av-container grid gap-10 py-14 lg:grid-cols-[220px_1fr] lg:py-20">
      <nav aria-label="On this page" className="hidden lg:block">
        <ul className="sticky top-40 space-y-1 text-sm">
          {sections.map((s, i) => (
            <li key={s}><a href={`#s-${i}`} className="block rounded-full px-3 py-1.5 text-av-muted hover:bg-av-sand hover:text-av-ink">{s}</a></li>
          ))}
        </ul>
      </nav>
      <article className="max-w-3xl space-y-10">
        <StatusAlert tone="warning" title="Draft — requires founder and legal review" testId="legal-draft-alert">
          This page is a draft and is not a legally approved policy. Final text must be reviewed by the founder and qualified legal counsel before launch.
        </StatusAlert>
        <p className="text-sm text-av-muted">Last updated: [date] · {`AfroVending Online Marketplace LLC`}</p>
        {sections.map((s, i) => (
          <section key={s} id={`s-${i}`} className="scroll-mt-40 space-y-3">
            <h2 className="text-2xl font-semibold text-av-ink">{i + 1}. {s}</h2>
            <p className="text-av-ink/70">[Section content — to be provided by legal counsel.]</p>
          </section>
        ))}
      </article>
    </div>
  </div>
);
