import React, { useState, useEffect } from 'react';
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { getNotifications, getClientProfile, type BusinessType } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { useLanguage, languageOptions, Language } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import OnboardingTour from '@/components/OnboardingTour';
import OfflineBanner from '@/components/states/OfflineBanner';
import CommandPalette, { type PaletteGroup } from '@/components/dashboard/rx/CommandPalette';
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
  Clock,
  Truck,
  FileText,
  Star,
  GitBranch,
  Webhook,
  SlidersHorizontal,
  Wallet,
} from 'lucide-react';

type UserRole = 'master' | 'agent' | 'client';

interface NavItem {
  icon: React.ElementType;
  label: string;
  path: string;
  /**
   * Modules that only exist for restaurant tenants. The backing pages
   * (floor map, reservations, KDS, menu builder) 403 for a `retail`
   * business_type server-side, so we hide them from the rail rather than
   * advertise broken links. Shown for `restaurant`, `both`, and while the
   * type is still loading (optimistic — a fetch blip never hides a module).
   */
  restaurantOnly?: boolean;
}

interface NavSection {
  /** i18n key for the section header. Omit for an unlabelled lead group. */
  label?: string;
  items: NavItem[];
}

const navConfig: Record<UserRole, NavSection[]> = {
  master: [
    {
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
      items: [
        { icon: LayoutDashboard, label: 'dashboard', path: '/agent' },
        { icon: Palette, label: 'branding', path: '/branding' },
        { icon: Shield, label: 'audit_log', path: '/audit' },
        { icon: Bell, label: 'notifications', path: '/notifications' },
      ],
    },
  ],
  // Client rail grouped into four task-oriented sections (H6) so it scales past
  // a flat 27-icon stack. Reused glyphs are de-duplicated: catalog modifiers use
  // SlidersHorizontal (Package is the master "packages" icon); expenses use
  // Wallet (Receipt belongs to the receipt template).
  client: [
    { items: [{ icon: LayoutDashboard, label: 'dashboard', path: '/client' }] },
    {
      label: 'nav_sell',
      items: [
        { icon: Monitor, label: 'pos_terminal', path: '/pos' },
        { icon: UtensilsCrossed, label: 'floor_map', path: '/floor', restaurantOnly: true },
        { icon: CalendarClock, label: 'rw_reservations', path: '/reservations', restaurantOnly: true },
        { icon: ChefHat, label: 'kds', path: '/kds', restaurantOnly: true },
        { icon: Clock, label: 'shifts', path: '/shifts' },
        { icon: Globe, label: 'online_orders', path: '/channels' },
        { icon: Gift, label: 'gift_cards', path: '/gift-cards' },
      ],
    },
    {
      label: 'nav_catalog',
      items: [
        { icon: ShoppingBag, label: 'products', path: '/products' },
        { icon: FolderTree, label: 'categories', path: '/categories' },
        { icon: SlidersHorizontal, label: 'catalog_modifiers', path: '/catalog-modifiers' },
        { icon: Layers, label: 'menu_builder', path: '/menu-builder', restaurantOnly: true },
        { icon: Tag, label: 'discounts', path: '/discounts' },
        { icon: Truck, label: 'suppliers', path: '/suppliers' },
        { icon: FileText, label: 'quotations', path: '/quotations' },
      ],
    },
    {
      label: 'nav_people',
      items: [
        { icon: UserCheck, label: 'customers', path: '/customers' },
        { icon: Star, label: 'loyalty', path: '/loyalty' },
        { icon: Users, label: 'staff', path: '/staff' },
        { icon: GitBranch, label: 'branches', path: '/branches' },
      ],
    },
    {
      label: 'nav_setup',
      items: [
        { icon: BarChart3, label: 'reports', path: '/reports' },
        { icon: Wallet, label: 'expenses', path: '/expenses' },
        { icon: Store, label: 'store_settings', path: '/store-settings' },
        { icon: Printer, label: 'printers', path: '/printers' },
        { icon: CreditCard, label: 'devices', path: '/devices' },
        { icon: Receipt, label: 'receipt_template', path: '/receipt-template' },
        { icon: Webhook, label: 'webhooks', path: '/webhooks' },
        { icon: ShieldCheck, label: 'zatca_status', path: '/zatca' },
        { icon: Shield, label: 'audit_log', path: '/audit' },
        { icon: Bell, label: 'notifications', path: '/notifications' },
      ],
    },
  ],
};

const DASHBOARD_PATHS = new Set(['/master', '/agent', '/client']);

