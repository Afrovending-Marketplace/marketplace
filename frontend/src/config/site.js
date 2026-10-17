import { SHELL } from "@/constants/testIds";

export const BRAND = {
  name: "AfroVending",
  legalName: "AfroVending Online Marketplace LLC",
  tagline: "From Culture to Commerce",
  email: "info@afrovending.com",
  website: "https://www.afrovending.com",
  location: "Massachusetts, United States",
};

// Routes reserved for future phases. Each renders the Coming Soon page until its phase ships.
export const FUTURE_ROUTES = [
  { path: "/cart", title: "Your Cart", phase: "06", module: "Multi-vendor cart & checkout" },
  { path: "/trust-safety", title: "Trust & Safety", phase: "13", module: "Security & monitoring" },
];

export const routeByPath = (path) => FUTURE_ROUTES.find((r) => r.path === path);

export const NAV_LINKS = [
  { label: "Shop all", path: "/shop", testId: SHELL.navShop },
  { label: "All categories", path: "/categories", testId: SHELL.navCategories },
  { label: "Vendors", path: "/vendors", testId: SHELL.navVendors },
  { label: "Sell on AfroVending", path: "/sell", testId: SHELL.navBecomeVendor, highlight: true },
];

export const COMPANY_LINKS = [
  { label: "About", path: "/about" },
  { label: "Contact", path: "/contact" },
  { label: "FAQ", path: "/faq" },
];

export const FOOTER_COLUMNS = [
  {
    title: "Shop",
    links: [
      { label: "Shop all", path: "/shop" },
      { label: "All categories", path: "/categories" },
      { label: "Fashion", path: "/categories/fashion" },
      { label: "Beauty", path: "/categories/beauty" },
      { label: "Food & Groceries", path: "/categories/food-groceries" },
    ],
  },
  {
    title: "Sell",
    links: [
      { label: "Sell on AfroVending", path: "/sell" },
      { label: "Browse vendors", path: "/vendors" },
      { label: "Vendor FAQ", path: "/faq#vendors" },
    ],
  },
  { title: "Company", links: COMPANY_LINKS },
  {
    title: "Legal",
    links: [
      { label: "Privacy Policy", path: "/privacy" },
      { label: "Terms & Conditions", path: "/terms" },
      { label: "Vendor Agreement", path: "/vendor-agreement" },
      { label: "Shipping & Delivery", path: "/shipping-policy" },
      { label: "Returns & Refunds", path: "/returns-policy" },
      { label: "Prohibited Products", path: "/prohibited-products" },
    ],
  },
];
