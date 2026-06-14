import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { client, getAgentClients, getAgentBranding, getAgentRevenue, getAgentCommissionStatements, createNewClient, toggleClient, setClientZatca, setClientFeature, resetClientPassword, runDunning, type AgentRevenue, type CommissionStatement } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import StatTile from '@/components/dashboard/StatTile';
import { Avatar } from '@/components/dashboard/Avatar';
import { Switch } from '@/components/ui/switch';
import { PageHeader, SectionHeading } from '@/components/dashboard/PageHeader';
import { Users, DollarSign, CreditCard, Clock, UserPlus, Palette, ShoppingBag, BarChart3, TrendingUp, Box, Percent, Star, QrCode, Mail, Sliders, Eye, KeyRound, Store } from 'lucide-react';

interface ClientItem {
  id: number;
  business_name: string;
  email: string;
  phone: string;
  is_active: boolean;
  subscription_fee: number;
  // ZA-09: whether ZATCA e-invoicing is on for this client (default ON).
  zatca_enabled: boolean;
}

interface Branding {
  company_name: string;
  logo_url: string;
  primary_color: string;
}

export default function AgentDashboard() {
  const [clients, setClients] = useState<ClientItem[]>([]);
  // H9 (ISSUE-023): real slot economics from GET /agent/clients. `remainingSlots`
  // is the agent's free capacity; `totalClients` is the count of provisioned
  // clients (each occupies a slot), so capacity = remaining + used.
  const [remainingSlots, setRemainingSlots] = useState(0);
  const [totalClients, setTotalClients] = useState(0);
  const [branding, setBranding] = useState<Branding | null>(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newClientForm, setNewClientForm] = useState({ business_name: '', email: '', phone: '', subscription_fee: '', billing_cycle: 'monthly' });
  // AG-03: per-client feature-toggle dialog. The toggleable feature set mirrors
  // the backend require_feature gates (default-enabled until explicitly disabled).
  const [featureClient, setFeatureClient] = useState<ClientItem | null>(null);
  const [featureBusy, setFeatureBusy] = useState(false);
  // AG-03 inline panel (handoff right column): which client the feature-override
  // switches act on, plus a local on/off map. Features are on by default (there
  // is no per-client feature-state read endpoint), so a switch defaults to ON and
  // flipping it calls setClientFeature optimistically.
  const [panelClientId, setPanelClientId] = useState<number | null>(null);
  const [featureState, setFeatureState] = useState<Record<string, boolean>>({});
  // One-time credentials surfaced after provisioning a client (C-1/CL-01). Shown
  // once in a modal so the agent can hand them over; never retrievable again.
  const [createdCreds, setCreatedCreds] = useState<
    { email: string; temp_password: string; email_delivered: boolean; reset?: boolean } | null
  >(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [resettingId, setResettingId] = useState<number | null>(null);
  // ZA-09 (F-022): per-client ZATCA toggle — id being flipped + a transient error.
  const [zatcaTogglingId, setZatcaTogglingId] = useState<number | null>(null);
  const [zatcaError, setZatcaError] = useState<string | null>(null);
  // RSL-01 (F-029): real settled-subscription economics from the commission
  // ledger — collected / owed-to-platform / net margin. Loaded independently so
  // a failure renders this panel's error state, not a blank page.
  const [revenue, setRevenue] = useState<AgentRevenue | null>(null);
  const [revenueLoading, setRevenueLoading] = useState(true);
  const [revenueError, setRevenueError] = useState(false);
  // RSL-02 (ISSUE-055): per-period commission statements with line items by
  // client — loaded independently so a failure only affects this panel.
  const [statements, setStatements] = useState<CommissionStatement[]>([]);
  const [statementsLoading, setStatementsLoading] = useState(true);
  const [statementsError, setStatementsError] = useState(false);
  // Dunning sweep (CL-06)
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
      // API returns AgentClientsResponse { items, total, remaining_slots } (typed in api.ts).
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
      setDunningResult(
        `${t('dunning_done')}: ${result.processed} · ${t('recovered')} ${result.recovered} · ${t('suspended')} ${result.suspended}`
      );
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
      // Surface the one-time login credentials for the new merchant.
      if (created?.temp_password) {
        setCreatedCreds({
          email: created.email,
          temp_password: created.temp_password,
          email_delivered: !!created.email_delivered,
        });
      }
      loadData();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setCreateError(detail || (err instanceof Error ? err.message : 'Create client failed'));
      console.error('Create client failed:', err);
    }
  }

  async function handleToggleClient(clientId: number) {
    setTogglingId(clientId);
    try {
      await toggleClient(clientId);
      setClients((prev) =>
        prev.map((c) => (c.id === clientId ? { ...c, is_active: !c.is_active } : c))
      );
    } catch (err) {
      console.error('Toggle client failed:', err);
    } finally {
      setTogglingId(null);
    }
  }

  // RSL-06: agent resets a locked-out merchant's password and relays the new
  // one-time credential (force-reset on next login).
  async function handleResetPassword(clientId: number) {
    setResettingId(clientId);
    try {
      const result = await resetClientPassword(clientId);
      setCreatedCreds({
        email: result.email,
        temp_password: result.temp_password,
        email_delivered: !!result.email_delivered,
        reset: true,
      });
    } catch (err) {
      console.error('Reset client password failed:', err);
    } finally {
      setResettingId(null);
    }
  }

  // ZA-09 (F-022): flip ZATCA e-invoicing for a client. The sale path honors the
  // flag — off means simplified non-tax receipts. Optimistic update with a
  // rollback on failure so the badge always reflects the real stored policy.
  async function handleToggleZatca(clientId: number) {
    setZatcaTogglingId(clientId);
    setZatcaError(null);
    try {
      const result = await setClientZatca(clientId);
      setClients((prev) =>
        prev.map((c) => (c.id === clientId ? { ...c, zatca_enabled: result.zatca_enabled } : c))
      );
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

  // Inline feature-overrides switch (handoff right column). Optimistic: flip the
  // local switch immediately, persist, and roll back on failure.
  async function handleToggleFeatureInline(client: ClientItem, featureName: string, next: boolean) {
    setFeatureState((prev) => ({ ...prev, [featureName]: next }));
    try {
      await setClientFeature(client.id, featureName, next);
    } catch (err) {
      console.error('Set feature failed:', err);
      setFeatureState((prev) => ({ ...prev, [featureName]: !next }));
    }
  }

  async function handleLogout() {
    await client.auth.logout();
    navigate('/');
  }

  // Toggleable features matching the backend require_feature() gates (AG-03).
  const TOGGLEABLE_FEATURES = ['inventory', 'discounts', 'loyalty', 'zatca', 'email_receipts'];
  // Inline feature-overrides card meta (icon + tint + sub-label), handoff order.
  const FEATURE_META: Record<string, { icon: typeof Box; tone: string; label: string; desc: string }> = {
    inventory: { icon: Box, tone: 'bg-brand-50 text-brand-700', label: t('inventory') || 'Inventory', desc: t('stock_tracking') || 'Stock tracking' },
    discounts: { icon: Percent, tone: 'bg-success/10 text-success', label: t('discounts') || 'Discounts', desc: t('codes_promos') || 'Codes & promos' },
    loyalty: { icon: Star, tone: 'bg-gold-50 text-gold-600', label: t('loyalty') || 'Loyalty program', desc: t('points_rewards') || 'Points & rewards' },
    zatca: { icon: QrCode, tone: 'bg-sky/10 text-sky', label: t('zatca') || 'ZATCA e-invoice', desc: t('qr_receipts') || 'QR receipts' },
    email_receipts: { icon: Mail, tone: 'bg-violet/10 text-violet', label: t('email_receipts') || 'Email receipts', desc: t('auto_send') || 'Auto-send' },
  };

  // Total slot capacity = free slots + provisioned clients (each holds a slot).
  const slotCapacity = remainingSlots + totalClients;
  const activeClients = clients.filter((c) => c.is_active);
  const totalMonthlyRevenue = activeClients.reduce((sum, c) => sum + (c.subscription_fee || 0), 0);
  const avgRevenuePerClient = activeClients.length > 0 ? totalMonthlyRevenue / activeClients.length : 0;
  // Client the inline feature-overrides panel acts on (defaults to the first).
  const panelClient = clients.find((c) => c.id === panelClientId) || clients[0] || null;
  // Brand swatch from branding.primary_color (falls back to the brand token).
  const brandColor = branding?.primary_color || '#1488a6';

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-pulse text-muted-foreground">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <PageHeader
        title={branding?.company_name || t('dashboard')}
        subtitle={t('clients')}
        actions={
          <Button onClick={() => setDialogOpen(true)} className="shadow-brand">
            <UserPlus className="h-4 w-4" />
            {t('create_client') || 'Add Client'}
          </Button>
        }
      />

      {/* Stats — handoff stat tiles. */}
      <div data-tour="stats-section" className="grid grid-cols-1 gap-[18px] sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          icon={Users}
          tone="brand"
          label={t('total_clients') || 'Total Clients'}
          value={clients.length}
          footer={
            <span className="inline-flex items-center gap-1.5 text-success">
              <span className="h-[7px] w-[7px] rounded-full bg-success" /> {activeClients.length} {t('active') || 'active'}
            </span>
          }
        />
        <StatTile
          icon={DollarSign}
          tone="success"
          label={t('total_monthly_revenue') || 'Monthly Revenue'}
          value={formatMoney(totalMonthlyRevenue, language)}
          footer={<span className="text-muted-foreground">{activeClients.length} {t('active_subscriptions') || 'subscriptions'}</span>}
        />
        <StatTile
          icon={CreditCard}
          tone="violet"
          label={t('active_subscriptions') || 'Active Subscriptions'}
          value={activeClients.length}
          valueSmall={clients.length ? `/ ${clients.length}` : undefined}
        />
        <StatTile
          icon={Clock}
          tone="warning"
          label={t('remaining_slots') || 'Remaining Slots'}
          value={remainingSlots}
          valueSmall={slotCapacity ? `of ${slotCapacity}` : undefined}
        />
      </div>

      {/* Revenue & Margin (RSL-01, F-029) — handoff 3-cell margin grid. */}
      <Card className="rounded-2xl border-border shadow-card">
        <CardContent className="p-6">
          <div className="mb-3.5 flex items-center justify-between">
            <h2 className="text-base font-bold tracking-tight text-foreground">{t('revenue_commission') || 'Revenue & Margin'}</h2>
            <span className="text-[12.5px] text-muted-foreground">{t('based_on_current_month') || "Based on current month's subscriptions"}</span>
          </div>
          {revenueLoading ? (
            <div className="animate-pulse py-4 text-sm text-muted-foreground">{t('loading')}</div>
          ) : revenueError ? (
            <div role="alert" className="flex flex-col items-start gap-2">
              <p className="text-sm text-danger">{t('revenue_load_error') || 'Could not load revenue.'}</p>
              <Button variant="outline" size="sm" onClick={loadRevenue}>{t('retry') || 'Retry'}</Button>
            </div>
          ) : !revenue || revenue.payments === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">{t('revenue_empty') || 'No settled subscription payments yet.'}</p>
          ) : (
            <div className="grid grid-cols-1 gap-px overflow-hidden rounded-xl bg-border sm:grid-cols-3">
              <div className="bg-card p-4">
                <div className="text-xs font-medium text-muted-foreground">{t('revenue_collected') || 'Collected'}</div>
                <div className="mt-1.5 text-[21px] font-extrabold tracking-tight tabular-nums text-foreground">{formatMoney(revenue.collected, language)}</div>
              </div>
              <div className="bg-card p-4">
                <div className="text-xs font-medium text-muted-foreground">{t('revenue_platform_owed') || 'Owed to platform'}</div>
                <div className="mt-1.5 text-[21px] font-extrabold tracking-tight tabular-nums text-warning">{formatMoney(revenue.master_owed, language)}</div>
              </div>
              <div className="bg-card p-4">
                <div className="text-xs font-medium text-muted-foreground">{t('revenue_net_margin') || 'Net margin'}</div>
                <div className="mt-1.5 text-[21px] font-extrabold tracking-tight tabular-nums text-success">{formatMoney(revenue.net, language)}</div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Commission statements (RSL-02, ISSUE-055) — one per billing period,
          with line items by client; each reconciles (collected = owed + net). */}
      <Card className="rounded-2xl border-border shadow-card">
        <CardContent className="p-6" data-testid="commission-statements">
          <div className="mb-3.5 flex items-center justify-between">
            <h2 className="text-base font-bold tracking-tight text-foreground">{t('commission_statements') || 'Commission statements'}</h2>
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
                    <div className="text-sm font-semibold text-foreground">
                      {stmt.period_start} <span className="text-muted-foreground">→</span> {stmt.period_end}
                    </div>
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
        </CardContent>
      </Card>

      {/* Quick Actions — handoff chips. */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-2.5">
        <button onClick={() => navigate('/branding')} className="chip-link">
          <Palette className="h-4 w-4" /> {t('brand_editor') || 'Branding'}
        </button>
        <button onClick={() => navigate('/products')} className="chip-link">
          <ShoppingBag className="h-4 w-4" /> {t('products') || 'Products'}
        </button>
        <button onClick={() => navigate('/reports')} className="chip-link">
          <BarChart3 className="h-4 w-4" /> {t('reports') || 'Reports'}
        </button>
      </div>

      {/* Clients */}
      <section>
        <SectionHeading
          title={`${t('clients')} (${clients.length})`}
          actions={
            <>
              {dunningResult && (
                <span role="status" className="text-sm text-muted-foreground">{dunningResult}</span>
              )}
              <Button
                variant="outline"
                onClick={handleRunDunning}
                disabled={dunningBusy}
                title={t('run_billing_hint')}
              >
                {dunningBusy ? t('loading') : (t('run_billing_cycle') || 'Run billing')}
              </Button>
              <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogTrigger asChild>
                  <Button className="shadow-brand">{t('create_client')}</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{t('create_client')}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4">
                    <Input
                      placeholder={t('business_name')}
                      value={newClientForm.business_name}
                      onChange={(e) => setNewClientForm({ ...newClientForm, business_name: e.target.value })}
                    />
                    <Input
                      placeholder={t('email')}
                      value={newClientForm.email}
                      onChange={(e) => setNewClientForm({ ...newClientForm, email: e.target.value })}
                    />
                    <Input
                      placeholder={t('phone')}
                      value={newClientForm.phone}
                      onChange={(e) => setNewClientForm({ ...newClientForm, phone: e.target.value })}
                    />
                    {/* CL-03: subscription fee + billing cycle */}
                    <div className="flex gap-2">
                      <Input
                        type="number"
                        min={0}
                        step="0.01"
                        placeholder={t('subscription_fee')}
                        value={newClientForm.subscription_fee}
                        onChange={(e) => setNewClientForm({ ...newClientForm, subscription_fee: e.target.value })}
                        className="flex-1"
                      />
                      <Select
                        value={newClientForm.billing_cycle}
                        onValueChange={(v) => setNewClientForm({ ...newClientForm, billing_cycle: v })}
                      >
                        <SelectTrigger className="w-32">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="monthly">{t('monthly') || 'Monthly'}</SelectItem>
                          <SelectItem value="yearly">{t('yearly') || 'Yearly'}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    {createError && (
                      <p className="text-sm text-red-500">{createError}</p>
                    )}
                    <div className="flex gap-2 justify-end">
                      <Button variant="outline" onClick={() => setDialogOpen(false)}>
                        {t('cancel')}
                      </Button>
                      <Button onClick={handleCreateClient}>
                        {t('save')}
                      </Button>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>
            </>
          }
        />

        {/* One-time credentials for a newly provisioned client (C-1/CL-01) */}
        <Dialog open={!!createdCreds} onOpenChange={(open) => !open && setCreatedCreds(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {createdCreds?.reset
                  ? (t('password_reset_done') || 'Password reset')
                  : (t('client_created') || 'Client created')}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {createdCreds?.email_delivered
                  ? (createdCreds?.reset
                    ? (t('new_password_emailed') || 'The new password was emailed to the client.')
                    : (t('credentials_emailed') || 'Login credentials were emailed to the client.'))
                  : (t('credentials_show_once') ||
                    'Share these login credentials with the client now — they will not be shown again. They must change the password on first login.')}
              </p>
              <div className="rounded-xl p-3 font-mono text-sm bg-muted text-foreground">
                <div>{t('email')}: {createdCreds?.email}</div>
                <div>{t('password') || 'Password'}: {createdCreds?.temp_password}</div>
              </div>
              <div className="flex gap-2 justify-end">
                <Button
                  variant="outline"
                  onClick={() => {
                    if (createdCreds) {
                      navigator.clipboard?.writeText(
                        `Email: ${createdCreds.email}\nPassword: ${createdCreds.temp_password}`
                      );
                    }
                  }}
                >
                  {t('copy') || 'Copy'}
                </Button>
                <Button onClick={() => setCreatedCreds(null)}>{t('done') || 'Done'}</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* AG-03: per-client feature toggles */}
        <Dialog open={!!featureClient} onOpenChange={(open) => !open && setFeatureClient(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('features') || 'Features'} — {featureClient?.business_name}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {t('feature_toggle_hint') || 'Enable or disable capabilities for this client. Features are on by default.'}
              </p>
              {TOGGLEABLE_FEATURES.map((f) => (
                <div key={f} className="flex items-center justify-between gap-2">
                  <span className="text-foreground/90">{t(f) || f}</span>
                  <div className="flex gap-2">
                    <Button size="sm" disabled={featureBusy} onClick={() => handleSetFeature(f, true)} className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs">
                      {t('enable') || 'Enable'}
                    </Button>
                    <Button size="sm" disabled={featureBusy} variant="outline" onClick={() => handleSetFeature(f, false)} className="border-red-300 text-red-600 hover:bg-red-50 text-xs dark:border-red-500/40 dark:text-red-300 dark:hover:bg-red-500/10">
                      {t('disable') || 'Disable'}
                    </Button>
                  </div>
                </div>
              ))}
              <div className="flex justify-end pt-2">
                <Button onClick={() => setFeatureClient(null)}>{t('done') || 'Done'}</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {zatcaError && (
          <div role="alert" className="mb-3 rounded-xl px-3 py-2 text-sm bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-700/40">
            {zatcaError}
          </div>
        )}

        {/* Handoff split: client list (left) + feature overrides & brand preview (right). */}
        <div className="grid items-start gap-[18px] lg:grid-cols-[1fr_320px]">
          {/* Client list */}
          <Card className="rounded-2xl border-border shadow-card">
            <CardContent className="overflow-x-auto p-6">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border text-[11.5px] font-bold uppercase tracking-wider text-muted-foreground/80">
                    <th className="py-2.5 pe-3 text-start font-bold">{t('business_name') || 'Client'}</th>
                    <th className="py-2.5 pe-3 text-start font-bold">{t('subscription_fee') || 'Fee'}</th>
                    <th className="py-2.5 pe-3 text-start font-bold">{t('status')}</th>
                    <th className="py-2.5 pe-3 text-start font-bold">{t('zatca_status') || 'ZATCA'}</th>
                    <th className="py-2.5 text-end font-bold">{t('actions') || 'Actions'}</th>
                  </tr>
                </thead>
                <tbody>
                  {clients.map((c) => (
                    <tr
                      key={c.id}
                      className={`border-b border-border last:border-b-0 transition-colors hover:bg-muted/40 ${panelClient?.id === c.id ? 'bg-brand-50/60' : ''}`}
                    >
                      <td className="py-3.5 pe-3">
                        <button
                          type="button"
                          onClick={() => setPanelClientId(c.id)}
                          className="flex items-center gap-2.5 text-start"
                          title={t('manage_features') || 'Manage features'}
                        >
                          <Avatar name={c.business_name} size={34} />
                          <span className="min-w-0">
                            <b className="block truncate font-semibold text-foreground">{c.business_name}</b>
                            <span className="block truncate text-[11.5px] text-muted-foreground">{c.email}</span>
                          </span>
                        </button>
                      </td>
                      <td className="py-3.5 pe-3 font-semibold tabular-nums text-foreground">{formatMoney(c.subscription_fee || 0, language)}</td>
                      <td className="py-3.5 pe-3">
                        <span className={c.is_active ? 'pill-success' : 'pill-danger'}>
                          <span className="h-[7px] w-[7px] rounded-full bg-current" /> {c.is_active ? t('active') : t('inactive')}
                        </span>
                      </td>
                      <td className="py-3.5 pe-3">
                        <span className={c.zatca_enabled ? 'pill-sky' : 'pill-muted'}>
                          {c.zatca_enabled ? (t('zatca_on') || 'On') : (t('zatca_off') || 'Off')}
                        </span>
                      </td>
                      <td className="py-3.5">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleToggleClient(c.id)}
                            disabled={togglingId === c.id}
                            title={c.is_active ? (t('deactivate') || 'Deactivate') : (t('activate') || 'Activate')}
                            className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${c.is_active ? 'bg-danger/10 text-danger hover:bg-danger/15' : 'bg-success/10 text-success hover:bg-success/15'}`}
                          >
                            {togglingId === c.id ? '…' : c.is_active ? (t('deactivate') || 'Deactivate') : (t('activate') || 'Activate')}
                          </button>
                          <button
                            type="button"
                            onClick={() => setFeatureClient(c)}
                            title={t('features') || 'Features'}
                            className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700"
                          >
                            <Sliders className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleResetPassword(c.id)}
                            disabled={resettingId === c.id}
                            title={t('reset_password') || 'Reset password'}
                            className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700 disabled:opacity-50"
                          >
                            {resettingId === c.id ? <span className="text-xs">…</span> : <KeyRound className="h-4 w-4" />}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleToggleZatca(c.id)}
                            disabled={zatcaTogglingId === c.id}
                            title={c.zatca_enabled ? (t('disable_zatca') || 'Disable ZATCA') : (t('enable_zatca') || 'Enable ZATCA')}
                            className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700 disabled:opacity-50"
                          >
                            {zatcaTogglingId === c.id ? <span className="text-xs">…</span> : <QrCode className="h-4 w-4" />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {clients.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-sm text-muted-foreground">{t('no_clients') || 'No clients yet.'}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Right column: feature overrides + white-label preview. */}
          <div className="flex flex-col gap-[18px]">
            <Card className="rounded-2xl border-border shadow-card">
              <CardContent className="p-6">
                <h2 className="mb-1 text-sm font-bold tracking-tight text-foreground">{t('feature_overrides') || 'Feature overrides'}</h2>
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
                            <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${meta?.tone || 'bg-muted text-muted-foreground'}`}>
                              <Icon className="h-4 w-4" />
                            </span>
                            <div>
                              <b className="block text-[13.5px] font-semibold text-foreground">{meta?.label || (t(f) || f)}</b>
                              <span className="block text-[11.5px] text-muted-foreground">{meta?.desc}</span>
                            </div>
                          </div>
                          <Switch
                            checked={checked}
                            onCheckedChange={(v) => handleToggleFeatureInline(panelClient, f, v)}
                          />
                        </div>
                      );
                    })}
                  </>
                ) : (
                  <p className="py-4 text-sm text-muted-foreground">{t('select_client_features') || 'Select a client to manage features.'}</p>
                )}
              </CardContent>
            </Card>

            {/* White-label preview (handoff). */}
            <Card className="rounded-2xl border-border shadow-card">
              <CardContent className="p-6">
                <h2 className="mb-3 text-sm font-bold tracking-tight text-foreground">{t('your_white_label') || 'Your white-label look'}</h2>
                <div className="overflow-hidden rounded-xl border border-border">
                  <div className="flex h-16 items-center gap-2.5 px-4" style={{ background: `linear-gradient(135deg, ${brandColor}, ${brandColor})` }}>
                    <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-white/20 ring-1 ring-white/25 text-white">
                      <Store className="h-4 w-4" />
                    </span>
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
                <Button onClick={() => navigate('/branding')} className="mt-4 w-full shadow-brand">
                  <Palette className="h-4 w-4" /> {t('edit_branding') || 'Edit branding'}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    </div>
  );
}
