import { useEffect } from 'react';
import { toast } from 'sonner';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AuthProvider } from '@/contexts/AuthContext';
import { BrandingProvider } from '@/contexts/BrandingContext';
import { LanguageProvider } from '@/lib/i18n';
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
import BranchManagement from './pages/BranchManagement';
import FloorMap from './pages/FloorMap';
import ZatcaStatus from './pages/ZatcaStatus';
import ChannelOrders from './pages/ChannelOrders';
import GiftCardManagement from './pages/GiftCardManagement';
import CustomerDisplay from './pages/CustomerDisplay';
import ForceResetPassword from './pages/ForceResetPassword';
import NotFound from './pages/NotFound';
import ProtectedRoute from './components/ProtectedRoute';
import DashboardLayout from './components/DashboardLayout';

const queryClient = new QueryClient();

/**
 * Phase 3: surface production-hardening API responses to the user. The
 * atomsClient interceptor dispatches window events on 429 (rate-limited) and
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

    {/* Client routes */}
    <Route
      element={
        <ProtectedRoute allowedRoles={['client']}>
          <DashboardLayout />
        </ProtectedRoute>
      }
    >
      <Route path="/client" element={<ClientDashboard />} />
      <Route path="/pos" element={<POSTerminal />} />
      <Route path="/shifts" element={<ShiftManagement />} />
      <Route path="/loyalty" element={<LoyaltyProgram />} />
      <Route path="/branches" element={<BranchManagement />} />
      <Route path="/floor" element={<FloorMap />} />
      <Route path="/channels" element={<ChannelOrders />} />
      <Route path="/zatca" element={<ZatcaStatus />} />
      <Route path="/gift-cards" element={<GiftCardManagement />} />
    </Route>

    {/* Shared routes (agent + client) */}
    <Route
      element={
        <ProtectedRoute allowedRoles={['agent', 'client']}>
          <DashboardLayout />
        </ProtectedRoute>
      }
    >
      <Route path="/products" element={<ProductManagement />} />
      <Route path="/reports" element={<ReportsAnalytics />} />
      <Route path="/customers" element={<CustomerManagement />} />
      <Route path="/staff" element={<StaffManagement />} />
      <Route path="/expenses" element={<ExpenseTracking />} />
      <Route path="/categories" element={<CategoryManagement />} />
      <Route path="/discounts" element={<DiscountManagement />} />
      <Route path="/quotations" element={<QuotationManagement />} />
      <Route path="/suppliers" element={<SupplierManagement />} />
      <Route path="/webhooks" element={<WebhookManagement />} />
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

const App = () => (
  <QueryClientProvider client={queryClient}>
    <LanguageProvider>
      <ThemeProvider>
        <TooltipProvider>
          <Toaster />
          <GlobalEventToasts />
          <BrowserRouter>
            <AuthProvider>
              <BrandingProvider>
                <AppRoutes />
              </BrandingProvider>
            </AuthProvider>
          </BrowserRouter>
        </TooltipProvider>
      </ThemeProvider>
    </LanguageProvider>
  </QueryClientProvider>
);

export default App;
export { AppRoutes };