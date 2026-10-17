import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
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
import { POLICY_PAGES } from "@/pages/LegalPages";
import LoginPage from "@/pages/auth/LoginPage";
import RegisterPage from "@/pages/auth/RegisterPage";
import { ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage } from "@/pages/auth/RecoveryPages";
import AccountLayout from "@/pages/account/AccountLayout";
import AccountOverview from "@/pages/account/AccountOverview";
import ProfilePage from "@/pages/account/ProfilePage";
import AddressesPage from "@/pages/account/AddressesPage";
import PrivacySettingsPage from "@/pages/account/PrivacySettingsPage";
import { AdminConsolePage, ForbiddenPage } from "@/pages/RolePages";
import VendorDashboardPage from "@/pages/vendor/VendorDashboardPage";
import VendorApplyPage from "@/pages/vendor/VendorApplyPage";
import PublicStorePage from "@/pages/vendor/PublicStorePage";
import AdminVendorsPage from "@/pages/admin/AdminVendorsPage";
import DesignSystemPage from "@/pages/DesignSystemPage";
import ComingSoonPage from "@/pages/ComingSoonPage";
import NotFoundPage from "@/pages/NotFoundPage";
import { FUTURE_ROUTES } from "@/config/site";

const ADMIN_ROLES = ["support_admin", "marketplace_admin", "super_admin"];

function App() {
  return (
    <AuthProvider>
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
            {POLICY_PAGES.map((p) => <Route key={p.path} path={p.path} element={p.element} />)}
            <Route path="login" element={<LoginPage />} />
            <Route path="register" element={<RegisterPage />} />
            <Route path="forgot-password" element={<ForgotPasswordPage />} />
            <Route path="reset-password" element={<ResetPasswordPage />} />
            <Route path="verify-email" element={<VerifyEmailPage />} />
            <Route path="forbidden" element={<ForbiddenPage />} />
            <Route element={<ProtectedRoute />}>
              <Route path="account" element={<AccountLayout />}>
                <Route index element={<AccountOverview />} />
                <Route path="profile" element={<ProfilePage />} />
                <Route path="addresses" element={<AddressesPage />} />
                <Route path="privacy" element={<PrivacySettingsPage />} />
              </Route>
              <Route path="vendor/apply" element={<VendorApplyPage />} />
            </Route>
            <Route element={<ProtectedRoute roles={ADMIN_ROLES} />}>
              <Route path="admin" element={<AdminConsolePage />} />
            </Route>
            <Route element={<ProtectedRoute roles={["marketplace_admin", "super_admin"]} />}>
              <Route path="admin/vendors" element={<AdminVendorsPage />} />
            </Route>
            <Route path="store/:slug" element={<PublicStorePage />} />
            <Route element={<ProtectedRoute roles={["vendor"]} />}>
              <Route path="vendor/dashboard" element={<VendorDashboardPage />} />
            </Route>
            <Route path="design-system" element={<DesignSystemPage />} />
            {FUTURE_ROUTES.map((r) => <Route key={r.path} path={r.path} element={<ComingSoonPage />} />)}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
