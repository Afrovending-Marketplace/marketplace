import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PageHero } from "@/components/common/PageHero";
import { api } from "@/lib/api";

const DOCS = [
  ["/terms", "terms", "Terms of Service"],
  ["/privacy", "privacy", "Privacy Policy"],
  ["/vendor-agreement", "vendor_agreement", "Vendor Agreement"],
  ["/shipping-policy", "shipping", "Shipping & Delivery Policy"],
  ["/returns-policy", "returns", "Returns & Refunds Policy"],
  ["/cookie-policy", "cookies", "Cookie Policy"],
  ["/prohibited-products", "prohibited", "Prohibited Products Policy"],
];

const fmt = (d) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { dateStyle: "long" }) : "");

export const PolicyMarkdown = ({ body, testId }) => (
  <div className="av-prose max-w-none space-y-4 text-sm leading-relaxed text-av-ink/85 [&_h1]:hidden [&_h2]:mt-8 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-av-ink [&_li]:ml-5 [&_ol]:list-decimal [&_ol]:space-y-1 [&_table]:w-full [&_table]:text-left [&_td]:border-t [&_td]:border-av-line [&_td]:p-2 [&_th]:p-2 [&_ul]:list-disc [&_ul]:space-y-1 [&_blockquote]:border-l-4 [&_blockquote]:border-av-gold [&_blockquote]:pl-3 overflow-x-auto" data-testid={testId}>
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
  </div>
);

function PolicyPage({ slug, title, testId }) {
  const [p, setP] = useState(null);
  useEffect(() => {
    api.get(`/policies/${slug}`).then((r) => setP(r.data)).catch(() => setP({ status: "finalising" }));
  }, [slug]);
  return (
    <div data-testid={testId}>
      <PageHero eyebrow="Legal" title={title} />
      <div className="av-container max-w-3xl pb-20">
        {!p ? null : p.status !== "published" ? (
          <div className="rounded-2xl border border-av-line bg-av-sand p-6" data-testid="policy-finalising">
            <h2 className="font-semibold text-av-ink">This policy is being finalised</h2>
            <p className="mt-2 text-sm text-av-muted">We're completing the legal review of this policy before AfroVending opens. Questions? Email <a href="mailto:info@afrovending.com" className="underline">info@afrovending.com</a>.</p>
          </div>
        ) : (
          <>
            <p className="mb-6 text-xs text-av-muted" data-testid="policy-meta">Version {p.version} · Effective {fmt(p.effective_date)}</p>
            <PolicyMarkdown body={p.body} testId="policy-body" />
          </>
        )}
      </div>
    </div>
  );
}

export const POLICY_PAGES = DOCS.map(([path, slug, title]) => ({
  path, slug, title,
  element: <PolicyPage slug={slug} title={title} testId={`${path.slice(1)}-page`} />,
}));
