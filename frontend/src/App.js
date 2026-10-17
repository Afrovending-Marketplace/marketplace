import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import HomePage from "@/pages/HomePage";
import ShopPage from "@/pages/ShopPage";
import SearchPage from "@/pages/SearchPage";
import CategoriesPage from "@/pages/CategoriesPage";
import CategoryPage from "@/pages/CategoryPage";
import ProductPage from "@/pages/ProductPage";
import VendorsPage from "@/pages/VendorsPage";
import VendorStorePage from "@/pages/VendorStorePage";
import AboutPage from "@/pages/AboutPage";
import ContactPage from "@/pages/ContactPage";
import FaqPage from "@/pages/FaqPage";
import SellPage from "@/pages/SellPage";
import { PrivacyPage, TermsPage } from "@/pages/LegalPages";
import DesignSystemPage from "@/pages/DesignSystemPage";
import ComingSoonPage from "@/pages/ComingSoonPage";
import NotFoundPage from "@/pages/NotFoundPage";
import { FUTURE_ROUTES } from "@/config/site";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="shop" element={<ShopPage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="categories" element={<CategoriesPage />} />
          <Route path="categories/:slug" element={<CategoryPage />} />
          <Route path="products/:slug" element={<ProductPage />} />
          <Route path="vendors" element={<VendorsPage />} />
          <Route path="vendors/:slug" element={<VendorStorePage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="contact" element={<ContactPage />} />
          <Route path="faq" element={<FaqPage />} />
          <Route path="help" element={<Navigate to="/faq" replace />} />
          <Route path="sell" element={<SellPage />} />
          <Route path="become-vendor" element={<Navigate to="/sell" replace />} />
          <Route path="privacy" element={<PrivacyPage />} />
          <Route path="terms" element={<TermsPage />} />
          <Route path="design-system" element={<DesignSystemPage />} />
          {FUTURE_ROUTES.map((r) => (
            <Route key={r.path} path={r.path} element={<ComingSoonPage />} />
          ))}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
