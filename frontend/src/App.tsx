import { useEffect, type ReactNode } from 'react';
import { toast } from 'sonner';
import { DirectionProvider } from '@radix-ui/react-direction';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AccessibilityProvider } from '@/contexts/AccessibilityContext';
import { AuthProvider } from '@/contexts/AuthContext';
import { BrandingProvider } from '@/contexts/BrandingContext';
import { BusinessProfileProvider } from '@/contexts/BusinessProfileContext';
import { LanguageProvider, useLanguage } from '@/lib/i18n';
import LandingPage from './pages/LandingPage';
import Index from './pages/Index';
import MasterDashboard from './pages/MasterDashboard';
import AgentDashboard from './pages/AgentDashboard';
import ClientDashboard from './pages/ClientDashboard';
import POSTerminal from './pages/POSTerminal';
import AgentLandingPage from './pages/AgentLandingPage';
import ProductManagement from './pages/ProductManagement';
import BrandingEditor from './pages/BrandingEditor';
import ReportsAnalytics from './pages/ReportsAnalytics';
import Notifications from './pages/Notifications';
import PackageManagement from './pages/PackageManagement';
import CustomerManagement from './pages/CustomerManagement';
import ExpenseTracking from './pages/ExpenseTracking';
import StaffManagement from './pages/StaffManagement';
import AuditLog from './pages/AuditLog';
import CategoryManagement from './pages/CategoryManagement';
import DiscountManagement from './pages/DiscountManagement';
import QuotationManagement from './pages/QuotationManagement';
import SupplierManagement from './pages/SupplierManagement';
import ShiftManagement from './pages/ShiftManagement';
import LoyaltyProgram from './pages/LoyaltyProgram';
import WebhookManagement from './pages/WebhookManagement';
import UserProfile from './pages/UserProfile';
import StoreSettings from './pages/StoreSettings';
import SubscriptionManagement from './pages/SubscriptionManagement';
import BranchManagement from './pages/BranchManagement';
import GuidedStocktake from './pages/GuidedStocktake';
import FloorMap from './pages/FloorMap';
import Reservations from './pages/Reservations';
import OrderTicket from './pages/OrderTicket';
import MenuBuilder from './pages/MenuBuilder';
import CatalogModifiers from './pages/CatalogModifiers';
import KDS from './pages/KDS';
import ZatcaStatus from './pages/ZatcaStatus';
import Operations from './pages/Operations';
import ChannelOrders from './pages/ChannelOrders';
import GiftCardManagement from './pages/GiftCardManagement';
import PrinterSettings from './pages/PrinterSettings';
import DevicesSettings from './pages/DevicesSettings';
import ReceiptTemplateDesigner from './pages/ReceiptTemplateDesigner';
import CustomerDisplay from './pages/CustomerDisplay';
import ForceResetPassword from './pages/ForceResetPassword';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import NotFound from './pages/NotFound';
import ProtectedRoute from './components/ProtectedRoute';
import BusinessTypeRoute from './components/BusinessTypeRoute';
import DashboardLayout from './components/DashboardLayout';

const queryClient = new QueryClient();

/**
 * Phase 3: surface production-hardening API responses to the user. The
 * apiClient interceptor dispatches window events on 429 (rate-limited) and
 * 401-after-revocation; this listener turns them into toasts. The hard redirect
 * to /login on revocation is handled in the interceptor itself.
 */
const GlobalEventToasts = () => {
  useEffect(() => {
    const onRateLimited = (e: Event) => {
      const retryAfter = (e as CustomEvent).detail?.retryAfter;
      toast.error(
        retryAfter
          ? `Too many requests. Please retry in ${retryAfter}s.`
          : 'Too many requests. Please slow down and try again.'
      );
    };
    const onSessionExpired = () => {
      toast.error('Your session has ended. Please sign in again.');
    };
    window.addEventListener('pos:rate-limited', onRateLimited);
    window.addEventListener('pos:session-expired', onSessionExpired);
    return () => {
      window.removeEventListener('pos:rate-limited', onRateLimited);
      window.removeEventListener('pos:session-expired', onSessionExpired);
    };
  }, []);
  return null;
};

