import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import HomePage from "@/pages/HomePage";
import AdminHomePage, { AcceptInvitePage, AdminTeamPage } from "@/pages/admin/AdminHomePage";
import AdminMfaPage from "@/pages/admin/AdminMfaPage";
import AdminTicketsPage, { SupportPage, SupportTicketPage } from "@/pages/admin/AdminTicketsPage";
import AdminContentPage from "@/pages/admin/AdminContentPage";
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
import AdminProductsPage from "@/pages/admin/AdminProductsPage";
import AdminCategoriesPage from "@/pages/admin/AdminCategoriesPage";
import AdminSearchInsightsPage from "@/pages/admin/AdminSearchInsightsPage";
import AdminCommercePage from "@/pages/admin/AdminCommercePage";
import CartPage from "@/pages/CartPage";
import CheckoutPage from "@/pages/CheckoutPage";
import DraftOrderPage from "@/pages/DraftOrderPage";
import PaymentStatusPage from "@/pages/PaymentStatusPage";
import AccountOrdersPage from "@/pages/account/AccountOrdersPage";
import VendorEarningsPage from "@/pages/vendor/VendorEarningsPage";
import AdminPaymentsPage from "@/pages/admin/AdminPaymentsPage";
import OrderDetailPage from "@/pages/account/OrderDetailPage";
import VendorOrdersPage from "@/pages/vendor/VendorOrdersPage";
import VendorReviewsPage from "@/pages/vendor/VendorReviewsPage";
import NotificationsPage, { MyReviewsPage } from "@/pages/account/NotificationsPage";
import AdminModerationPage from "@/pages/admin/AdminModerationPage";
import AdminMarketingPage from "@/pages/admin/AdminMarketingPage";
import VendorMarketingPage from "@/pages/vendor/VendorMarketingPage";
import { WishlistPage, ReferralsPage, UnsubscribePage } from "@/pages/account/MarketingPages";
import { CookieConsent, RouteTracker } from "@/components/common/CookieConsent";
import AdminFulfillmentPage from "@/pages/admin/AdminFulfillmentPage";
import { CartProvider } from "@/context/CartContext";
import VendorProductsPage from "@/pages/vendor/VendorProductsPage";
import ProductEditorPage from "@/pages/vendor/ProductEditorPage";
import ProductImportPage from "@/pages/vendor/ProductImportPage";
import { CatalogProvider } from "@/context/CatalogContext";
import DesignSystemPage from "@/pages/DesignSystemPage";
import ComingSoonPage from "@/pages/ComingSoonPage";
import NotFoundPage from "@/pages/NotFoundPage";
import { FUTURE_ROUTES } from "@/config/site";

const ADMIN_ROLES = ["support_admin", "content_admin", "finance_admin", "marketplace_admin", "super_admin"];

function App() {
  return (
    <AuthProvider>
      <CatalogProvider>
      <CartProvider>
      <BrowserRouter>
        <RouteTracker />
        <CookieConsent />
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
            <Route path="unsubscribe" element={<UnsubscribePage />} />
            <Route path="forgot-password" element={<ForgotPasswordPage />} />
            <Route path="reset-password" element={<ResetPasswordPage />} />
            <Route path="verify-email" element={<VerifyEmailPage />} />
            <Route path="forbidden" element={<ForbiddenPage />} />
            <Route element={<ProtectedRoute />}>
              <Route path="checkout" element={<CheckoutPage />} />
              <Route path="checkout/draft/:id" element={<DraftOrderPage />} />
              <Route path="checkout/payment/:id" element={<PaymentStatusPage />} />
              <Route path="account" element={<AccountLayout />}>
                <Route index element={<AccountOverview />} />
                <Route path="orders" element={<AccountOrdersPage />} />
                <Route path="orders/:id" element={<OrderDetailPage />} />
                <Route path="profile" element={<ProfilePage />} />
                <Route path="addresses" element={<AddressesPage />} />
                <Route path="privacy" element={<PrivacySettingsPage />} />
                <Route path="support" element={<SupportPage />} />
                <Route path="support/:id" element={<SupportTicketPage />} />
                <Route path="notifications" element={<NotificationsPage />} />
                <Route path="reviews" element={<MyReviewsPage />} />
                <Route path="wishlist" element={<WishlistPage />} />
                <Route path="referrals" element={<ReferralsPage />} />
              </Route>
              <Route path="vendor/apply" element={<VendorApplyPage />} />
            </Route>
            <Route path="admin/invite" element={<AcceptInvitePage />} />
            <Route element={<ProtectedRoute roles={ADMIN_ROLES} />}>
              <Route path="admin" element={<AdminHomePage />} />
              <Route path="admin/console" element={<AdminConsolePage />} />
              <Route path="admin/mfa" element={<AdminMfaPage />} />
              <Route path="admin/team" element={<AdminTeamPage />} />
              <Route path="admin/tickets" element={<AdminTicketsPage />} />
              <Route path="admin/content" element={<AdminContentPage />} />
              <Route path="admin/moderation" element={<AdminModerationPage />} />
              <Route path="admin/marketing" element={<AdminMarketingPage />} />
            </Route>
            <Route element={<ProtectedRoute roles={ADMIN_ROLES} />}>
              <Route path="admin/vendors" element={<AdminVendorsPage />} />
              <Route path="admin/products" element={<AdminProductsPage />} />
              <Route path="admin/categories" element={<AdminCategoriesPage />} />
              <Route path="admin/search-insights" element={<AdminSearchInsightsPage />} />
              <Route path="admin/commerce" element={<AdminCommercePage />} />
              <Route path="admin/payments" element={<AdminPaymentsPage />} />
              <Route path="admin/fulfillment" element={<AdminFulfillmentPage />} />
            </Route>
            <Route path="store/:slug" element={<PublicStorePage />} />
            <Route element={<ProtectedRoute roles={["vendor"]} />}>
              <Route path="vendor/dashboard" element={<VendorDashboardPage />} />
              <Route path="vendor/earnings" element={<VendorEarningsPage />} />
              <Route path="vendor/orders" element={<VendorOrdersPage />} />
              <Route path="vendor/reviews" element={<VendorReviewsPage />} />
              <Route path="vendor/marketing" element={<VendorMarketingPage />} />
              <Route path="vendor/products" element={<VendorProductsPage />} />
              <Route path="vendor/products/import" element={<ProductImportPage />} />
              <Route path="vendor/products/:id" element={<ProductEditorPage />} />
            </Route>
            <Route path="design-system" element={<DesignSystemPage />} />
            <Route path="cart" element={<CartPage />} />
            {FUTURE_ROUTES.map((r) => <Route key={r.path} path={r.path} element={<ComingSoonPage />} />)}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </CartProvider>
      </CatalogProvider>
    </AuthProvider>
  );
}

export default App;
