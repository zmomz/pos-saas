import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  getClientDashboard, getClientBranding, getTransactions, getClientSubscription,
  payClientSubscription, saveSubscriptionCard, downloadSubscriptionInvoice,
  getLowStockProducts, getTopProducts, getInventoryReport,
  getRestaurantTables, getKdsTickets, getReservations,
  type SubscriptionStatus,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { useBusinessProfile } from '@/contexts/BusinessProfileContext';
import { isRetailType, isRestaurantType, SALE_MODES, type SaleMode } from '@/lib/businessType';
import { notifyError } from '@/lib/notify';
import { formatMoney, formatDate, currencyLabel } from '@/lib/format';
import { cn } from '@/lib/utils';
import { usePageChrome } from '@/contexts/PageChromeContext';
import CountUp from '@/components/dashboard/rx/CountUp';
import ErrorState from '@/components/states/ErrorState';
import LoadingState from '@/components/states/LoadingState';
import CardOnFileDialog, { type CardOnFileToken } from '@/components/billing/CardOnFileDialog';
import AgentMoyasarBanner from '@/components/billing/AgentMoyasarBanner';
import {
  DollarSign, TrendingUp, Monitor, ShoppingBag,
  BarChart3, Users, Download, AlertTriangle, ArrowRight, CreditCard,
  UtensilsCrossed, ChefHat, CalendarClock, Boxes, Layers,
} from 'lucide-react';

interface DashboardStats {
  total_sales: number;
  today_sales: number;
  total_transactions: number;
  today_transactions: number;
  products_count: number;
}

interface Transaction {
  id: number;
  invoice_number: string;
  total_amount: number;
  payment_method: string;
  created_at: string;
}

interface RetailFocus {
  lowStock: number | null;
  inventoryValue: number | null;
  bestSeller: string | null;
}

interface RestaurantFocus {
  activeTables: number | null;
  totalTables: number | null;
  kitchenQueue: number | null;
  reservations: number | null;
}

// Tolerate the various list-endpoint shapes (array | {items} | {total}) without
// fabricating a count when none is available.
function countOf(data: unknown): number | null {
  if (Array.isArray(data)) return data.length;
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>;
    if (Array.isArray(d.items)) return (d.items as unknown[]).length;
    if (Array.isArray(d.products)) return (d.products as unknown[]).length;
    if (typeof d.total === 'number') return d.total;
  }
  return null;
}

function firstName(data: unknown): string | null {
  const arr = Array.isArray(data)
    ? data
    : data && typeof data === 'object' && Array.isArray((data as Record<string, unknown>).items)
      ? ((data as Record<string, unknown>).items as unknown[])
      : [];
  const first = arr[0] as Record<string, unknown> | undefined;
  if (!first) return null;
  return (first.name || first.product_name || first.product || first.title || null) as string | null;
}

