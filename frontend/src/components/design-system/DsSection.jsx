export const DsSection = ({ id, title, description, children }) => (
  <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-28 border-b border-av-line py-14 first:pt-0">
    <h2 id={`${id}-title`} className="text-2xl sm:text-3xl font-semibold tracking-tight text-av-ink">{title}</h2>
    {description && <p className="mt-2 max-w-2xl text-sm text-av-muted">{description}</p>}
    <div className="mt-8">{children}</div>
  </section>
);