/**
 * Apply business-type awareness to the rail (#213 / depends on the #201 spine).
 * A `retail` tenant never sees the restaurant-only modules; `restaurant`,
 * `both`, and an as-yet-unknown type (null) see everything. Empty sections are
 * dropped so no header is left dangling.
 */
function visibleSections(
  sections: NavSection[],
  businessType: BusinessType | null,
): NavSection[] {
  if (businessType !== 'retail') return sections;
  return sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => !item.restaurantOnly),
    }))
    .filter((section) => section.items.length > 0);
}

function greetingKey(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'good_morning';
  if (hour < 18) return 'good_afternoon';
  return 'good_evening';
}

/**
 * App shell — sectioned, business-type-aware icon rail (80px on desktop, a
 * labelled drawer on mobile) + a sticky command bar (⌘K · bell · primary
 * action). Each page owns its identity through its own <h1> (PageHeading); the
 * command bar only carries the greeting on the dashboard home. Pages contribute
 * their subtitle / primary action / ⌘K quick actions through `usePageChrome`;
 * the rail nav and global ⌘K are shared across every role.
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
  // Business type drives which modules the client rail shows (#213). Null until
  // the profile loads (or on a fetch blip) → the rail stays inclusive rather
  // than briefly hiding a valid module.
  const [businessType, setBusinessType] = useState<BusinessType | null>(null);
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

  // Only clients have a business_type; the endpoint 403s for master/agent.
  useEffect(() => {
    if (userRole !== 'client') return;
    let active = true;
    getClientProfile()
      .then((profile) => {
        if (active && profile?.business_type) setBusinessType(profile.business_type);
      })
      .catch(() => {
        /* leave null → show every module; never hide one on a fetch blip */
      });
    return () => {
      active = false;
    };
  }, [userRole]);

  const sections = visibleSections(navConfig[userRole] || navConfig.client, businessType);
  const navItems = sections.flatMap((section) => section.items);

  const isDashboardHome = DASHBOARD_PATHS.has(location.pathname);
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
          // Labelled drawer on mobile (w-72), 80px icon rail on desktop (lg:w-20).
          'fixed inset-y-0 start-0 z-50 flex w-72 flex-col items-stretch gap-1.5 border-e border-border bg-card py-4 transition-transform duration-200 ease-in-out lg:static lg:w-20 lg:items-center lg:translate-x-0',
          drawerOpen
            ? 'translate-x-0'
            : isRTL
            ? 'translate-x-full lg:translate-x-0'
            : '-translate-x-full lg:translate-x-0'
        )}
      >
        {/* Logo (with wordmark in the labelled mobile drawer) */}
        <div className="mb-2 flex items-center gap-3 px-3 lg:justify-center lg:px-0">
          <div className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-[15px] bg-gradient-to-br from-brand to-brand-700 text-xl font-extrabold text-white shadow-brand">
            {(t('app_name') || 'P').charAt(0).toUpperCase()}
          </div>
          <span className="truncate text-[17px] font-extrabold tracking-tight lg:hidden">
            {t('app_name') || 'POS'}
          </span>
        </div>
        <button
          onClick={() => setDrawerOpen(false)}
          className="absolute end-2 top-2 text-muted-foreground hover:text-foreground lg:hidden"
          aria-label={t('close') || 'Close'}
        >
          <X className="h-5 w-5" />
        </button>

        {/* Sectioned nav (H6). overflow-x-hidden is required: overflow-y-auto
            would otherwise compute overflow-x to `auto` too (CSS spec coupling)
            and the rail would scroll horizontally toward the portalled tooltips.
            Mobile shows full rows with labels + section headers; desktop
            collapses to the icon rail with a centred micro-label per section. */}
        <TooltipProvider delayDuration={0}>
          <nav className="flex w-full flex-1 flex-col gap-0.5 overflow-y-auto overflow-x-hidden px-2 py-1 lg:items-center lg:px-1">
            {sections.map((section, sectionIndex) => (
              <div key={section.label ?? `section-${sectionIndex}`} className="w-full">
                {section.label && (
                  <div className="px-2 pb-1 pt-3">
                    {/* Full header in the drawer; a clipped micro-label on the rail. */}
                    <span className="block truncate text-[11px] font-bold uppercase tracking-wider text-muted-foreground lg:hidden">
                      {t(section.label)}
                    </span>
                    <span className="hidden truncate text-center text-[9px] font-bold uppercase tracking-wider text-muted-foreground/70 lg:block">
                      {t(section.label)}
                    </span>
                  </div>
                )}
                {section.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Tooltip key={item.path}>
                      <TooltipTrigger asChild>
                        <NavLink
                          to={item.path}
                          end={DASHBOARD_PATHS.has(item.path)}
                          onClick={() => setDrawerOpen(false)}
                          aria-label={t(item.label)}
                          className={({ isActive }) =>
                            cn(
                              'flex items-center rounded-[14px] transition-all',
                              'w-full justify-start gap-3 px-3 py-2.5',
                              'lg:mx-auto lg:h-[46px] lg:w-[46px] lg:justify-center lg:gap-0 lg:px-0 lg:py-0',
                              isActive
                                ? 'bg-gradient-to-br from-brand to-brand-700 text-white shadow-brand'
                                : 'text-muted-foreground hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10'
                            )
                          }
                        >
                          <Icon className="h-[21px] w-[21px] shrink-0" />
                          {/* Label is the drawer affordance; the rail uses the tooltip. */}
                          <span className="truncate text-[14px] font-semibold lg:hidden">
                            {t(item.label)}
                          </span>
                        </NavLink>
                      </TooltipTrigger>
                      {/* Portalled to <body>, so the label escapes the rail instead
                          of widening it. Desktop only — mobile uses the drawer. */}
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

        {/* Bottom controls. Labelled rows in the drawer; icon buttons on the rail. */}
        <div className="mt-1 flex w-full flex-col items-stretch gap-1 border-t border-border px-2 pt-2 lg:items-center lg:gap-1.5 lg:border-0 lg:px-1 lg:pt-0">
          <button
            data-tour="theme-toggle"
            onClick={toggleTheme}
            title={isDark ? t('light_mode') : t('dark_mode')}
            className="flex items-center justify-start gap-3 rounded-[13px] px-3 py-2 text-muted-foreground transition-colors hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10 lg:mx-auto lg:h-[42px] lg:w-[42px] lg:justify-center lg:gap-0 lg:px-0 lg:py-0"
          >
            {isDark ? <Sun className="h-5 w-5 shrink-0 text-gold" /> : <Moon className="h-5 w-5 shrink-0" />}
            <span className="truncate text-[14px] font-semibold lg:hidden">
              {isDark ? t('light_mode') : t('dark_mode')}
            </span>
          </button>

          {/* Language */}
          <div className="relative">
            <button
              onClick={() => setLangOpen((o) => !o)}
              title={t('language') || 'Language'}
              className="flex w-full items-center justify-start gap-3 rounded-[13px] px-3 py-2 text-muted-foreground transition-colors hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10 lg:mx-auto lg:h-[42px] lg:w-[42px] lg:justify-center lg:gap-0 lg:px-0 lg:py-0"
            >
              <Globe className="h-5 w-5 shrink-0" />
              <span className="truncate text-[14px] font-semibold lg:hidden">
                {t('language') || 'Language'}
              </span>
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
            className="flex items-center justify-start gap-3 rounded-[13px] px-3 py-2 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger lg:mx-auto lg:h-[42px] lg:w-[42px] lg:justify-center lg:gap-0 lg:px-0 lg:py-0"
          >
            <LogOut className="h-5 w-5 shrink-0" />
            <span className="truncate text-[14px] font-semibold lg:hidden">{t('logout')}</span>
          </button>

          {/* Identity row: avatar + (in the drawer) name/email */}
          <div
            title={user?.email || 'User'}
            className="mt-0.5 flex items-center gap-3 px-3 py-1 lg:mx-auto lg:justify-center lg:px-0"
          >
            <div className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-[13px] bg-gradient-to-br from-gold to-gold-600 text-sm font-extrabold text-warning-foreground">
              {(displayName || user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 lg:hidden">
              {displayName && (
                <div className="truncate text-[14px] font-semibold">
                  {displayName.charAt(0).toUpperCase()}
                  {displayName.slice(1)}
                </div>
              )}
              {user?.email && (
                <div className="truncate text-[12px] text-muted-foreground">{user.email}</div>
              )}
            </div>
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

          {/* Page identity lives in the page's own <h1> (PageHeading) everywhere
              except the dashboard home, where the greeting *is* the identity.
              Demoting it here is the H6 fix: the greeting no longer outranks the
              page title on every screen. */}
          {isDashboardHome && (
            <div className="min-w-0" data-tour="dashboard-title">
              <h1 className="truncate text-[20px] font-extrabold leading-tight tracking-tight">
                {displayName ? `${greeting}, ${displayName.charAt(0).toUpperCase()}${displayName.slice(1)}` : greeting}
              </h1>
              {chrome.subtitle && (
                <div className="truncate text-[13px] text-muted-foreground">{chrome.subtitle}</div>
              )}
            </div>
          )}

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
