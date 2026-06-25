import React, { useState, useEffect } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { getNotifications } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { useLanguage, languageOptions, Language } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import OnboardingTour from '@/components/OnboardingTour';
import OfflineBanner from '@/components/states/OfflineBanner';
import CommandPalette, { type PaletteGroup } from '@/components/dashboard/rx/CommandPalette';
import { PageChromeProvider, useShellChrome } from '@/contexts/PageChromeContext';
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
  UserCheck,
  Receipt,
  Shield,
  FolderTree,
  Tag,
  Sun,
  Moon,
  UtensilsCrossed,
  CalendarClock,
  Layers,
  ChefHat,
  ShieldCheck,
  Gift,
  Printer,
  CreditCard,
  Store,
  Clock,
  Truck,
  FileText,
  Star,
  GitBranch,
  Webhook,
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
    { icon: Package, label: 'packages', path: '/packages' },
    { icon: Shield, label: 'audit_log', path: '/audit' },
    { icon: Bell, label: 'notifications', path: '/notifications' },
  ],
  // Agents are resellers: they manage white-label branding and their own
  // merchant clients, but own no catalog/sales of their own. The merchant-data
  // pages (products, categories, customers, staff, expenses, discounts,
  // reports) are all client-scoped on the backend and 403 for an agent, so they
  // are intentionally absent here rather than advertised as broken links.
  agent: [
    { icon: LayoutDashboard, label: 'dashboard', path: '/agent' },
    { icon: Palette, label: 'branding', path: '/branding' },
    { icon: Shield, label: 'audit_log', path: '/audit' },
    { icon: Bell, label: 'notifications', path: '/notifications' },
  ],
  client: [
    { icon: LayoutDashboard, label: 'dashboard', path: '/client' },
    { icon: Monitor, label: 'pos_terminal', path: '/pos' },
    { icon: UtensilsCrossed, label: 'floor_map', path: '/floor' },
    { icon: CalendarClock, label: 'rw_reservations', path: '/reservations' },
    { icon: Layers, label: 'menu_builder', path: '/menu-builder' },
    { icon: ChefHat, label: 'kds', path: '/kds' },
    { icon: ShoppingBag, label: 'products', path: '/products' },
    { icon: FolderTree, label: 'categories', path: '/categories' },
    { icon: Package, label: 'catalog_modifiers', path: '/catalog-modifiers' },
    { icon: UserCheck, label: 'customers', path: '/customers' },
    { icon: Star, label: 'loyalty', path: '/loyalty' },
    { icon: Users, label: 'staff', path: '/staff' },
    { icon: Clock, label: 'shifts', path: '/shifts' },
    { icon: Truck, label: 'suppliers', path: '/suppliers' },
    { icon: FileText, label: 'quotations', path: '/quotations' },
    { icon: Receipt, label: 'expenses', path: '/expenses' },
    { icon: Tag, label: 'discounts', path: '/discounts' },
    { icon: Gift, label: 'gift_cards', path: '/gift-cards' },
    { icon: GitBranch, label: 'branches', path: '/branches' },
    { icon: Printer, label: 'printers', path: '/printers' },
    { icon: CreditCard, label: 'devices', path: '/devices' },
    { icon: Receipt, label: 'receipt_template', path: '/receipt-template' },
    { icon: Store, label: 'store_settings', path: '/store-settings' },
    { icon: BarChart3, label: 'reports', path: '/reports' },
    { icon: Globe, label: 'online_orders', path: '/channels' },
    { icon: Webhook, label: 'webhooks', path: '/webhooks' },
    { icon: ShieldCheck, label: 'zatca_status', path: '/zatca' },
    { icon: Shield, label: 'audit_log', path: '/audit' },
    { icon: Bell, label: 'notifications', path: '/notifications' },
  ],
};

const DASHBOARD_PATHS = new Set(['/master', '/agent', '/client']);

function greetingKey(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'good_morning';
  if (hour < 18) return 'good_afternoon';
  return 'good_evening';
}

