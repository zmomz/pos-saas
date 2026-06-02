import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AuthProvider } from '@/contexts/AuthContext';
import { BrandingProvider } from '@/contexts/BrandingContext';
import LandingPage from './pages/LandingPage';
import Index from './pages/Index';
import AuthCallback from './pages/AuthCallback';
import AuthError from './pages/AuthError';
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
import CustomerDisplay from './pages/CustomerDisplay';
import NotFound from './pages/NotFound';
import ProtectedRoute from './components/ProtectedRoute';
import DashboardLayout from './components/DashboardLayout';

const queryClient = new QueryClient();

const AppRoutes = () => (
  <Routes>
    {/* Public routes */}
    <Route path="/" element={<LandingPage />} />
    <Route path="/login" element={<Index />} />
    <Route path="/d/:agentId" element={<AgentLandingPage />} />
    <Route path="/auth/callback" element={<AuthCallback />} />
    <Route path="/auth/error" element={<AuthError />} />
    <Route path="/customer-display" element={<CustomerDisplay />} />

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
    <ThemeProvider>
      <TooltipProvider>
        <Toaster />
        <BrowserRouter>
          <AuthProvider>
            <BrandingProvider>
              <AppRoutes />
            </BrandingProvider>
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
export { AppRoutes };