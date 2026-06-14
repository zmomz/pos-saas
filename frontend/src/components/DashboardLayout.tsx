import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { useLanguage, languageOptions, Language } from '@/lib/i18n';
import OnboardingTour from '@/components/OnboardingTour';
import OfflineBanner from '@/components/states/OfflineBanner';
import {
  LayoutDashboard,
  Users,
  Package,
  Bell,
  Palette,
  ShoppingBag,
  BarChart3,
  Monitor,
  Menu,
  X,
  LogOut,
  Globe,
  ChevronDown,
  UserCheck,
  Receipt,
  Shield,
  FolderTree,
  Tag,
  Sun,
  Moon,
  UtensilsCrossed,
  Layers,
  ChefHat,
  ShieldCheck,
  Gift,
  Printer,
  CreditCard,
} from 'lucide-react';

type UserRole = 'master' | 'agent' | 'client';

interface NavItem {
  icon: React.ElementType;
  label: string;
  path: string;
}

const navConfig: Record<UserRole, NavItem[]> = {
  master: [
    { icon: LayoutDashboard, label: 'dashboard', path: '/master' },
    { icon: Users, label: 'agents', path: '/master' },
    { icon: Package, label: 'packages', path: '/packages' },
    { icon: Shield, label: 'audit_log', path: '/audit' },
    { icon: Bell, label: 'notifications', path: '/notifications' },
  ],
  agent: [
    { icon: LayoutDashboard, label: 'dashboard', path: '/agent' },
    { icon: Users, label: 'clients', path: '/agent' },
    { icon: Palette, label: 'branding', path: '/branding' },
    { icon: ShoppingBag, label: 'products', path: '/products' },
    { icon: FolderTree, label: 'categories', path: '/categories' },
    { icon: UserCheck, label: 'customers', path: '/customers' },
    { icon: Users, label: 'staff', path: '/staff' },
    { icon: Receipt, label: 'expenses', path: '/expenses' },
    { icon: Tag, label: 'discounts', path: '/discounts' },
    { icon: BarChart3, label: 'reports', path: '/reports' },
    { icon: Shield, label: 'audit_log', path: '/audit' },
    { icon: Bell, label: 'notifications', path: '/notifications' },
  ],
  client: [
    { icon: LayoutDashboard, label: 'dashboard', path: '/client' },
    { icon: Monitor, label: 'pos_terminal', path: '/pos' },
    { icon: UtensilsCrossed, label: 'floor_map', path: '/floor' },
    { icon: Layers, label: 'menu_builder', path: '/menu-builder' },
    { icon: ChefHat, label: 'kds', path: '/kds' },
    { icon: ShoppingBag, label: 'products', path: '/products' },
    { icon: FolderTree, label: 'categories', path: '/categories' },
    { icon: UserCheck, label: 'customers', path: '/customers' },
    { icon: Users, label: 'staff', path: '/staff' },
    { icon: Receipt, label: 'expenses', path: '/expenses' },
    { icon: Tag, label: 'discounts', path: '/discounts' },
    { icon: Gift, label: 'gift_cards', path: '/gift-cards' },
    { icon: Printer, label: 'printers', path: '/printers' },
    { icon: CreditCard, label: 'devices', path: '/devices' },
    { icon: Receipt, label: 'receipt_template', path: '/receipt-template' },
    { icon: BarChart3, label: 'reports', path: '/reports' },
    { icon: Globe, label: 'online_orders', path: '/channels' },
    { icon: ShieldCheck, label: 'zatca_status', path: '/zatca' },
    { icon: Shield, label: 'audit_log', path: '/audit' },
    { icon: Bell, label: 'notifications', path: '/notifications' },
  ],
};

const DashboardLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const { toggleTheme, isDark } = useTheme();
  const { t, language, setLanguage, isRTL } = useLanguage();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [langDropdownOpen, setLangDropdownOpen] = useState(false);

  const userRole = (user?.role as UserRole) || 'client';
  const navItems = navConfig[userRole] || navConfig.client;

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const handleLanguageChange = (lang: Language) => {
    setLanguage(lang);
    setLangDropdownOpen(false);
  };

  return (
    <div className={`flex h-screen overflow-hidden bg-background ${isRTL ? 'flex-row-reverse' : ''}`}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        data-tour="sidebar-nav"
        className={`fixed lg:relative lg:h-screen inset-y-0 ${isRTL ? 'right-0' : 'left-0'} z-50 w-64 bg-sidebar text-sidebar-foreground transform transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          sidebarOpen
            ? 'translate-x-0'
            : isRTL
            ? 'translate-x-full lg:translate-x-0'
            : '-translate-x-full lg:translate-x-0'
        } ${isRTL ? 'border-l border-sidebar-border' : 'border-r border-sidebar-border'}`}
      >
        {/* Sidebar header */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-sidebar-border">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/20 text-white font-bold">
              {(t('app_name') || 'P').charAt(0).toUpperCase()}
            </span>
            <h1 className="text-lg font-bold tracking-tight truncate text-white">{t('app_name')}</h1>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden text-sidebar-foreground hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Nav links */}
        <nav className="p-3 space-y-1 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 8rem)' }}>
          {navItems.map((item, index) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={`${item.path}-${index}`}
                to={item.path}
                end={item.path === '/master' || item.path === '/agent' || item.path === '/client'}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `group relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-white/10 text-white font-semibold before:absolute before:inset-y-1.5 before:start-0 before:w-1 before:rounded-full before:bg-sidebar-primary'
                      : 'text-sidebar-foreground hover:bg-white/5 hover:text-white'
                  }`
                }
              >
                <Icon className="h-5 w-5 flex-shrink-0" />
                <span className="truncate">{t(item.label)}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* User info at bottom */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-sidebar-border bg-sidebar">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-sidebar-primary flex items-center justify-center text-sidebar-primary-foreground text-sm font-bold">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate text-white">{user?.email || 'User'}</p>
              <p className="text-xs capitalize text-sidebar-foreground">{userRole}</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content area — own scroll container so the sidebar stays put. */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        {/* Header */}
        <header className="h-16 bg-card/80 backdrop-blur-md border-b border-border flex items-center justify-between px-4 sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden text-muted-foreground hover:text-foreground"
            >
              <Menu className="h-6 w-6" />
            </button>
            <h2 data-tour="dashboard-title" className="font-semibold hidden sm:block text-foreground">{t('dashboard')}</h2>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            {/* Theme toggle */}
            <button
              data-tour="theme-toggle"
              onClick={toggleTheme}
              className="p-2 rounded-lg transition-colors bg-muted text-foreground hover:bg-accent"
              title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {isDark ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4" />}
            </button>

            {/* Language switcher */}
            <div className="relative">
              <button
                onClick={() => setLangDropdownOpen(!langDropdownOpen)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors text-sm bg-muted text-muted-foreground hover:text-foreground hover:bg-accent"
              >
                <Globe className="h-4 w-4" />
                <span className="hidden sm:inline">
                  {languageOptions.find((l) => l.value === language)?.label || 'English'}
                </span>
                <ChevronDown className="h-3 w-3" />
              </button>
              {langDropdownOpen && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setLangDropdownOpen(false)}
                  />
                  <div
                    className={`absolute top-full mt-1 ${isRTL ? 'left-0' : 'right-0'} z-50 bg-popover text-popover-foreground border border-border rounded-xl shadow-lg py-1 min-w-[140px]`}
                  >
                    {languageOptions.map((option) => (
                      <button
                        key={option.value}
                        onClick={() => handleLanguageChange(option.value)}
                        className={`w-full text-start px-4 py-2 text-sm transition-colors ${
                          language === option.value
                            ? 'bg-accent text-accent-foreground font-medium'
                            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                        }`}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Logout button */}
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors text-sm text-muted-foreground hover:text-red-500 hover:bg-muted"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">{t('logout')}</span>
            </button>
          </div>
        </header>

        {/* Global offline banner (UX-02 / F-051) — covers every back-office page. */}
        <OfflineBanner />

        {/* Page content */}
        <main className="flex-1 p-4 sm:p-6 overflow-auto">
          <Outlet />
        </main>
      </div>

      {/* Onboarding Tour */}
      <OnboardingTour />
    </div>
  );
};

export default DashboardLayout;