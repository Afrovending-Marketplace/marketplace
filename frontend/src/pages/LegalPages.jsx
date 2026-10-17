import { LegalLayout } from "@/components/common/LegalLayout";

const DOCS = [
  ["/privacy", "Privacy Policy", ["Information we collect", "How we use information", "Sharing with vendors and service providers", "Cookies and analytics", "Data retention", "Your rights and choices", "Children's privacy", "International transfers", "Contact us"]],
  ["/terms", "Terms and Conditions", ["Acceptance of terms", "Accounts", "Buying on AfroVending", "Selling on AfroVending", "Fees and payments", "Shipping, returns and refunds", "Prohibited items and conduct", "Intellectual property", "Disclaimers and limitation of liability", "Disputes and governing law", "Changes to these terms", "Contact"]],
  ["/vendor-agreement", "Vendor Agreement", ["Eligibility and verification", "Store and listing standards", "Commission and fees", "Payouts", "Fulfilment obligations", "Returns and disputes", "Suspension and termination", "Contact"]],
  ["/shipping-policy", "Shipping and Delivery Policy", ["Who ships your order", "Shipping methods and costs", "Delivery estimates", "International shipping, duties and taxes", "Tracking", "Lost or damaged items", "Contact"]],
  ["/returns-policy", "Returns and Refund Policy", ["Return eligibility", "Return window", "How to start a return", "Refund method and timing", "Non-returnable items", "Vendor-specific policies", "Contact"]],
  ["/prohibited-products", "Prohibited Products Policy", ["Purpose", "Prohibited items", "Restricted items", "Counterfeit and intellectual property", "Reporting a listing", "Enforcement", "Contact"]],
];

const slug = (path) => path.slice(1);

export const POLICY_PAGES = DOCS.map(([path, title, sections]) => ({
  path,
  element: <LegalLayout testId={`${slug(path)}-page`} title={title} sections={sections} />,
}));
