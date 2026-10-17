import { SHELL } from "@/constants/testIds";

export const BRAND = {
  name: "AfroVending",
  legalName: "AfroVending Online Marketplace LLC",
  tagline: "From Culture to Commerce",
};

// Routes reserved for future phases. Each renders the Coming Soon page until its phase ships.
export const FUTURE_ROUTES = [
  { path: "/shop", title: "Shop", phase: "05", module: "Search, filters & product discovery" },
  { path: "/categories", title: "Categories", phase: "03", module: "Product catalog & categories" },
  { path: "/vendors", title: "Vendors", phase: "04", module: "Vendor storefronts" },
  { path: "/become-vendor", title: "Become a Vendor", phase: "02", module: "Vendor onboarding & verification" },
  { path: "/help", title: "Help Center", phase: "11", module: "Support & notifications" },
  { path: "/account", title: "Your Account", phase: "01", module: "Customer authentication & accounts" },
  { path: "/cart", title: "Cart", phase: "06", module: "Multi-vendor cart & checkout" },
  { path: "/search", title: "Search", phase: "05", module: "Search, filters & product discovery" },
  { path: "/privacy", title: "Privacy Policy", phase: "12", module: "Content management & SEO" },
  { path: "/terms", title: "Terms of Service", phase: "12", module: "Content management & SEO" },
  { path: "/trust-safety", title: "Trust & Safety", phase: "13", module: "Security & monitoring" },
];

export const routeByPath = (path) => FUTURE_ROUTES.find((r) => r.path === path);

export const NAV_LINKS = [
  { label: "Shop", path: "/shop", testId: SHELL.navShop },
  { label: "Categories", path: "/categories", testId: SHELL.navCategories },
  { label: "Vendors", path: "/vendors", testId: SHELL.navVendors },
  { label: "Become a Vendor", path: "/become-vendor", testId: SHELL.navBecomeVendor, highlight: true },
  { label: "Help", path: "/help", testId: SHELL.navHelp },
];

export const FOOTER_COLUMNS = [
  {
    title: "Shop & Discover",
    links: [
      { label: "All Categories", path: "/categories" },
      { label: "Shop the Marketplace", path: "/shop" },
      { label: "Featured Vendors", path: "/vendors" },
    ],
  },
  {
    title: "For Entrepreneurs",
    links: [
      { label: "Become a Vendor", path: "/become-vendor" },
      { label: "Vendor Help", path: "/help" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Privacy Policy", path: "/privacy" },
      { label: "Terms of Service", path: "/terms" },
      { label: "Trust & Safety", path: "/trust-safety" },
      { label: "Help Center", path: "/help" },
    ],
  },
];
