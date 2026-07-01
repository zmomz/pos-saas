import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { getNotifications, globalSearch } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { useBusinessProfile } from '@/contexts/BusinessProfileContext';
import { isPathAllowed } from '@/lib/businessType';
import { useTheme } from '@/contexts/ThemeContext';
import { useLanguage, languageOptions, Language } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import OnboardingTour from '@/components/OnboardingTour';
import OfflineBanner from '@/components/states/OfflineBanner';
import CommandPalette, { type PaletteGroup } from '@/components/dashboard/rx/CommandPalette';
import { buildSearchGroups } from '@/components/dashboard/rx/globalSearchGroups';
import { PageChromeProvider, useShellChrome } from '@/contexts/PageChromeContext';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
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
  Wallet,
  Clock,
  Truck,
  FileText,
  Star,
  GitBranch,
  Webhook,
  Activity,
  ClipboardList,
  Banknote,
  SlidersHorizontal,
} from 'lucide-react';

type UserRole = 'master' | 'agent' | 'client';

interface NavItem {
  icon: React.ElementType;
  label: string;
  path: string;
}

/**
 * A rail group. `section` is an i18n key for the group header, or '' for the
 * top, header-less group (the dashboard home link). Items inside a group are
 * still subject to the business-type filter, so a group with every item hidden
 * collapses away entirely.
 */
interface NavSection {
  section: string;
  items: NavItem[];
}

// Sectioned navigation (issue #213): the flat 27-icon rail is grouped into
// Sell / Catalog / People / Setup so it scales past a wall of icons. Icons are
// de-duplicated within each role's rail (Receipt now belongs only to the
// receipt template, Package only to master packages, modifiers get their own
// SlidersHorizontal) so no two destinations look identical.
export const navConfig: Record<UserRole, NavSection[]> = {
  master: [
    {
      section: '',
      items: [
        { icon: LayoutDashboard, label: 'dashboard', path: '/master' },
        { icon: Package, label: 'packages', path: '/packages' },
        { icon: Shield, label: 'audit_log', path: '/audit' },
        { icon: Bell, label: 'notifications', path: '/notifications' },
      ],
    },
  ],
  // Agents are resellers: they manage white-label branding and their own
  // merchant clients, but own no catalog/sales of their own. The merchant-data
  // pages (products, categories, customers, staff, expenses, discounts,
  // reports) are all client-scoped on the backend and 403 for an agent, so they
  // are intentionally absent here rather than advertised as broken links.
  agent: [
    {
      section: '',
      items: [
        { icon: LayoutDashboard, label: 'dashboard', path: '/agent' },
        { icon: Palette, label: 'branding', path: '/branding' },
        { icon: Shield, label: 'audit_log', path: '/audit' },
        { icon: Bell, label: 'notifications', path: '/notifications' },
      ],
    },
  ],
  client: [
    {
      section: '',
      items: [{ icon: LayoutDashboard, label: 'dashboard', path: '/client' }],
    },
    {
      section: 'nav_section_sell',
      items: [
        { icon: Monitor, label: 'pos_terminal', path: '/pos' },
        { icon: Globe, label: 'online_orders', path: '/channels' },
        { icon: UtensilsCrossed, label: 'floor_map', path: '/floor' },
        { icon: CalendarClock, label: 'rw_reservations', path: '/reservations' },
        { icon: Layers, label: 'menu_builder', path: '/menu-builder' },
        { icon: ChefHat, label: 'kds', path: '/kds' },
      ],
    },
    {
      section: 'nav_section_catalog',
      items: [
        { icon: ShoppingBag, label: 'products', path: '/products' },
        { icon: FolderTree, label: 'categories', path: '/categories' },
        { icon: SlidersHorizontal, label: 'catalog_modifiers', path: '/catalog-modifiers' },
        { icon: Truck, label: 'suppliers', path: '/suppliers' },
        { icon: FileText, label: 'quotations', path: '/quotations' },
        { icon: ClipboardList, label: 'stocktake', path: '/stocktake' },
        { icon: Tag, label: 'discounts', path: '/discounts' },
        { icon: Gift, label: 'gift_cards', path: '/gift-cards' },
        { icon: Star, label: 'loyalty', path: '/loyalty' },
      ],
    },
    {
      section: 'nav_section_people',
      items: [
        { icon: UserCheck, label: 'customers', path: '/customers' },
        { icon: Users, label: 'staff', path: '/staff' },
        { icon: Clock, label: 'shifts', path: '/shifts' },
      ],
    },
    {
      section: 'nav_section_setup',
      items: [
        { icon: GitBranch, label: 'branches', path: '/branches' },
        { icon: Printer, label: 'printers', path: '/printers' },
        { icon: CreditCard, label: 'devices', path: '/devices' },
        { icon: Receipt, label: 'receipt_template', path: '/receipt-template' },
        { icon: Store, label: 'store_settings', path: '/store-settings' },
        { icon: Wallet, label: 'billing', path: '/billing' },
        { icon: Banknote, label: 'expenses', path: '/expenses' },
        { icon: BarChart3, label: 'reports', path: '/reports' },
        { icon: Webhook, label: 'webhooks', path: '/webhooks' },
        { icon: ShieldCheck, label: 'zatca_status', path: '/zatca' },
        { icon: Activity, label: 'ops_title', path: '/ops' },
        { icon: Shield, label: 'audit_log', path: '/audit' },
        { icon: Bell, label: 'notifications', path: '/notifications' },
      ],
    },
  ],
};

