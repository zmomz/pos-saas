import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { client, getAgentClients, getAgentBranding, getAgentRevenue, createNewClient, toggleClient, setClientZatca, setClientFeature, resetClientPassword, runDunning, type AgentRevenue } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import StatCard from '@/components/dashboard/StatCard';
import { PageHeader, SectionHeading } from '@/components/dashboard/PageHeader';
import { Users, DollarSign, CreditCard, Clock, UserPlus, Palette, ShoppingBag, BarChart3, TrendingUp } from 'lucide-react';

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
  package_type: string;
  client_slots: number;
  used_slots: number;
}

export default function AgentDashboard() {
  const [clients, setClients] = useState<ClientItem[]>([]);
  const [branding, setBranding] = useState<Branding | null>(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newClientForm, setNewClientForm] = useState({ business_name: '', email: '', phone: '', subscription_fee: '', billing_cycle: 'monthly' });
  // AG-03: per-client feature-toggle dialog. The toggleable feature set mirrors
  // the backend require_feature gates (default-enabled until explicitly disabled).
  const [featureClient, setFeatureClient] = useState<ClientItem | null>(null);
  const [featureBusy, setFeatureBusy] = useState(false);
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
  // Dunning sweep (CL-06)
  const [dunningBusy, setDunningBusy] = useState(false);
  const [dunningResult, setDunningResult] = useState<string | null>(null);
  const navigate = useNavigate();
  const { t, language } = useLanguage();

  useEffect(() => {
    loadData();
    loadRevenue();
  }, []);

  async function loadData() {
    try {
      const [clientData, brandData] = await Promise.all([getAgentClients(), getAgentBranding()]);
      // API returns { items, total, remaining_slots }; tolerate array/clients shapes too.
      setClients(Array.isArray(clientData) ? clientData : (clientData?.items || clientData?.clients || []));
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

  async function handleLogout() {
    await client.auth.logout();
    navigate('/');
  }

  // Toggleable features matching the backend require_feature() gates (AG-03).
  const TOGGLEABLE_FEATURES = ['inventory', 'discounts', 'loyalty', 'zatca', 'email_receipts'];

  const remainingSlots = (branding?.client_slots || 0) - (branding?.used_slots || 0);
  const activeClients = clients.filter((c) => c.is_active);
  const totalMonthlyRevenue = activeClients.reduce((sum, c) => sum + (c.subscription_fee || 0), 0);
  const avgRevenuePerClient = activeClients.length > 0 ? totalMonthlyRevenue / activeClients.length : 0;

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

      {/* Stats */}
      <div data-tour="stats-section" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Users} tone="brand" label={t('total_clients') || 'Total Clients'} value={clients.length} />
        <StatCard icon={DollarSign} tone="emerald" label={t('total_monthly_revenue') || 'Monthly Revenue'} value={formatMoney(totalMonthlyRevenue, language)} />
        <StatCard icon={CreditCard} tone="violet" label={t('active_subscriptions') || 'Active Subscriptions'} value={activeClients.length} />
        <StatCard icon={Clock} tone="amber" label={t('remaining_slots') || 'Remaining Slots'} value={remainingSlots} />
      </div>

      {/* Revenue / commission panel (RSL-01, F-029): real settled-subscription
          economics from the split ledger — collected, owed to platform, net margin. */}
      <Card className="rounded-2xl shadow-card">
        <CardHeader className="flex flex-row items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/15">
            <TrendingUp className="h-5 w-5 text-emerald-600 dark:text-emerald-300" />
          </span>
          <CardTitle className="text-base text-foreground">
            {t('revenue_commission') || 'Revenue & Margin'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {revenueLoading ? (
            <div className="animate-pulse text-sm text-muted-foreground">{t('loading')}</div>
          ) : revenueError ? (
            <div role="alert" className="flex flex-col items-start gap-2">
              <p className="text-sm text-red-600 dark:text-red-300">
                {t('revenue_load_error') || 'Could not load revenue.'}
              </p>
              <Button variant="outline" size="sm" onClick={loadRevenue}>
                {t('retry') || 'Retry'}
              </Button>
            </div>
          ) : !revenue || revenue.payments === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t('revenue_empty') || 'No settled subscription payments yet.'}
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="rounded-xl bg-muted/40 p-4">
                <p className="text-sm text-muted-foreground">{t('revenue_collected') || 'Collected'}</p>
                <p className="text-xl font-bold text-foreground">{formatMoney(revenue.collected, language)}</p>
              </div>
              <div className="rounded-xl bg-muted/40 p-4">
                <p className="text-sm text-muted-foreground">{t('revenue_platform_owed') || 'Owed to platform'}</p>
                <p className="text-xl font-bold text-amber-600 dark:text-amber-400">{formatMoney(revenue.master_owed, language)}</p>
              </div>
              <div className="rounded-xl bg-muted/40 p-4">
                <p className="text-sm text-muted-foreground">{t('revenue_net_margin') || 'Net margin'}</p>
                <p className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{formatMoney(revenue.net, language)}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick Actions */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-3">
        <Button variant="outline" onClick={() => navigate('/branding')}>
          <Palette className="h-4 w-4" />
          {t('brand_editor') || 'Branding'}
        </Button>
        <Button variant="outline" onClick={() => navigate('/products')}>
          <ShoppingBag className="h-4 w-4" />
          {t('products') || 'Products'}
        </Button>
        <Button variant="outline" onClick={() => navigate('/reports')}>
          <BarChart3 className="h-4 w-4" />
          {t('reports') || 'Reports'}
        </Button>
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

        <div className="overflow-x-auto rounded-2xl border border-border bg-card shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="p-3 text-start font-medium">{t('business_name')}</th>
                <th className="p-3 text-start font-medium">{t('email')}</th>
                <th className="p-3 text-start font-medium">{t('phone')}</th>
                <th className="p-3 text-start font-medium">{t('subscription_fee')}</th>
                <th className="p-3 text-start font-medium">{t('status')}</th>
                <th className="p-3 text-start font-medium">{t('zatca_status')}</th>
                <th className="p-3 text-start font-medium">{t('actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.id} className="border-t border-border text-foreground/80 transition-colors hover:bg-muted/40">
                  <td className="p-3 font-medium text-foreground">{c.business_name}</td>
                  <td className="p-3">{c.email}</td>
                  <td className="p-3">{c.phone}</td>
                  <td className="p-3">{formatMoney(c.subscription_fee || 0, language)}</td>
                  <td className="p-3">
                    <Badge className={c.is_active ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'}>
                      {c.is_active ? t('active') : t('inactive')}
                    </Badge>
                  </td>
                  <td className="p-3">
                    <Badge className={c.zatca_enabled ? 'bg-emerald-600 text-white' : 'bg-muted text-muted-foreground'}>
                      {c.zatca_enabled ? (t('zatca_on') || 'On') : (t('zatca_off') || 'Off')}
                    </Badge>
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2 flex-wrap">
                      <Button
                        size="sm"
                        variant={c.is_active ? 'destructive' : 'default'}
                        onClick={() => handleToggleClient(c.id)}
                        disabled={togglingId === c.id}
                        className={
                          c.is_active
                            ? 'bg-red-600 hover:bg-red-700 text-white text-xs'
                            : 'bg-emerald-600 hover:bg-emerald-700 text-white text-xs'
                        }
                      >
                        {togglingId === c.id
                          ? '...'
                          : c.is_active
                            ? (t('deactivate') || 'Deactivate')
                            : (t('activate') || 'Activate')}
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setFeatureClient(c)} className="text-xs">
                        {t('features') || 'Features'}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleResetPassword(c.id)}
                        disabled={resettingId === c.id}
                        title={t('reset_password') || 'Reset password'}
                        className="text-xs"
                      >
                        {resettingId === c.id ? '...' : (t('reset_password') || 'Reset Password')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleToggleZatca(c.id)}
                        disabled={zatcaTogglingId === c.id}
                        title={c.zatca_enabled ? (t('disable_zatca') || 'Disable ZATCA') : (t('enable_zatca') || 'Enable ZATCA')}
                        className="text-xs"
                      >
                        {zatcaTogglingId === c.id
                          ? '...'
                          : c.zatca_enabled
                            ? (t('disable_zatca') || 'Disable ZATCA')
                            : (t('enable_zatca') || 'Enable ZATCA')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