export default function ClientDashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [brandName, setBrandName] = useState('');
  const [subscription, setSubscription] = useState<SubscriptionStatus | null>(null);
  const [paying, setPaying] = useState(false);
  const [cardDialogOpen, setCardDialogOpen] = useState(false);
  // SubscriptionStatus does not expose the saved card, so we reflect a just-saved
  // card locally (Rail 2 — merchant card-on-file).
  const [savedCard, setSavedCard] = useState<{ last4: string; brand: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [retailFocus, setRetailFocus] = useState<RetailFocus | null>(null);
  const [restaurantFocus, setRestaurantFocus] = useState<RestaurantFocus | null>(null);
  const navigate = useNavigate();
  const { t, language } = useLanguage();
  const { businessType, saleMode, setSaleMode } = useBusinessProfile();

  const isRetail = businessType ? isRetailType(businessType) : false;
  const isRestaurant = businessType ? isRestaurantType(businessType) : false;
  const isHybrid = businessType === 'both';

  useEffect(() => {
    loadData();
  }, []);

  // Type-specific operations data (issue #201) — fetched only for the relevant
  // vertical so a retail merchant never calls the restaurant endpoints (which
  // 403 by type) and vice versa. Each call degrades to null on failure so the
  // tile shows "unknown" rather than a fabricated number.
  useEffect(() => {
    if (!businessType) return;
    if (isRetailType(businessType)) loadRetailFocus();
    if (isRestaurantType(businessType)) loadRestaurantFocus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessType]);

  async function loadData() {
    setLoading(true);
    setLoadError(false);
    try {
      // The headline KPIs hang off the dashboard stats — a failure here must
      // surface honestly (H4) rather than render an all-zero fake, so it is the
      // one hard dependency. The chrome around it (branding/transactions/
      // subscription) degrades on its own.
      const dashData = await getClientDashboard();
      setStats(dashData);
      const [brandData, txData, subData] = await Promise.all([
        getClientBranding().catch(() => null),
        getTransactions(1, 10).catch(() => []),
        getClientSubscription().catch(() => null),
      ]);
      setBrandName(brandData?.company_name || '');
      setTransactions(Array.isArray(txData) ? txData : (txData?.items || txData?.transactions || []));
      setSubscription(subData);
    } catch (err) {
      console.error('Failed to load:', err);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  async function loadRetailFocus() {
    const [low, top, inv] = await Promise.all([
      getLowStockProducts().catch(() => null),
      getTopProducts(3).catch(() => null),
      getInventoryReport(30).catch(() => null),
    ]);
    setRetailFocus({
      lowStock: countOf(low),
      bestSeller: firstName(top),
      inventoryValue: typeof inv?.total_valuation === 'number' ? inv.total_valuation : null,
    });
  }

  async function loadRestaurantFocus() {
    const [tables, kds, resv] = await Promise.all([
      getRestaurantTables().catch(() => null),
      getKdsTickets().catch(() => null),
      getReservations({ status: 'booked' }).catch(() => null),
    ]);
    const tableItems = tables?.items ?? null;
    const kdsItems = kds?.items ?? null;
    setRestaurantFocus({
      totalTables: tableItems ? tableItems.length : null,
      activeTables: tableItems ? tableItems.filter((tbl) => (tbl.state || 'free') !== 'free').length : null,
      kitchenQueue: kdsItems ? kdsItems.filter((c) => c.status === 'active').length : countOf(kds),
      reservations: countOf(resv),
    });
  }

  async function handleSaveCard(token: CardOnFileToken) {
    const result = await saveSubscriptionCard({ token: token.token, last4: token.last4, brand: token.brand });
    setSavedCard({ last4: result.card_last4 || token.last4, brand: result.card_brand || token.brand });
  }

  async function handlePaySubscription() {
    // Pre-flight (#235): block the charge when the agent hasn't connected Moyasar.
    if (!subscription?.moyasar_publishable_key) {
      toast.error(t('moyasar_preflight_blocked') || 'Payment is unavailable until your provider connects Moyasar.');
      return;
    }
    setPaying(true);
    try {
      const updated = await payClientSubscription();
      setSubscription(updated);
    } catch (err) {
      notifyError(err, t('subscription_payment_failed') || 'Subscription payment failed. Please try again.');
    } finally {
      setPaying(false);
    }
  }

  // Type-aware POS entry: a hybrid merchant carries their chosen default sale
  // mode as intent; single-vertical merchants just open the terminal.
  const openPos = () => navigate(isHybrid ? `/pos?mode=${saleMode}` : '/pos');

  // ⌘K quick actions follow the merchant's vertical so they never jump to a
  // route their business type hides.
  const quickPalette = isRestaurant && !isRetail
    ? [
        { icon: Monitor, label: t('go_to_pos') || 'Open POS', kbd: 'P', onSelect: openPos },
        { icon: UtensilsCrossed, label: t('floor_map') || 'Floor', onSelect: () => navigate('/floor') },
        { icon: ChefHat, label: t('kds') || 'Kitchen', onSelect: () => navigate('/kds') },
        { icon: BarChart3, label: t('reports') || 'Reports', onSelect: () => navigate('/reports') },
      ]
    : [
        { icon: Monitor, label: t('go_to_pos') || 'Open POS', kbd: 'P', onSelect: openPos },
        { icon: ShoppingBag, label: t('products') || 'Products', onSelect: () => navigate('/products') },
        { icon: BarChart3, label: t('reports') || 'Reports', onSelect: () => navigate('/reports') },
        { icon: Users, label: t('staff') || 'Staff', onSelect: () => navigate('/staff') },
      ];

  usePageChrome(
    {
      subtitle: `${brandName ? `${brandName} · ` : ''}${t('recent_transactions')}`,
      primaryAction: (
        <Button onClick={openPos} className="h-11 rounded-[10px] shadow-brand">
          <Monitor className="h-4 w-4" />
          {t('go_to_pos') || 'Open POS'}
        </Button>
      ),
      paletteGroups: [{ label: t('cmd_quick_actions'), items: quickPalette }],
    },
    [language, brandName, businessType, saleMode]
  );

  if (loading) {
    return <LoadingState />;
  }

  // H4 — the dashboard stats failed to load. Tell the truth with a retry rather
  // than rendering all-zero KPIs that read as a real (empty) business.
  if (loadError) {
    return <ErrorState onRetry={loadData} />;
  }

  const todaySales = stats?.today_sales || 0;
  const todayTx = stats?.today_transactions || 0;
  const avgTicket = todayTx > 0 ? todaySales / todayTx : 0;
  // Currency label placement matches formatMoney: trailing in RTL, leading otherwise.
  const curProps = language === 'ar' || language === 'ur'
    ? { suffix: ` ${currencyLabel(language)}` }
    : { prefix: `${currencyLabel(language)} ` };
  const subOverdue = subscription && ['past_due', 'dunning', 'suspended'].includes(subscription.subscription_status);
  const subStatusCls = subscription?.subscription_status === 'active'
    ? 'bg-success/10 text-success'
    : subscription?.subscription_status === 'suspended'
      ? 'bg-danger/10 text-danger'
      : 'bg-warning/15 text-warning';
  // Pure-restaurant merchants build their offering as menu items, not products.
  const catalogLabel = isRestaurant && !isRetail ? (t('menu_items') || 'Menu items') : (t('products_count') || 'Products');
  const num = (v: number | null) => (v === null ? '—' : String(v));

  // Real sparkline from recent transaction amounts (chronological).
  const spark = (() => {
    const amts = [...transactions].reverse().map((tx) => tx.total_amount || 0);
    if (amts.length < 2) return '';
    const max = Math.max(...amts);
    const min = Math.min(...amts);
    const span = max - min || 1;
    const W = 320, H = 46, pad = 3;
    return amts.map((v, i) => {
      const x = pad + ((W - 2 * pad) * i) / (amts.length - 1);
      const y = pad + (H - 2 * pad) * (1 - (v - min) / span);
      return `${x},${y}`;
    }).join(' ');
  })();

  return (
    <div className="animate-fade-up space-y-5">
      {/* Subscription dunning banner */}
      {subscription && subOverdue && (
        <div role="alert" className={cn('dxr-tile flex items-center gap-4', subscription.subscription_status === 'suspended' ? 'border-danger/45' : 'border-warning/45')}>
          <span className={cn('dxr-sw h-10 w-10', subscription.subscription_status === 'suspended' ? 'dxr-sw-danger' : 'dxr-sw-warning')}><AlertTriangle className="h-5 w-5" /></span>
          <div className="flex-1">
            <div className="font-bold">{subscription.subscription_status === 'suspended' ? (t('subscription_suspended_notice') || 'Subscription suspended') : (t('payment_overdue_notice') || 'Subscription payment overdue')}</div>
            <div className="text-sm text-muted-foreground">
              {t('overdue_amount') || 'Amount due'}: {formatMoney(subscription.subscription_fee, language)}
              {subscription.grace_deadline ? ` · ${t('pay_before') || 'pay before'} ${subscription.grace_deadline}` : ''}
            </div>
          </div>
          <Button onClick={handlePaySubscription} disabled={paying || subscription.subscription_fee <= 0 || !subscription.moyasar_publishable_key} className="bg-gradient-to-b from-gold to-gold-600 text-warning-foreground hover:opacity-90">
            {paying ? t('loading') : (t('pay_now') || 'Pay now')}
          </Button>
        </div>
      )}

      {/* Fail-closed: the owning agent hasn't connected Moyasar (#235). */}
      {subscription && (subscription.subscription_fee > 0 || subscription.payments.length > 0) && (
        <AgentMoyasarBanner connected={!!subscription.moyasar_publishable_key} audience="merchant" />
      )}

      {/* Bento KPIs */}
      <div data-tour="stats-section" className="grid gap-4 lg:auto-rows-[116px] lg:grid-cols-12">
        {/* Today's sales spotlight */}
        <section className="dxr-tile dxr-ink flex flex-col lg:col-span-8 lg:row-span-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="dxr-eyebrow">{t('today_sales') || "Today's Sales"}</div>
              <div className="mt-2 text-[clamp(30px,3.6vw,44px)] font-extrabold leading-none tracking-tight tabular-nums">
                <CountUp value={todaySales} {...curProps} />
              </div>
              <div className="mt-1.5 text-[13px] text-white/65">{todayTx} {t('total_transactions') || 'transactions'} · {t('avg_ticket') || 'avg'} {formatMoney(avgTicket, language)}</div>
            </div>
          </div>
          <div className="mt-auto">
            {spark ? (
              <svg viewBox="0 0 320 46" preserveAspectRatio="none" className="h-12 w-full">
                <polyline points={spark} fill="none" stroke="var(--cyan)" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : (
              <div className="text-sm text-white/50">{t('empty_cart') || 'No transactions yet today.'}</div>
            )}
          </div>
        </section>

        {/* Open POS action tile */}
        <button onClick={openPos} className="dxr-tile flex flex-col justify-between bg-gradient-to-br from-brand to-brand-700 text-start text-white lg:col-span-4 lg:row-span-2">
          <div className="flex items-center justify-between">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15"><Monitor className="h-5 w-5" /></span>
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-white/15"><ArrowRight className="h-5 w-5 rtl:-scale-x-100" /></span>
          </div>
          <div>
            <div className="text-[22px] font-extrabold tracking-tight">{t('go_to_pos') || 'Open POS'}</div>
            <div className="mt-0.5 text-[12.5px] text-white/80">{t('start_new_sale') || 'Start a new sale'}</div>
          </div>
        </button>

        {/* KPI chips */}
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('total_transactions') || 'Transactions'}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums"><CountUp value={stats?.total_transactions || 0} /></div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{todayTx} {t('today') || 'today'}</div>
        </section>
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('total_sales') || 'Total Sales'}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums"><CountUp value={stats?.total_sales || 0} {...curProps} /></div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{t('all_time') || 'all time'}</div>
        </section>
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('avg_ticket') || 'Avg Ticket'}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums">{formatMoney(avgTicket, language)}</div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{t('today') || 'today'}</div>
        </section>
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{catalogLabel}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums"><CountUp value={stats?.products_count || 0} /></div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{t('active') || 'active'}</div>
        </section>
      </div>

      {/* Hybrid sale-mode switch — only a `both` merchant rings up sales across
          retail and the restaurant order types, so only they get the switch. */}
      {isHybrid && (
        <div className="dxr-tile flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-[14px] font-extrabold tracking-tight">{t('sale_mode') || 'Default sale mode'}</div>
            <div className="text-[12.5px] text-muted-foreground">{t('sale_mode_hint') || 'How a new sale opens in the POS.'}</div>
          </div>
          <div className="dxr-seg" role="group" aria-label={t('sale_mode') || 'Default sale mode'}>
            {SALE_MODES.map((mode: SaleMode) => (
              <button
                key={mode}
                type="button"
                data-active={saleMode === mode}
                onClick={() => setSaleMode(mode)}
              >
                {t(`sale_mode_${mode}`) || mode}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Type-aware operations focus (issue #201). Real metrics linking to the
          page that acts on them; "—" means the figure is currently unavailable. */}
      {isRetail && (
        <section>
          {isHybrid && <h2 className="mb-2.5 text-[13px] font-bold uppercase tracking-wider text-muted-foreground">{t('dash_retail_ops') || 'Retail'}</h2>}
          <div className="grid gap-4 sm:grid-cols-3">
            <FocusTile
              swatch="dxr-sw-warning" icon={<AlertTriangle className="h-[18px] w-[18px]" />}
              label={t('kpi_low_stock') || 'Low stock'} value={num(retailFocus?.lowStock ?? null)}
              sub={t('kpi_needs_reorder') || 'items need reorder'} onClick={() => navigate('/products')}
            />
            <FocusTile
              swatch="dxr-sw-brand" icon={<Boxes className="h-[18px] w-[18px]" />}
              label={t('kpi_inventory_value') || 'Inventory value'}
              value={retailFocus?.inventoryValue != null ? formatMoney(retailFocus.inventoryValue, language) : '—'}
              sub={t('kpi_on_hand') || 'stock on hand'} onClick={() => navigate('/reports')}
            />
            <FocusTile
              swatch="dxr-sw-gold" icon={<TrendingUp className="h-[18px] w-[18px]" />}
              label={t('kpi_best_seller') || 'Best seller'} value={retailFocus?.bestSeller || '—'}
              valueClass="truncate text-lg" sub={t('kpi_top_30d') || 'top item · last 30 days'} onClick={() => navigate('/reports')}
            />
          </div>
        </section>
      )}

      {isRestaurant && (
        <section>
          {isHybrid && <h2 className="mb-2.5 text-[13px] font-bold uppercase tracking-wider text-muted-foreground">{t('dash_restaurant_ops') || 'Restaurant'}</h2>}
          <div className="grid gap-4 sm:grid-cols-3">
            <FocusTile
              swatch="dxr-sw-violet" icon={<UtensilsCrossed className="h-[18px] w-[18px]" />}
              label={t('kpi_active_tables') || 'Active tables'}
              value={restaurantFocus?.activeTables != null && restaurantFocus?.totalTables != null
                ? `${restaurantFocus.activeTables}/${restaurantFocus.totalTables}`
                : num(restaurantFocus?.activeTables ?? null)}
              sub={t('kpi_seated_now') || 'seated now'} onClick={() => navigate('/floor')}
            />
            <FocusTile
              swatch="dxr-sw-sky" icon={<ChefHat className="h-[18px] w-[18px]" />}
              label={t('kpi_kitchen_queue') || 'Kitchen queue'} value={num(restaurantFocus?.kitchenQueue ?? null)}
              sub={t('kpi_tickets_cooking') || 'tickets cooking'} onClick={() => navigate('/kds')}
            />
            <FocusTile
              swatch="dxr-sw-success" icon={<CalendarClock className="h-[18px] w-[18px]" />}
              label={t('kpi_reservations') || 'Reservations'} value={num(restaurantFocus?.reservations ?? null)}
              sub={t('kpi_upcoming') || 'upcoming'} onClick={() => navigate('/reservations')}
            />
          </div>
        </section>
      )}

      {/* Quick actions — vertical-aware so every chip lands on a reachable page. */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-2.5">
        {isRetail && (
          <button onClick={() => navigate('/products')} className="chip-link"><ShoppingBag className="h-4 w-4" /> {t('manage_products') || 'Products'}</button>
        )}
        {isRestaurant && (
          <>
            <button onClick={() => navigate('/floor')} className="chip-link"><UtensilsCrossed className="h-4 w-4" /> {t('floor_map') || 'Floor'}</button>
            <button onClick={() => navigate('/menu-builder')} className="chip-link"><Layers className="h-4 w-4" /> {t('menu_builder') || 'Menu'}</button>
          </>
        )}
        <button onClick={() => navigate('/reports')} className="chip-link"><BarChart3 className="h-4 w-4" /> {t('reports_analytics') || 'Reports'}</button>
        <button onClick={() => navigate('/staff')} className="chip-link"><Users className="h-4 w-4" /> {t('staff') || 'Staff'}</button>
      </div>

      {/* Subscription + transactions */}
      <div className="grid items-start gap-[18px] lg:grid-cols-[360px_1fr]">
        {/* Subscription panel */}
        {subscription && (subscription.subscription_fee > 0 || subscription.payments.length > 0) ? (
          <div className="dxr-tile">
            <div className="mb-3 flex items-center justify-between">
              <button onClick={() => navigate('/billing')} className="text-[16px] font-extrabold tracking-tight hover:text-brand-700">{t('subscription') || 'Subscription'}</button>
              <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold', subStatusCls)}>
                <span className="h-1.5 w-1.5 rounded-full bg-current" />{subscription.subscription_status}
              </span>
            </div>
            <div className="flex items-end justify-between">
              <div>
                <div className="text-xs text-muted-foreground">{t('subscription_fee') || 'Fee'}</div>
                <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums">{formatMoney(subscription.subscription_fee, language)}</div>
                <div className="text-[11.5px] text-muted-foreground">/ {t(subscription.billing_cycle) || subscription.billing_cycle}</div>
              </div>
              <div className="text-end">
                <div className="text-xs text-muted-foreground">{t('next_billing') || 'Next billing'}</div>
                <div className="mt-1 font-semibold tabular-nums">{subscription.next_billing_date ? formatDate(subscription.next_billing_date, language) : '—'}</div>
              </div>
            </div>
            {/* Payment method (Rail 2 — merchant card-on-file) */}
            <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/40 px-3 py-2.5">
              <div className="flex items-center gap-2.5">
                <span className="dxr-sw dxr-sw-brand h-8 w-8"><CreditCard className="h-4 w-4" /></span>
                <div>
                  <div className="text-[12.5px] font-semibold text-foreground">{t('payment_method') || 'Payment method'}</div>
                  {savedCard ? (
                    <div className="text-[11.5px] text-muted-foreground">•••• {savedCard.last4}{savedCard.brand ? ` · ${savedCard.brand}` : ''}</div>
                  ) : (
                    <div className="text-[11.5px] text-muted-foreground">{t('no_card_on_file') || 'No card on file'}</div>
                  )}
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => setCardDialogOpen(true)}>
                {savedCard ? (t('update') || 'Update') : (t('add_card') || 'Add card')}
              </Button>
            </div>
            <Button onClick={handlePaySubscription} disabled={paying || subscription.subscription_fee <= 0 || !subscription.moyasar_publishable_key} className="mt-3 w-full shadow-brand">
              {paying ? t('loading') : (t('pay_now') || 'Pay now')}
            </Button>
            {subscription.payments.length > 0 && (
              <div className="mt-4 border-t border-border pt-3">
                <p className="mb-2 text-sm text-muted-foreground">{t('payment_history') || 'Payment history'}</p>
                <div className="space-y-1">
                  {subscription.payments.slice(0, 6).map((p) => (
                    <div key={p.id} className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{p.period_start || (p.created_at ? p.created_at.slice(0, 10) : '')}</span>
                      <div className="flex items-center gap-3">
                        <span className="font-semibold tabular-nums">{formatMoney(p.amount, language)}</span>
                        <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 px-2" onClick={() => downloadSubscriptionInvoice(p.id)} title={t('download_invoice') || 'Download invoice'}>
                          <Download className="h-4 w-4" />
                          <span className="hidden sm:inline">{t('download_invoice') || 'Invoice'}</span>
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="dxr-tile flex flex-col items-center justify-center text-center text-muted-foreground">
            <DollarSign className="mb-2 h-10 w-10 opacity-25" />
            <p className="text-sm">{t('no_subscription') || 'No active subscription.'}</p>
          </div>
        )}

        {/* Recent transactions */}
        <div className="dxr-tile p-0">
          <div className="flex items-center justify-between px-5 pb-3 pt-5">
            <h2 className="text-[16px] font-extrabold tracking-tight">{t('recent_transactions') || 'Recent Transactions'}</h2>
            <button onClick={() => navigate('/reports')} className="inline-flex items-center gap-1 text-[13px] font-bold text-brand-700">{t('view_all') || 'View all'} <ArrowRight className="h-[15px] w-[15px] rtl:-scale-x-100" /></button>
          </div>
          <div className="overflow-x-auto px-2 pb-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10.5px] font-bold uppercase tracking-wider text-muted-foreground/80">
                  <th className="px-3 py-2.5 text-start">{t('invoice_number') || 'Invoice'}</th>
                  <th className="px-3 py-2.5 text-start">{t('total') || 'Total'}</th>
                  <th className="px-3 py-2.5 text-start">{t('payment_method') || 'Payment'}</th>
                  <th className="px-3 py-2.5 text-start">{t('status') || 'Status'}</th>
                </tr>
              </thead>
              <tbody>
                {transactions.length === 0 ? (
                  <tr><td colSpan={4} className="px-3 py-10 text-center text-muted-foreground">{t('empty_cart') || 'No transactions yet.'}</td></tr>
                ) : (
                  transactions.map((tx) => (
                    <tr key={tx.id} className="border-t border-border/70 transition-colors hover:bg-muted/40">
                      <td className="px-3 py-3 font-mono text-[13px]">{tx.invoice_number}</td>
                      <td className="px-3 py-3 font-semibold tabular-nums">{formatMoney(tx.total_amount || 0, language)}</td>
                      <td className="px-3 py-3"><span className="pill-sky">{tx.payment_method}</span></td>
                      <td className="px-3 py-3"><span className="pill-success"><span className="h-1.5 w-1.5 rounded-full bg-current" />{t('paid') || 'Paid'}</span></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <CardOnFileDialog
        open={cardDialogOpen}
        onOpenChange={setCardDialogOpen}
        onSave={handleSaveCard}
        publishableKey={subscription?.moyasar_publishable_key}
        titleKey="payment_method"
      />
    </div>
  );
}

// A type-aware operations tile: icon swatch + metric + sub-label, links to the
// page that acts on it. Kept local to the dashboard.
function FocusTile({
  swatch, icon, label, value, sub, onClick, valueClass,
}: {
  swatch: string;
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  onClick: () => void;
  valueClass?: string;
}) {
  return (
    <button onClick={onClick} className="dxr-tile dxr-hover flex items-center gap-3.5 text-start">
      <span className={cn('dxr-sw h-11 w-11 shrink-0', swatch)}>{icon}</span>
      <div className="min-w-0">
        <div className="text-[12.5px] font-semibold text-muted-foreground">{label}</div>
        <div className={cn('mt-0.5 font-extrabold tracking-tight tabular-nums', valueClass || 'text-2xl')}>{value}</div>
        <div className="text-[11px] text-muted-foreground">{sub}</div>
      </div>
      <ArrowRight className="ms-auto h-4 w-4 shrink-0 text-muted-foreground rtl:-scale-x-100" />
    </button>
  );
}