const DASHBOARD_PATHS = new Set(['/master', '/agent', '/client']);

/**
 * Resolve the page-identity title (issue #213) for the current location from a
 * role's rail. Longest matching path wins so nested routes (`/products/123`)
 * inherit their parent's identity. Returns the matched item's i18n label key,
 * or '' when nothing matches (e.g. detail routes outside the rail).
 */
function titleKeyForPath(sections: NavSection[], pathname: string): string {
  let best = '';
  let bestLen = -1;
  for (const section of sections) {
    for (const item of section.items) {
      const matches = pathname === item.path || pathname.startsWith(`${item.path}/`);
      if (matches && item.path.length > bestLen) {
        best = item.label;
        bestLen = item.path.length;
      }
    }
  }
  return best;
}

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
  const location = useLocation();
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

  const { businessType } = useBusinessProfile();
  const userRole = (user?.role as UserRole) || 'client';
  // Type-aware navigation (issue #201): a merchant only sees the rail items that
  // belong to their business_type. Retail hides Floor/Tables/KDS/Menu-builder/
  // Reservations; restaurant hides Products/Categories/Suppliers/PO; `both`
  // shows everything. While the type is still loading (null) we show the full
  // rail rather than briefly hiding the wrong items — the route guards still
  // protect any vertical page reached early.
  const navSections = useMemo(() => {
    const base = navConfig[userRole] || navConfig.client;
    const filtered =
      userRole !== 'client' || !businessType
        ? base
        : base.map((section) => ({
            ...section,
            items: section.items.filter((item) => isPathAllowed(item.path, businessType)),
          }));
    // Drop any group left empty by the business-type filter so no orphan header
    // shows above zero links.
    return filtered.filter((section) => section.items.length > 0);
  }, [userRole, businessType]);

  const navItems = useMemo(() => navSections.flatMap((s) => s.items), [navSections]);

  const displayName = (user?.name || user?.email?.split('@')[0] || '').trim();
  const greeting = t(greetingKey());

  // Page identity (issue #213): the dashboard home keeps the personal greeting;
  // every other page promotes its own name to the H1 instead. A page may
  // override the derived title via `chrome.title`.
  const isDashboardHome = DASHBOARD_PATHS.has(location.pathname);
  const titleKey = titleKeyForPath(navConfig[userRole] || navConfig.client, location.pathname);
  const pageTitle = chrome.title || (titleKey ? t(titleKey) : '');

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

  // #231: make the ⌘K palette a true global search — feed the query to the
  // cross-entity /search backend and merge navigable product/customer/
  // transaction hits in above the static nav. Memoised so the palette's
  // debounce effect isn't re-armed on every render.
  const searchEverything = useCallback(
    async (query: string): Promise<PaletteGroup[]> =>
      buildSearchGroups(await globalSearch(query), navigate, t),
    [navigate, t],
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Skip link (#226 · WCAG 2.4.1): first focusable element so keyboard/SR
          users can bypass the icon rail + header. Visually hidden until it
          receives focus, then it paints as a real button over the chrome. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:start-4 focus:top-4 focus:z-[100] focus:rounded-[14px] focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white focus:shadow-brand focus:outline-none focus:ring-2 focus:ring-brand-700"
      >
        {t('skip_to_content')}
      </a>

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
          'fixed inset-y-0 start-0 z-50 flex w-64 flex-col items-center gap-1.5 border-e border-border bg-card py-4 transition-transform duration-200 ease-in-out lg:static lg:w-20 lg:translate-x-0',
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

        {/* Nav icons. overflow-x-hidden is required: overflow-y-auto would
            otherwise compute overflow-x to `auto` too (CSS spec coupling) and
            the rail would scroll horizontally toward the portalled tooltips. */}
        <TooltipProvider delayDuration={0}>
          <nav className="flex w-full flex-1 flex-col items-center gap-1.5 overflow-y-auto overflow-x-hidden px-2 py-1">
            {navSections.map((section) => (
              <div
                key={section.section || 'home'}
                role="group"
                aria-label={section.section ? t(section.section) : undefined}
                className="flex w-full flex-col items-center gap-1.5"
              >
                {section.section && (
                  // Group header: a real text label in the mobile drawer; a
                  // thin divider stands in for it on the 80px desktop icon rail
                  // (the label stays in the a11y tree via sr-only).
                  <div className="w-full px-2 pt-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground lg:px-0">
                    <span className="lg:sr-only">{t(section.section)}</span>
                    <span aria-hidden="true" className="mx-auto mt-1 hidden h-px w-6 bg-border lg:block" />
                  </div>
                )}
                {section.items.map((item, index) => {
                  const Icon = item.icon;
                  return (
                    <Tooltip key={`${item.path}-${index}`}>
                      <TooltipTrigger asChild>
                        <NavLink
                          to={item.path}
                          end={DASHBOARD_PATHS.has(item.path)}
                          onClick={() => setDrawerOpen(false)}
                          aria-label={t(item.label)}
                          className={({ isActive }) =>
                            cn(
                              'flex h-[46px] w-full shrink-0 items-center justify-start gap-3 rounded-[14px] px-3 transition-all lg:w-[46px] lg:justify-center lg:gap-0 lg:px-0',
                              isActive
                                ? 'bg-gradient-to-br from-brand to-brand-700 text-white shadow-brand'
                                : 'text-muted-foreground hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10'
                            )
                          }
                        >
                          <Icon className="h-[21px] w-[21px] shrink-0" />
                          {/* Visible label in the mobile drawer; the desktop
                              icon rail relies on the portalled tooltip below. */}
                          <span className="truncate text-sm font-semibold lg:hidden">
                            {t(item.label)}
                          </span>
                        </NavLink>
                      </TooltipTrigger>
                      {/* Portalled to <body>, so the label escapes the rail
                          instead of widening it. Desktop only — mobile uses
                          the in-drawer label above. */}
                      <TooltipContent
                        side={isRTL ? 'left' : 'right'}
                        className="hidden font-semibold lg:block"
                      >
                        {t(item.label)}
                      </TooltipContent>
                    </Tooltip>
                  );
                })}
              </div>
            ))}
          </nav>
        </TooltipProvider>

        {/* Bottom controls */}
        <div className="flex w-full flex-col items-center gap-1.5 px-1">
          <button
            data-tour="theme-toggle"
            onClick={toggleTheme}
            aria-label={isDark ? t('switch_to_light_mode') : t('switch_to_dark_mode')}
            title={isDark ? t('switch_to_light_mode') : t('switch_to_dark_mode')}
            className="flex h-[42px] w-[42px] items-center justify-center rounded-[13px] text-muted-foreground transition-colors hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10"
          >
            {isDark ? <Sun className="h-5 w-5 text-gold" /> : <Moon className="h-5 w-5" />}
          </button>

          {/* Language */}
          <div className="relative">
            <button
              onClick={() => setLangOpen((o) => !o)}
              aria-label={t('language') || 'Language'}
              aria-expanded={langOpen}
              aria-haspopup="listbox"
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
            aria-label={t('logout')}
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
            <h1 className="truncate text-[20px] font-extrabold leading-tight tracking-tight">
              {isDashboardHome
                ? displayName
                  ? `${greeting}, ${displayName.charAt(0).toUpperCase()}${displayName.slice(1)}`
                  : greeting
                : pageTitle || t('app_name')}
            </h1>
            {chrome.subtitle && (
              <div className="truncate text-[13px] text-muted-foreground">{chrome.subtitle}</div>
            )}
          </div>

          <div className="flex-1" />

          <CommandPalette
            triggerLabel={t('search_everything')}
            placeholder={t('search_or_command')}
            label={t('command_palette')}
            groups={paletteGroups}
            onSearch={searchEverything}
            searchingLabel={t('loading')}
            searchErrorLabel={t('ops_load_error')}
          />

          <button
            onClick={() => navigate('/notifications')}
            aria-label={t('notifications')}
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

        {/* Page content — skip-link target (#226). tabIndex=-1 makes it a
            programmatic focus target so activating the in-page anchor moves
            keyboard focus here, not just the scroll position. */}
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-auto p-4 sm:p-6 focus:outline-none">
          <Outlet />
        </main>
      </div>

      {/* Onboarding Tour */}
      <OnboardingTour />
    </div>
  );
};

export default DashboardLayout;
