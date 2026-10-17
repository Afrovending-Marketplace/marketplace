import { LegalLayout } from "@/components/common/LegalLayout";

const PRIVACY = ["Information we collect", "How we use information", "Sharing with vendors and service providers", "Cookies and analytics", "Data retention", "Your rights and choices", "Children's privacy", "International transfers", "Contact us"];
const TERMS = ["Acceptance of terms", "Accounts", "Buying on AfroVending", "Selling on AfroVending", "Fees and payments", "Shipping, returns and refunds", "Prohibited items and conduct", "Intellectual property", "Disclaimers and limitation of liability", "Disputes and governing law", "Changes to these terms", "Contact"];

export const PrivacyPage = () => <LegalLayout testId="privacy-page" title="Privacy Policy" sections={PRIVACY} />;
export const TermsPage = () => <LegalLayout testId="terms-page" title="Terms of Service" sections={TERMS} />;