const AppRoutes = () => (
  <Routes>
    {/* Public routes */}
    <Route path="/" element={<LandingPage />} />
    <Route path="/login" element={<Index />} />
    <Route path="/d/:agentId" element={<AgentLandingPage />} />
    <Route path="/customer-display" element={<CustomerDisplay />} />
    {/* First-login force-password-change (consumes must_change_password) */}
    <Route path="/force-reset" element={<ForceResetPassword />} />
    {/* Self-service forgot/reset password (#199, parity #3) */}
    <Route path="/auth/password/forgot" element={<ForgotPassword />} />
    <Route path="/auth/password/reset" element={<ResetPassword />} />

    {/* Master admin routes */}
    <Route
      element={
        <ProtectedRoute allowedRoles={['master']}>
          <DashboardLayout />
        </ProtectedRoute>
      }
    >
      <Route path="/master" element={<MasterDashboard />} />
      <Route path="/packages" element={<PackageManagement />} />
    </Route>

    {/* Agent routes */}
    <Route
      element={
        <ProtectedRoute allowedRoles={['agent']}>
          <DashboardLayout />
        </ProtectedRoute>
      }
    >
      <Route path="/agent" element={<AgentDashboard />} />
      <Route path="/branding" element={<BrandingEditor />} />
    </Route>

    {/* Client (merchant) routes. These pages read client-scoped endpoints that
        403 for an agent, so they are not shared with the agent reseller role.
        Vertical-specific pages are further gated by business_type via
        BusinessTypeRoute (issue #201): the guard derives from the type before
        any per-merchant feature override, mirroring the backend. */}
    <Route
      element={
        <ProtectedRoute allowedRoles={['client']}>
          <DashboardLayout />
        </ProtectedRoute>
      }
    >
      {/* Shared across every business type */}
      <Route path="/client" element={<ClientDashboard />} />
      <Route path="/pos" element={<POSTerminal />} />
      <Route path="/shifts" element={<ShiftManagement />} />
      <Route path="/loyalty" element={<LoyaltyProgram />} />
      <Route path="/branches" element={<BranchManagement />} />
      <Route path="/catalog-modifiers" element={<CatalogModifiers />} />
      <Route path="/channels" element={<ChannelOrders />} />
      <Route path="/zatca" element={<ZatcaStatus />} />
      <Route path="/ops" element={<Operations />} />
      <Route path="/gift-cards" element={<GiftCardManagement />} />
      <Route path="/printers" element={<PrinterSettings />} />
      <Route path="/devices" element={<DevicesSettings />} />
      <Route path="/receipt-template" element={<ReceiptTemplateDesigner />} />
      <Route path="/store-settings" element={<StoreSettings />} />
      <Route path="/billing" element={<SubscriptionManagement />} />
      <Route path="/stocktake" element={<GuidedStocktake />} />
      <Route path="/reports" element={<ReportsAnalytics />} />
      <Route path="/customers" element={<CustomerManagement />} />
      <Route path="/staff" element={<StaffManagement />} />
      <Route path="/expenses" element={<ExpenseTracking />} />
      <Route path="/discounts" element={<DiscountManagement />} />
      <Route path="/webhooks" element={<WebhookManagement />} />

      {/* Restaurant vertical — floor/tables/KDS/menu/reservations */}
      <Route element={<BusinessTypeRoute vertical="restaurant" />}>
        <Route path="/floor" element={<FloorMap />} />
        <Route path="/reservations" element={<Reservations />} />
        <Route path="/floor/ticket/:ticketId" element={<OrderTicket />} />
        <Route path="/menu-builder" element={<MenuBuilder />} />
        <Route path="/kds" element={<KDS />} />
      </Route>

      {/* Retail vertical — catalog + procurement */}
      <Route element={<BusinessTypeRoute vertical="retail" />}>
        <Route path="/products" element={<ProductManagement />} />
        <Route path="/categories" element={<CategoryManagement />} />
        <Route path="/suppliers" element={<SupplierManagement />} />
        <Route path="/quotations" element={<QuotationManagement />} />
      </Route>
    </Route>

    {/* Shared routes (all authenticated roles) */}
    <Route
      element={
        <ProtectedRoute allowedRoles={['master', 'agent', 'client']}>
          <DashboardLayout />
        </ProtectedRoute>
      }
    >
      <Route path="/notifications" element={<Notifications />} />
      <Route path="/audit" element={<AuditLog />} />
      <Route path="/profile" element={<UserProfile />} />
    </Route>

    {/* 404 catch-all */}
    <Route path="*" element={<NotFound />} />
  </Routes>
);

/**
 * Feeds the active language's direction into Radix's DirectionProvider so every
 * Radix primitive (Select, DropdownMenu, Popover, Tooltip, Toast…) flips its
 * alignment, arrow-key navigation and slide animations for Arabic/Urdu instead
 * of defaulting to LTR. Lives inside LanguageProvider so it can read the state.
 */
const DirectionGate = ({ children }: { children: ReactNode }) => {
  const { isRTL } = useLanguage();
  return (
    <DirectionProvider dir={isRTL ? 'rtl' : 'ltr'}>{children}</DirectionProvider>
  );
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <LanguageProvider>
      <DirectionGate>
        <ThemeProvider>
          <AccessibilityProvider>
          <TooltipProvider>
            <Toaster />
            <GlobalEventToasts />
            <BrowserRouter>
              <AuthProvider>
                <BrandingProvider>
                  <BusinessProfileProvider>
                    <AppRoutes />
                  </BusinessProfileProvider>
                </BrandingProvider>
              </AuthProvider>
            </BrowserRouter>
          </TooltipProvider>
          </AccessibilityProvider>
        </ThemeProvider>
      </DirectionGate>
    </LanguageProvider>
  </QueryClientProvider>
);

export default App;
export { AppRoutes };