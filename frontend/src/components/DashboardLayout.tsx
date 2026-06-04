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
  ShieldCheck,
  Gift,
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
    { icon: ShoppingBag, label: 'products', path: '/products' },
    { icon: FolderTree, label: 'categories', path: '/categories' },
    { icon: UserCheck, label: 'customers', path: '/customers' },
    { icon: Users, label: 'staff', path: '/staff' },
    { icon: Receipt, label: 'expenses', path: '/expenses' },
    { icon: Tag, label: 'discounts', path: '/discounts' },
    { icon: Gift, label: 'gift_cards', path: '/gift-cards' },
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
    <div className={`min-h-screen flex ${isDark ? 'bg-slate-800' : 'bg-gray-100'} ${isRTL ? 'flex-row-reverse' : ''}`}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        data-tour="sidebar-nav"
        className={`fixed lg:static inset-y-0 ${isRTL ? 'right-0' : 'left-0'} z-50 w-64 ${isDark ? 'bg-slate-900 border-slate-700' : 'bg-white border-gray-200'} transform transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          sidebarOpen
            ? 'translate-x-0'
            : isRTL
            ? 'translate-x-full lg:translate-x-0'
            : '-translate-x-full lg:translate-x-0'
        } ${isRTL ? 'border-l' : 'border-r'}`}
      >
        {/* Sidebar header */}
        <div className={`h-16 flex items-center justify-between px-4 border-b ${isDark ? 'border-slate-700' : 'border-gray-200'}`}>
          <h1 className={`text-lg font-bold truncate ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('app_name')}</h1>
          <button
            onClick={() => setSidebarOpen(false)}
            className={`lg:hidden ${isDark ? 'text-slate-400 hover:text-white' : 'text-gray-500 hover:text-gray-900'}`}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Nav links */}
        <nav className="p-4 space-y-1">
          {navItems.map((item, index) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={`${item.path}-${index}`}
                to={item.path}
                end={item.path === '/master' || item.path === '/agent' || item.path === '/client'}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-600/20 text-blue-600 border border-blue-500/30'
                      : isDark
                        ? 'text-slate-300 hover:bg-slate-800 hover:text-white'
                        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`
                }
              >
                <Icon className="h-5 w-5 flex-shrink-0" />
                <span>{t(item.label)}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* User info at bottom */}
        <div className={`absolute bottom-0 left-0 right-0 p-4 border-t ${isDark ? 'border-slate-700' : 'border-gray-200'}`}>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-medium">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-sm truncate ${isDark ? 'text-white' : 'text-slate-900'}`}>{user?.email || 'User'}</p>
              <p className={`text-xs capitalize ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>{userRole}</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-h-screen">
        {/* Header */}
        <header className={`h-16 ${isDark ? 'bg-slate-900 border-slate-700' : 'bg-white border-gray-200'} border-b flex items-center justify-between px-4 sticky top-0 z-30`}>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className={`lg:hidden ${isDark ? 'text-slate-400 hover:text-white' : 'text-gray-500 hover:text-gray-900'}`}
            >
              <Menu className="h-6 w-6" />
            </button>
            <h2 data-tour="dashboard-title" className={`font-semibold hidden sm:block ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('dashboard')}</h2>
          </div>

          <div className="flex items-center gap-3">
            {/* Theme toggle */}
            <button
              data-tour="theme-toggle"
              onClick={toggleTheme}
              className={`p-2 rounded-lg transition-colors ${isDark ? 'bg-slate-800 text-yellow-400 hover:bg-slate-700' : 'bg-gray-100 text-slate-700 hover:bg-gray-200'}`}
              title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>

            {/* Language switcher */}
            <div className="relative">
              <button
                onClick={() => setLangDropdownOpen(!langDropdownOpen)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors text-sm ${isDark ? 'bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700' : 'bg-gray-100 text-gray-600 hover:text-gray-900 hover:bg-gray-200'}`}
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
                    className={`absolute top-full mt-1 ${isRTL ? 'left-0' : 'right-0'} z-50 ${isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'} border rounded-lg shadow-lg py-1 min-w-[140px]`}
                  >
                    {languageOptions.map((option) => (
                      <button
                        key={option.value}
                        onClick={() => handleLanguageChange(option.value)}
                        className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                          language === option.value
                            ? 'bg-blue-600/20 text-blue-400'
                            : isDark
                              ? 'text-slate-300 hover:bg-slate-700 hover:text-white'
                              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
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
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors text-sm ${isDark ? 'text-slate-300 hover:text-red-400 hover:bg-slate-800' : 'text-gray-600 hover:text-red-500 hover:bg-gray-100'}`}
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