/**
 * App shell — 80px icon rail + sticky command bar (greeting · ⌘K · bell ·
 * primary action), matching the creative-redesign reference. Pages contribute
 * their subtitle / primary action / ⌘K quick actions through
 * `usePageChrome`; the rail nav and global ⌘K are shared across every role.
 */
const DashboardLayout: React.FC = () => {
  return (
    <PageChromeProvider>
      <Shell />
    </PageChromeProvider>
  );
};

const Shell: React.FC = () => {
  const { user, logout } = useAuth();
  const { toggleTheme, isDark } = useTheme();
  const { t, language, setLanguage, isRTL } = useLanguage();
  const navigate = useNavigate();
  const chrome = useShellChrome();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  // Real unread-notification count drives the bell's indicator dot. Fetched once
  // on mount; a failed fetch leaves it at 0 (no dot) rather than showing a fake
  // unread state. The backend /notifications/list response carries unread_count.
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    let active = true;
    getNotifications()
      .then((data) => {
        if (active) setUnreadCount(Number(data?.unread_count) || 0);
      })
      .catch(() => {
        /* leave at 0 — never surface a fake unread indicator */
      });
    return () => {
      active = false;
    };
  }, []);

  const userRole = (user?.role as UserRole) || 'client';
  const navItems = navConfig[userRole] || navConfig.client;

  const displayName = (user?.name || user?.email?.split('@')[0] || '').trim();
  const greeting = t(greetingKey());

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const handleLanguageChange = (lang: Language) => {
    setLanguage(lang);
    setLangOpen(false);
  };

  // Global ⌘K: page-contributed quick actions first, then a navigate group
  // built from this role's rail so every dashboard can jump anywhere.
  const navGroup: PaletteGroup = {
    label: t('cmd_navigate'),
    items: navItems.map((n) => ({ icon: n.icon, label: t(n.label), onSelect: () => navigate(n.path) })),
  };
  const paletteGroups: PaletteGroup[] = [...(chrome.paletteGroups ?? []), navGroup];

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Mobile drawer overlay */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      {/* ── Icon rail ── (static on desktop, slide-in drawer on mobile) */}
      <aside
        data-tour="sidebar-nav"
        className={cn(
          'fixed inset-y-0 start-0 z-50 flex w-20 flex-col items-center gap-1.5 border-e border-border bg-card py-4 transition-transform duration-200 ease-in-out lg:static lg:translate-x-0',
          drawerOpen
            ? 'translate-x-0'
            : isRTL
            ? 'translate-x-full lg:translate-x-0'
            : '-translate-x-full lg:translate-x-0'
        )}
      >
        {/* Logo */}
        <div className="mb-2 flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-[15px] bg-gradient-to-br from-brand to-brand-700 text-xl font-extrabold text-white shadow-brand">
          {(t('app_name') || 'P').charAt(0).toUpperCase()}
        </div>
        <button
          onClick={() => setDrawerOpen(false)}
          className="absolute end-2 top-2 text-muted-foreground hover:text-foreground lg:hidden"
          aria-label={t('close') || 'Close'}
        >
          <X className="h-5 w-5" />
        </button>

        {/* Nav icons */}
        <nav className="flex w-full flex-1 flex-col items-center gap-1.5 overflow-y-auto px-1 py-1">
          {navItems.map((item, index) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={`${item.path}-${index}`}
                to={item.path}
                end={DASHBOARD_PATHS.has(item.path)}
                onClick={() => setDrawerOpen(false)}
                title={t(item.label)}
                className={({ isActive }) =>
                  cn(
                    'group relative flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-[14px] transition-all',
                    isActive
                      ? 'bg-gradient-to-br from-brand to-brand-700 text-white shadow-brand'
                      : 'text-muted-foreground hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10'
                  )
                }
              >
                <Icon className="h-[21px] w-[21px]" />
                {/* Hover tooltip (desktop rail only) */}
                <span className="pointer-events-none absolute start-[54px] z-50 hidden whitespace-nowrap rounded-md bg-foreground px-2.5 py-1.5 text-xs font-semibold text-background opacity-0 shadow-lg transition-opacity group-hover:opacity-100 lg:block">
                  {t(item.label)}
                </span>
              </NavLink>
            );
          })}
        </nav>

        {/* Bottom controls */}
        <div className="flex w-full flex-col items-center gap-1.5 px-1">
          <button
            data-tour="theme-toggle"
            onClick={toggleTheme}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            className="flex h-[42px] w-[42px] items-center justify-center rounded-[13px] text-muted-foreground transition-colors hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10"
          >
            {isDark ? <Sun className="h-5 w-5 text-gold" /> : <Moon className="h-5 w-5" />}
          </button>

          {/* Language */}
          <div className="relative">
            <button
              onClick={() => setLangOpen((o) => !o)}
              title={t('language') || 'Language'}
              className="flex h-[42px] w-[42px] items-center justify-center rounded-[13px] text-muted-foreground transition-colors hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10"
            >
              <Globe className="h-5 w-5" />
            </button>
            {langOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setLangOpen(false)} />
                <div className="absolute bottom-0 start-[52px] z-50 min-w-[140px] rounded-xl border border-border bg-popover py-1 text-popover-foreground shadow-lg">
                  {languageOptions.map((option) => (
                    <button
                      key={option.value}
                      onClick={() => handleLanguageChange(option.value)}
                      className={cn(
                        'block w-full px-4 py-2 text-start text-sm transition-colors',
                        language === option.value
                          ? 'bg-accent font-medium text-accent-foreground'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                      )}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          <button
            onClick={handleLogout}
            title={t('logout')}
            className="flex h-[42px] w-[42px] items-center justify-center rounded-[13px] text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger"
          >
            <LogOut className="h-5 w-5" />
          </button>

          {/* Avatar */}
          <div
            title={user?.email || 'User'}
            className="mt-0.5 flex h-[42px] w-[42px] items-center justify-center rounded-[13px] bg-gradient-to-br from-gold to-gold-600 text-sm font-extrabold text-warning-foreground"
          >
            {(displayName || user?.email || 'U').charAt(0).toUpperCase()}
          </div>
        </div>
      </aside>

      {/* ── Main column ── */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* Command bar */}
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-background/80 px-4 py-3 backdrop-blur-md sm:px-6">
          <button
            onClick={() => setDrawerOpen(true)}
            className="text-muted-foreground hover:text-foreground lg:hidden"
            aria-label={t('menu') || 'Menu'}
          >
            <Menu className="h-6 w-6" />
          </button>

          <div className="min-w-0" data-tour="dashboard-title">
            <div className="truncate text-[20px] font-extrabold leading-tight tracking-tight">
              {displayName ? `${greeting}, ${displayName.charAt(0).toUpperCase()}${displayName.slice(1)}` : greeting}
            </div>
            {chrome.subtitle && (
              <div className="truncate text-[13px] text-muted-foreground">{chrome.subtitle}</div>
            )}
          </div>

          <div className="flex-1" />

          <CommandPalette
            triggerLabel={t('search_everything')}
            placeholder={t('search_or_command')}
            groups={paletteGroups}
          />

          <button
            onClick={() => navigate('/notifications')}
            title={t('notifications')}
            className="relative flex h-11 w-11 items-center justify-center rounded-[14px] border border-input bg-card text-muted-foreground shadow-sm transition-colors hover:border-brand hover:text-brand-700"
          >
            <Bell className="h-[18px] w-[18px]" />
            {unreadCount > 0 && (
              <span className="absolute end-2.5 top-2.5 h-2 w-2 rounded-full bg-danger ring-2 ring-card" />
            )}
          </button>

          {chrome.primaryAction}
        </header>

        {/* Global offline banner (UX-02 / F-051) — covers every back-office page. */}
        <OfflineBanner />

        {/* Page content */}
        <main className="flex-1 overflow-auto p-4 sm:p-6">
          <Outlet />
        </main>
      </div>

      {/* Onboarding Tour */}
      <OnboardingTour />
    </div>
  );
};

export default DashboardLayout;
