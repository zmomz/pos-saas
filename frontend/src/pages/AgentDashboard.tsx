import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { getAgentClients, getAgentBranding, getAgentRevenue, getAgentCommissionStatements, createNewClient, toggleClient, setClientZatca, setClientFeature, resetClientPassword, runDunning, type AgentRevenue, type CommissionStatement } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';
import { Avatar } from '@/components/dashboard/Avatar';
import { usePageChrome } from '@/contexts/PageChromeContext';
import CountUp from '@/components/dashboard/rx/CountUp';
import Gauge from '@/components/dashboard/rx/Gauge';
import Bar from '@/components/dashboard/rx/Bar';
import { Users, CreditCard, UserPlus, Palette, ShoppingBag, BarChart3, Box, Percent, Star, QrCode, Mail, Sliders, KeyRound, Store, BadgeCheck } from 'lucide-react';

interface ClientItem {
  id: number;
  business_name: string;
  email: string;
  phone: string;
  is_active: boolean;
  subscription_fee: number;
  zatca_enabled: boolean;
}

interface Branding {
  company_name: string;
  logo_url: string;
  primary_color: string;
}

export default function AgentDashboard() {
  const [clients, setClients] = useState<ClientItem[]>([]);
  const [remainingSlots, setRemainingSlots] = useState(0);
  const [totalClients, setTotalClients] = useState(0);
  const [branding, setBranding] = useState<Branding | null>(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newClientForm, setNewClientForm] = useState({ business_name: '', email: '', phone: '', subscription_fee: '', billing_cycle: 'monthly' });
  const [featureClient, setFeatureClient] = useState<ClientItem | null>(null);
  const [featureBusy, setFeatureBusy] = useState(false);
  const [panelClientId, setPanelClientId] = useState<number | null>(null);
  const [featureState, setFeatureState] = useState<Record<string, boolean>>({});
  const [createdCreds, setCreatedCreds] = useState<
    { email: string; temp_password: string; email_delivered: boolean; reset?: boolean } | null
  >(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [resettingId, setResettingId] = useState<number | null>(null);
  const [zatcaTogglingId, setZatcaTogglingId] = useState<number | null>(null);
  const [zatcaError, setZatcaError] = useState<string | null>(null);
  const [revenue, setRevenue] = useState<AgentRevenue | null>(null);
  const [revenueLoading, setRevenueLoading] = useState(true);
  const [revenueError, setRevenueError] = useState(false);
  const [statements, setStatements] = useState<CommissionStatement[]>([]);
  const [statementsLoading, setStatementsLoading] = useState(true);
  const [statementsError, setStatementsError] = useState(false);
  const [dunningBusy, setDunningBusy] = useState(false);
  const [dunningResult, setDunningResult] = useState<string | null>(null);
  const navigate = useNavigate();
  const { t, language } = useLanguage();

  useEffect(() => {
    loadData();
    loadRevenue();
    loadStatements();
  }, []);

  async function loadData() {
    try {
      const [clientData, brandData] = await Promise.all([getAgentClients(), getAgentBranding()]);
      const items = clientData?.items || [];
      setClients(items);
      setRemainingSlots(clientData?.remaining_slots ?? 0);
      setTotalClients(clientData?.total ?? items.length);
      setBranding(brandData);
    } catch (err) {
      console.error('Failed to load:', err);
    } finally {
      setLoading(false);
    }
  }

  async function loadRevenue() {
    setRevenueLoading(true);
    setRevenueError(false);
    try {
      setRevenue(await getAgentRevenue());
    } catch (err) {
      console.error('Failed to load revenue:', err);
      setRevenueError(true);
    } finally {
      setRevenueLoading(false);
    }
  }

  async function loadStatements() {
    setStatementsLoading(true);
    setStatementsError(false);
    try {
      const data = await getAgentCommissionStatements();
      setStatements(data.statements || []);
    } catch (err) {
      console.error('Failed to load commission statements:', err);
      setStatementsError(true);
    } finally {
      setStatementsLoading(false);
    }
  }

  async function handleRunDunning() {
    setDunningBusy(true);
    setDunningResult(null);
    try {
      const result = await runDunning();
      setDunningResult(`${t('dunning_done')}: ${result.processed} · ${t('recovered')} ${result.recovered} · ${t('suspended')} ${result.suspended}`);
      await loadData();
    } catch (err) {
      console.error('Failed to run dunning:', err);
      setDunningResult(t('dunning_failed'));
    } finally {
      setDunningBusy(false);
    }
  }

  async function handleCreateClient() {
    setCreateError(null);
    try {
      const created = await createNewClient({
        business_name: newClientForm.business_name,
        email: newClientForm.email,
        phone: newClientForm.phone,
        subscription_fee: newClientForm.subscription_fee ? Number(newClientForm.subscription_fee) : undefined,
      });
      setDialogOpen(false);
      setNewClientForm({ business_name: '', email: '', phone: '', subscription_fee: '', billing_cycle: 'monthly' });
      if (created?.temp_password) {
        setCreatedCreds({ email: created.email, temp_password: created.temp_password, email_delivered: !!created.email_delivered });
      }
      loadData();
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setCreateError(detail || (err instanceof Error ? err.message : 'Create client failed'));
      console.error('Create client failed:', err);
    }
  }

  async function handleToggleClient(clientId: number) {
    setTogglingId(clientId);
    try {
      await toggleClient(clientId);
      setClients((prev) => prev.map((c) => (c.id === clientId ? { ...c, is_active: !c.is_active } : c)));
    } catch (err) {
      console.error('Toggle client failed:', err);
    } finally {
      setTogglingId(null);
    }
  }

  async function handleResetPassword(clientId: number) {
    setResettingId(clientId);
    try {
      const result = await resetClientPassword(clientId);
      setCreatedCreds({ email: result.email, temp_password: result.temp_password, email_delivered: !!result.email_delivered, reset: true });
    } catch (err) {
      console.error('Reset client password failed:', err);
    } finally {
      setResettingId(null);
    }
  }

  async function handleToggleZatca(clientId: number) {
    setZatcaTogglingId(clientId);
    setZatcaError(null);
    try {
      const result = await setClientZatca(clientId);
      setClients((prev) => prev.map((c) => (c.id === clientId ? { ...c, zatca_enabled: result.zatca_enabled } : c)));
    } catch (err) {
      console.error('Toggle ZATCA failed:', err);
      setZatcaError(t('zatca_toggle_failed') || 'Could not change ZATCA status. Please try again.');
    } finally {
      setZatcaTogglingId(null);
    }
  }

  async function handleSetFeature(featureName: string, isEnabled: boolean) {
    if (!featureClient) return;
    setFeatureBusy(true);
    try {
      await setClientFeature(featureClient.id, featureName, isEnabled);
    } catch (err) {
      console.error('Set feature failed:', err);
    } finally {
      setFeatureBusy(false);
    }
  }

  async function handleToggleFeatureInline(client: ClientItem, featureName: string, next: boolean) {
    setFeatureState((prev) => ({ ...prev, [featureName]: next }));
    try {
      await setClientFeature(client.id, featureName, next);
    } catch (err) {
      console.error('Set feature failed:', err);
      setFeatureState((prev) => ({ ...prev, [featureName]: !next }));
    }
  }

  const TOGGLEABLE_FEATURES = ['inventory', 'discounts', 'loyalty', 'zatca', 'email_receipts'];
  const FEATURE_META: Record<string, { icon: typeof Box; tone: string; label: string; desc: string }> = {
    inventory: { icon: Box, tone: 'dxr-sw-brand', label: t('inventory') || 'Inventory', desc: t('stock_tracking') || 'Stock tracking' },
    discounts: { icon: Percent, tone: 'dxr-sw-success', label: t('discounts') || 'Discounts', desc: t('codes_promos') || 'Codes & promos' },
    loyalty: { icon: Star, tone: 'dxr-sw-gold', label: t('loyalty') || 'Loyalty program', desc: t('points_rewards') || 'Points & rewards' },
    zatca: { icon: QrCode, tone: 'dxr-sw-sky', label: t('zatca') || 'ZATCA e-invoice', desc: t('qr_receipts') || 'QR receipts' },
    email_receipts: { icon: Mail, tone: 'dxr-sw-violet', label: t('email_receipts') || 'Email receipts', desc: t('auto_send') || 'Auto-send' },
  };

  const slotCapacity = remainingSlots + totalClients;
  const activeClients = clients.filter((c) => c.is_active);
  const totalMonthlyRevenue = activeClients.reduce((sum, c) => sum + (c.subscription_fee || 0), 0);
  const panelClient = clients.find((c) => c.id === panelClientId) || clients[0] || null;
  const brandColor = branding?.primary_color || '#1488a6';

  const collected = revenue?.collected ?? 0;
  const owed = revenue?.master_owed ?? 0;
  const net = revenue?.net ?? 0;
  const netPct = collected > 0 ? Math.round((net / collected) * 100) : 0;
  const owedPct = collected > 0 ? Math.round((owed / collected) * 100) : 0;
  const subsPct = clients.length > 0 ? Math.round((activeClients.length / clients.length) * 100) : 0;
  const hasRevenue = !!revenue && revenue.payments > 0;

  usePageChrome(
    {
      subtitle: `${branding?.company_name ? `${branding.company_name} · ` : ''}${clients.length} ${t('clients')} · ${activeClients.length} ${t('active_subscriptions') || 'active subscriptions'}`,
      primaryAction: (
        <Button onClick={() => setDialogOpen(true)} className="h-11 rounded-[10px] shadow-brand">
          <UserPlus className="h-4 w-4" />
          {t('create_client') || 'Add Client'}
        </Button>
      ),
      paletteGroups: [
        {
          label: t('cmd_quick_actions'),
          items: [
            { icon: UserPlus, label: t('create_client') || 'Add Client', kbd: 'C', onSelect: () => setDialogOpen(true) },
            { icon: CreditCard, label: t('run_billing_cycle') || 'Run billing', onSelect: handleRunDunning },
            { icon: Palette, label: t('brand_editor') || 'Branding', onSelect: () => navigate('/branding') },
            { icon: ShoppingBag, label: t('products') || 'Products', onSelect: () => navigate('/products') },
            { icon: BarChart3, label: t('reports') || 'Reports', onSelect: () => navigate('/reports') },
          ],
        },
      ],
    },
    [language, branding?.company_name, clients.length, activeClients.length]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-pulse text-muted-foreground">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-5">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="dxr-sw dxr-sw-brand h-9 w-9"><Store className="h-[18px] w-[18px]" /></span>
        <h1 className="text-[18px] font-extrabold tracking-tight">{branding?.company_name || t('dashboard')}</h1>
        <span className="pill-gold"><BadgeCheck className="h-3.5 w-3.5" />{t('white_label_active') || 'White-label active'}</span>
        <div className="flex-1" />
        <Button variant="outline" onClick={handleRunDunning} disabled={dunningBusy} title={t('run_billing_hint')}>
          {dunningBusy ? t('loading') : (t('run_billing_cycle') || 'Run billing')}
        </Button>
      </div>
      {dunningResult && <p role="status" className="text-sm text-muted-foreground">{dunningResult}</p>}

      {/* Top bento — revenue spotlight + gauge + KPI chips */}
      <div data-tour="stats-section" className="grid gap-4 lg:auto-rows-[116px] lg:grid-cols-12">
        {/* Revenue & margin spotlight */}
        <section className="dxr-tile dxr-ink flex flex-col lg:col-span-8 lg:row-span-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="dxr-eyebrow">{t('revenue_commission') || 'Revenue & Margin'}</div>
              <div className="mt-2 text-[clamp(28px,3.4vw,40px)] font-extrabold leading-none tracking-tight tabular-nums">
                <CountUp value={hasRevenue ? collected : totalMonthlyRevenue} prefix="SAR " />
              </div>
              <div className="mt-1.5 text-[13px] text-white/65">{t('revenue_collected') || 'Collected'} · {activeClients.length} {t('active_subscriptions') || 'subscriptions'}</div>
            </div>
            <div className="text-end">
              <div className="dxr-eyebrow">{t('revenue_net_margin') || 'Net margin'}</div>
              <div className="mt-1 text-[28px] font-extrabold tabular-nums text-white">{netPct}%</div>
            </div>
          </div>

          <div className="mt-auto">
            {revenueLoading ? (
              <div className="animate-pulse py-2 text-sm text-white/60">{t('loading')}</div>
            ) : revenueError ? (
              <div role="alert" className="flex flex-col items-start gap-2">
                <p className="text-sm text-[hsl(6_70%_80%)]">{t('revenue_load_error') || 'Could not load revenue.'}</p>
                <Button variant="secondary" size="sm" onClick={loadRevenue}>{t('retry') || 'Retry'}</Button>
              </div>
            ) : !hasRevenue ? (
              <p className="py-2 text-sm text-white/60">{t('revenue_empty') || 'No settled subscription payments yet.'}</p>
            ) : (
              <>
                <div className="flex h-8 overflow-hidden rounded-[10px]">
                  <div className="flex items-center bg-gradient-to-r from-brand-500 to-brand-600 px-3 text-[12px] font-extrabold text-white" style={{ width: `${netPct}%` }}>
                    {t('revenue_net_margin') || 'Net'} · {formatMoney(net, language)}
                  </div>
                  <div className="flex items-center bg-gradient-to-r from-warning to-gold-600 px-3 text-[12px] font-extrabold text-warning-foreground" style={{ width: `${owedPct}%` }}>
                    {t('revenue_platform_owed') || 'Owed'} · {formatMoney(owed, language)}
                  </div>
                </div>
                <div className="mt-2.5 flex gap-4 text-[12px] text-white/65">
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-brand-500" />{t('revenue_net_margin') || 'Net margin'}</span>
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-warning" />{t('revenue_platform_owed') || 'Owed to platform'}</span>
                </div>
              </>
            )}
          </div>
        </section>

        {/* Active subscriptions gauge */}
        <section className="dxr-tile dxr-hover lg:col-span-4 lg:row-span-2">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-[14px] font-extrabold">{t('active_subscriptions') || 'Active Subscriptions'}</h2>
            <CreditCard className="h-4 w-4 text-muted-foreground" />
          </div>
          <Gauge pct={subsPct} center={activeClients.length} caption={`/ ${clients.length} ${t('clients') || 'clients'}`} />
        </section>

        {/* KPI chips */}
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('total_clients') || 'Total Clients'}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums"><CountUp value={clients.length} /></div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{activeClients.length} {t('active') || 'active'}</div>
        </section>
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('revenue_net_margin') || 'Net Margin'}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums text-success">{formatMoney(net, language)}</div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{t('this_cycle') || 'this billing cycle'}</div>
        </section>
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('revenue_platform_owed') || 'Owed to Platform'}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums text-warning">{formatMoney(owed, language)}</div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{t('due_to_master') || 'due to platform'}</div>
        </section>
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('remaining_slots')}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums">{remainingSlots} of {slotCapacity}</div>
          <div className="mt-auto pt-2">
            <Bar pct={slotCapacity > 0 ? Math.round((remainingSlots / slotCapacity) * 100) : 0} barClassName="bg-gradient-to-r from-warning to-gold-600" />
          </div>
        </section>
      </div>

      {/* Quick actions */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-2.5">
        <button onClick={() => navigate('/branding')} className="chip-link"><Palette className="h-4 w-4" /> {t('brand_editor') || 'Branding'}</button>
        <button onClick={() => navigate('/products')} className="chip-link"><ShoppingBag className="h-4 w-4" /> {t('products') || 'Products'}</button>
        <button onClick={() => navigate('/reports')} className="chip-link"><BarChart3 className="h-4 w-4" /> {t('reports') || 'Reports'}</button>
      </div>

      {zatcaError && (
        <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">{zatcaError}</div>
      )}

      {/* Clients + right rail */}
      <div className="grid items-start gap-[18px] lg:grid-cols-[1fr_320px]">
        {/* Client list */}
        <div className="dxr-tile p-0">
          <div className="flex items-center justify-between px-5 pb-3 pt-5">
            <h2 className="text-[16px] font-extrabold tracking-tight">{t('clients')} <span className="text-muted-foreground">({clients.length})</span></h2>
          </div>
          <div className="overflow-x-auto px-2 pb-2">
            <table className="w-full">
              <thead>
                <tr className="text-[10.5px] font-bold uppercase tracking-wider text-muted-foreground/80">
                  <th className="px-3 py-2.5 text-start">{t('business_name') || 'Client'}</th>
                  <th className="px-3 py-2.5 text-start">{t('subscription_fee') || 'Fee'}</th>
                  <th className="px-3 py-2.5 text-start">{t('status')}</th>
                  <th className="px-3 py-2.5 text-start">{t('zatca_status') || 'ZATCA'}</th>
                  <th className="px-3 py-2.5 text-end">{t('actions') || 'Actions'}</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((c) => (
                  <tr key={c.id} className={cn('border-t border-border/70 transition-colors hover:bg-muted/40', panelClient?.id === c.id && 'bg-brand-50/60 dark:bg-brand-500/10')}>
                    <td className="px-3 py-3">
                      <button type="button" onClick={() => setPanelClientId(c.id)} className="flex items-center gap-2.5 text-start" title={t('manage_features') || 'Manage features'}>
                        <Avatar name={c.business_name} size={34} />
                        <span className="min-w-0">
                          <b className="block truncate font-semibold text-foreground">{c.business_name}</b>
                          <span className="block truncate text-[11.5px] text-muted-foreground">{c.email}</span>
                        </span>
                      </button>
                    </td>
                    <td className="px-3 py-3 font-semibold tabular-nums">{formatMoney(c.subscription_fee || 0, language)}</td>
                    <td className="px-3 py-3">
                      <span className={c.is_active ? 'pill-success' : 'pill-danger'}><span className="h-[7px] w-[7px] rounded-full bg-current" /> {c.is_active ? t('active') : t('inactive')}</span>
                    </td>
                    <td className="px-3 py-3">
                      <span className={c.zatca_enabled ? 'pill-sky' : 'pill-muted'}>{c.zatca_enabled ? (t('zatca_on') || 'On') : (t('zatca_off') || 'Off')}</span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        <button type="button" onClick={() => handleToggleClient(c.id)} disabled={togglingId === c.id} title={c.is_active ? (t('deactivate') || 'Deactivate') : (t('activate') || 'Activate')} className={cn('rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50', c.is_active ? 'bg-danger/10 text-danger hover:bg-danger/15' : 'bg-success/10 text-success hover:bg-success/15')}>
                          {togglingId === c.id ? '…' : c.is_active ? (t('deactivate') || 'Deactivate') : (t('activate') || 'Activate')}
                        </button>
                        <button type="button" onClick={() => setFeatureClient(c)} title={t('features') || 'Features'} className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700"><Sliders className="h-4 w-4" /></button>
                        <button type="button" onClick={() => handleResetPassword(c.id)} disabled={resettingId === c.id} title={t('reset_password') || 'Reset password'} className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700 disabled:opacity-50">{resettingId === c.id ? <span className="text-xs">…</span> : <KeyRound className="h-4 w-4" />}</button>
                        <button type="button" onClick={() => handleToggleZatca(c.id)} disabled={zatcaTogglingId === c.id} title={c.zatca_enabled ? (t('disable_zatca') || 'Disable ZATCA') : (t('enable_zatca') || 'Enable ZATCA')} className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700 disabled:opacity-50">{zatcaTogglingId === c.id ? <span className="text-xs">…</span> : <QrCode className="h-4 w-4" />}</button>
                      </div>
                    </td>
                  </tr>
                ))}
                {clients.length === 0 && (
                  <tr><td colSpan={5} className="py-8 text-center text-sm text-muted-foreground">{t('no_clients') || 'No clients yet.'}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right rail */}
        <div className="flex flex-col gap-[18px]">
          <div className="dxr-tile">
            <h2 className="mb-1 text-sm font-extrabold tracking-tight">{t('feature_overrides') || 'Feature overrides'}</h2>
            {panelClient ? (
              <>
                <div className="mb-1.5 flex items-center gap-2">
                  <Avatar name={panelClient.business_name} size={26} />
                  <b className="text-[13px] font-semibold text-foreground">{panelClient.business_name}</b>
                </div>
                {TOGGLEABLE_FEATURES.map((f) => {
                  const meta = FEATURE_META[f];
                  const Icon = meta?.icon || Box;
                  const checked = featureState[f] ?? true;
                  return (
                    <div key={f} className="flex items-center justify-between gap-3 border-b border-dashed border-border py-3 last:border-b-0">
                      <div className="flex items-center gap-2.5">
                        <span className={cn('dxr-sw h-8 w-8', meta?.tone || 'bg-muted text-muted-foreground')}><Icon className="h-4 w-4" /></span>
                        <div>
                          <b className="block text-[13.5px] font-semibold text-foreground">{meta?.label || (t(f) || f)}</b>
                          <span className="block text-[11.5px] text-muted-foreground">{meta?.desc}</span>
                        </div>
                      </div>
                      <Switch checked={checked} onCheckedChange={(v) => handleToggleFeatureInline(panelClient, f, v)} />
                    </div>
                  );
                })}
              </>
            ) : (
              <p className="py-4 text-sm text-muted-foreground">{t('select_client_features') || 'Select a client to manage features.'}</p>
            )}
          </div>

          {/* White-label preview */}
          <div className="dxr-tile">
            <h2 className="mb-3 text-sm font-extrabold tracking-tight">{t('your_white_label') || 'Your white-label look'}</h2>
            <div className="overflow-hidden rounded-xl border border-border">
              <div className="flex h-16 items-center gap-2.5 px-4" style={{ background: `linear-gradient(135deg, ${brandColor}, ${brandColor})` }}>
                <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-white/20 text-white ring-1 ring-white/25"><Store className="h-4 w-4" /></span>
                <b className="text-sm text-white">{branding?.company_name || t('app_name')}</b>
              </div>
              <div className="flex flex-col gap-2.5 bg-card p-4">
                <div className="h-[9px] w-[70%] rounded bg-muted" />
                <div className="h-[9px] w-[90%] rounded bg-muted" />
                <div className="h-[9px] w-[50%] rounded bg-muted" />
                <div className="mt-1 h-[30px] w-[120px] rounded-md" style={{ background: brandColor }} />
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <span className="h-[26px] w-[26px] rounded-md ring-1 ring-black/10" style={{ background: brandColor }} />
              <span className="h-[26px] w-[26px] rounded-md bg-gold ring-1 ring-black/10" />
              <span className="h-[26px] w-[26px] rounded-md bg-brand-800 ring-1 ring-black/10" />
            </div>
            <Button onClick={() => navigate('/branding')} className="mt-4 w-full shadow-brand"><Palette className="h-4 w-4" /> {t('edit_branding') || 'Edit branding'}</Button>
          </div>
        </div>
      </div>

      {/* Commission statements */}
      <section className="dxr-tile" data-testid="commission-statements">
        <div className="mb-3.5 flex items-center justify-between">
          <h2 className="text-[16px] font-extrabold tracking-tight">{t('commission_statements') || 'Commission statements'}</h2>
          <span className="text-[12.5px] text-muted-foreground">{t('per_billing_period') || 'Per billing period'}</span>
        </div>
        {statementsLoading ? (
          <div className="animate-pulse py-4 text-sm text-muted-foreground">{t('loading')}</div>
        ) : statementsError ? (
          <div role="alert" className="flex flex-col items-start gap-2">
            <p className="text-sm text-danger">{t('statements_load_error') || 'Could not load statements.'}</p>
            <Button variant="outline" size="sm" onClick={loadStatements}>{t('retry') || 'Retry'}</Button>
          </div>
        ) : statements.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">{t('statements_empty') || 'No commission statements yet.'}</p>
        ) : (
          <div className="space-y-4">
            {statements.map((stmt) => (
              <div key={`${stmt.period_start}-${stmt.period_end}`} className="overflow-hidden rounded-xl border border-border">
                <div className="flex flex-wrap items-center justify-between gap-2 bg-muted/40 px-4 py-2.5">
                  <div className="text-sm font-semibold text-foreground">{stmt.period_start} <span className="text-muted-foreground">→</span> {stmt.period_end}</div>
                  <div className="flex items-center gap-4 text-[12.5px] tabular-nums">
                    <span className="text-muted-foreground">{t('revenue_collected') || 'Collected'}: <span className="font-semibold text-foreground">{formatMoney(stmt.collected, language)}</span></span>
                    <span className="text-muted-foreground">{t('revenue_platform_owed') || 'Owed'}: <span className="font-semibold text-warning">{formatMoney(stmt.master_owed, language)}</span></span>
                    <span className="text-muted-foreground">{t('revenue_net_margin') || 'Net'}: <span className="font-semibold text-success">{formatMoney(stmt.net, language)}</span></span>
                  </div>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-[12px] text-muted-foreground">
                      <th className="px-4 py-2 text-start font-medium">{t('client') || 'Client'}</th>
                      <th className="px-4 py-2 text-end font-medium">{t('revenue_collected') || 'Collected'}</th>
                      <th className="px-4 py-2 text-end font-medium">{t('revenue_platform_owed') || 'Owed'}</th>
                      <th className="px-4 py-2 text-end font-medium">{t('revenue_net_margin') || 'Net'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stmt.by_client.map((line) => (
                      <tr key={line.client_id} className="border-b border-border last:border-0">
                        <td className="px-4 py-2 text-foreground">{line.business_name || `#${line.client_id}`}</td>
                        <td className="px-4 py-2 text-end tabular-nums text-foreground">{formatMoney(line.collected, language)}</td>
                        <td className="px-4 py-2 text-end tabular-nums text-warning">{formatMoney(line.master_owed, language)}</td>
                        <td className="px-4 py-2 text-end tabular-nums text-success">{formatMoney(line.net, language)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ===== Dialogs ===== */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogTrigger asChild><span className="hidden" /></DialogTrigger>
        <DialogContent>
          <DialogHeader><DialogTitle>{t('create_client')}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <Input placeholder={t('business_name')} value={newClientForm.business_name} onChange={(e) => setNewClientForm({ ...newClientForm, business_name: e.target.value })} />
            <Input placeholder={t('email')} value={newClientForm.email} onChange={(e) => setNewClientForm({ ...newClientForm, email: e.target.value })} />
            <Input placeholder={t('phone')} value={newClientForm.phone} onChange={(e) => setNewClientForm({ ...newClientForm, phone: e.target.value })} />
            <div className="flex gap-2">
              <Input type="number" min={0} step="0.01" placeholder={t('subscription_fee')} value={newClientForm.subscription_fee} onChange={(e) => setNewClientForm({ ...newClientForm, subscription_fee: e.target.value })} className="flex-1" />
              <Select value={newClientForm.billing_cycle} onValueChange={(v) => setNewClientForm({ ...newClientForm, billing_cycle: v })}>
                <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">{t('monthly') || 'Monthly'}</SelectItem>
                  <SelectItem value="yearly">{t('yearly') || 'Yearly'}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {createError && <p className="text-sm text-danger">{createError}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDialogOpen(false)}>{t('cancel')}</Button>
              <Button onClick={handleCreateClient}>{t('save')}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!createdCreds} onOpenChange={(open) => !open && setCreatedCreds(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{createdCreds?.reset ? (t('password_reset_done') || 'Password reset') : (t('client_created') || 'Client created')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {createdCreds?.email_delivered
                ? (createdCreds?.reset ? (t('new_password_emailed') || 'The new password was emailed to the client.') : (t('credentials_emailed') || 'Login credentials were emailed to the client.'))
                : (t('credentials_show_once') || 'Share these login credentials with the client now — they will not be shown again. They must change the password on first login.')}
            </p>
            <div className="rounded-xl bg-muted p-3 font-mono text-sm text-foreground">
              <div>{t('email')}: {createdCreds?.email}</div>
              <div>{t('password') || 'Password'}: {createdCreds?.temp_password}</div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { if (createdCreds) navigator.clipboard?.writeText(`Email: ${createdCreds.email}\nPassword: ${createdCreds.temp_password}`); }}>{t('copy') || 'Copy'}</Button>
              <Button onClick={() => setCreatedCreds(null)}>{t('done') || 'Done'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!featureClient} onOpenChange={(open) => !open && setFeatureClient(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t('features') || 'Features'} — {featureClient?.business_name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('feature_toggle_hint') || 'Enable or disable capabilities for this client. Features are on by default.'}</p>
            {TOGGLEABLE_FEATURES.map((f) => (
              <div key={f} className="flex items-center justify-between gap-2">
                <span className="text-foreground/90">{t(f) || f}</span>
                <div className="flex gap-2">
                  <Button size="sm" variant="success" disabled={featureBusy} onClick={() => handleSetFeature(f, true)} className="text-xs">{t('enable') || 'Enable'}</Button>
                  <Button size="sm" variant="outline-danger" disabled={featureBusy} onClick={() => handleSetFeature(f, false)} className="text-xs">{t('disable') || 'Disable'}</Button>
                </div>
              </div>
            ))}
            <div className="flex justify-end pt-2"><Button onClick={() => setFeatureClient(null)}>{t('done') || 'Done'}</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
