import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { client, getAgentClients, getAgentBranding, getAgentRevenue, createNewClient, toggleClient, setClientFeature, resetClientPassword, type AgentRevenue } from '@/lib/api';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { useTheme } from '@/contexts/ThemeContext';
import { Users, DollarSign, CreditCard, Clock, UserPlus, Palette, ShoppingBag, BarChart3, TrendingUp } from 'lucide-react';

interface ClientItem {
  id: number;
  business_name: string;
  email: string;
  phone: string;
  is_active: boolean;
  subscription_fee: number;
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
  // RSL-01 (F-029): real settled-subscription economics from the commission
  // ledger — collected / owed-to-platform / net margin. Loaded independently so
  // a failure renders this panel's error state, not a blank page.
  const [revenue, setRevenue] = useState<AgentRevenue | null>(null);
  const [revenueLoading, setRevenueLoading] = useState(true);
  const [revenueError, setRevenueError] = useState(false);
  const navigate = useNavigate();
  const { t, language, setLanguage } = useLanguage();
  const { isDark } = useTheme();

  useEffect(() => {
    loadData();
    loadRevenue();
  }, []);

  async function loadData() {
    try {
      const [clientData, brandData] = await Promise.all([getAgentClients(), getAgentBranding()]);
      setClients(clientData?.clients || clientData || []);
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
        <div className={`animate-pulse ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Enhanced Stats Section */}
      <div data-tour="stats-section" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className={`${isDark ? 'bg-gradient-to-br from-blue-900/40 to-slate-800 border-blue-700/40' : 'bg-gradient-to-br from-blue-50 to-white border-blue-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-blue-600/20' : 'bg-blue-100'}`}>
              <Users className={`h-6 w-6 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-blue-300' : 'text-blue-600'}`}>{t('total_clients') || 'Total Clients'}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{clients.length}</p>
            </div>
          </CardContent>
        </Card>

        <Card className={`${isDark ? 'bg-gradient-to-br from-green-900/40 to-slate-800 border-green-700/40' : 'bg-gradient-to-br from-green-50 to-white border-green-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-green-600/20' : 'bg-green-100'}`}>
              <DollarSign className={`h-6 w-6 ${isDark ? 'text-green-400' : 'text-green-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-green-300' : 'text-green-600'}`}>{t('total_monthly_revenue') || 'Monthly Revenue'}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{formatMoney(totalMonthlyRevenue, language)}</p>
            </div>
          </CardContent>
        </Card>

        <Card className={`${isDark ? 'bg-gradient-to-br from-purple-900/40 to-slate-800 border-purple-700/40' : 'bg-gradient-to-br from-purple-50 to-white border-purple-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-purple-600/20' : 'bg-purple-100'}`}>
              <CreditCard className={`h-6 w-6 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-purple-300' : 'text-purple-600'}`}>{t('active_subscriptions') || 'Active Subscriptions'}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{activeClients.length}</p>
            </div>
          </CardContent>
        </Card>

        <Card className={`${isDark ? 'bg-gradient-to-br from-amber-900/40 to-slate-800 border-amber-700/40' : 'bg-gradient-to-br from-amber-50 to-white border-amber-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-amber-600/20' : 'bg-amber-100'}`}>
              <Clock className={`h-6 w-6 ${isDark ? 'text-amber-400' : 'text-amber-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-amber-300' : 'text-amber-600'}`}>{t('remaining_slots') || 'Remaining Slots'}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{remainingSlots}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Revenue / commission panel (RSL-01, F-029): real settled-subscription
          economics from the split ledger — collected, owed to platform, net margin. */}
      <Card className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
        <CardHeader className="flex flex-row items-center gap-2">
          <TrendingUp className={`h-5 w-5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
          <CardTitle className={isDark ? 'text-white' : 'text-slate-900'}>
            {t('revenue_commission') || 'Revenue & Margin'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {revenueLoading ? (
            <div className={`animate-pulse text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              {t('loading')}
            </div>
          ) : revenueError ? (
            <div role="alert" className="flex flex-col items-start gap-2">
              <p className={`text-sm ${isDark ? 'text-red-300' : 'text-red-600'}`}>
                {t('revenue_load_error') || 'Could not load revenue.'}
              </p>
              <Button variant="outline" size="sm" onClick={loadRevenue}>
                {t('retry') || 'Retry'}
              </Button>
            </div>
          ) : !revenue || revenue.payments === 0 ? (
            <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              {t('revenue_empty') || 'No settled subscription payments yet.'}
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>{t('revenue_collected') || 'Collected'}</p>
                <p className={`text-xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{formatMoney(revenue.collected, language)}</p>
              </div>
              <div>
                <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>{t('revenue_platform_owed') || 'Owed to platform'}</p>
                <p className={`text-xl font-bold ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>{formatMoney(revenue.master_owed, language)}</p>
              </div>
              <div>
                <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>{t('revenue_net_margin') || 'Net margin'}</p>
                <p className={`text-xl font-bold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{formatMoney(revenue.net, language)}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick Actions */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-3">
        <Button
          onClick={() => setDialogOpen(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white"
        >
          <UserPlus className="h-4 w-4 mr-2" />
          {t('create_client') || 'Add Client'}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/branding')}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <Palette className="h-4 w-4 mr-2" />
          {t('brand_editor') || 'Branding'}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/products')}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <ShoppingBag className="h-4 w-4 mr-2" />
          {t('products') || 'Products'}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/reports')}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <BarChart3 className="h-4 w-4 mr-2" />
          {t('reports') || 'Reports'}
        </Button>
      </div>

      {/* Clients */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('clients')} ({clients.length})</h2>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-blue-600 hover:bg-blue-700 text-white">{t('create_client')}</Button>
            </DialogTrigger>
            <DialogContent className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
              <DialogHeader>
                <DialogTitle className={isDark ? 'text-white' : 'text-slate-900'}>{t('create_client')}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <Input
                  placeholder={t('business_name')}
                  value={newClientForm.business_name}
                  onChange={(e) => setNewClientForm({ ...newClientForm, business_name: e.target.value })}
                  className={isDark ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300 text-slate-900'}
                />
                <Input
                  placeholder={t('email')}
                  value={newClientForm.email}
                  onChange={(e) => setNewClientForm({ ...newClientForm, email: e.target.value })}
                  className={isDark ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300 text-slate-900'}
                />
                <Input
                  placeholder={t('phone')}
                  value={newClientForm.phone}
                  onChange={(e) => setNewClientForm({ ...newClientForm, phone: e.target.value })}
                  className={isDark ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300 text-slate-900'}
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
                    className={isDark ? 'bg-slate-700 border-slate-600 text-white flex-1' : 'bg-white border-gray-300 text-slate-900 flex-1'}
                  />
                  <Select
                    value={newClientForm.billing_cycle}
                    onValueChange={(v) => setNewClientForm({ ...newClientForm, billing_cycle: v })}
                  >
                    <SelectTrigger className={isDark ? 'bg-slate-700 border-slate-600 text-white w-32' : 'bg-white border-gray-300 text-slate-900 w-32'}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className={isDark ? 'bg-slate-800 border-slate-600' : 'bg-white border-gray-200'}>
                      <SelectItem value="monthly" className={isDark ? 'text-white hover:bg-slate-700' : 'text-slate-900 hover:bg-gray-100'}>{t('monthly') || 'Monthly'}</SelectItem>
                      <SelectItem value="yearly" className={isDark ? 'text-white hover:bg-slate-700' : 'text-slate-900 hover:bg-gray-100'}>{t('yearly') || 'Yearly'}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {createError && (
                  <p className="text-sm text-red-500">{createError}</p>
                )}
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={() => setDialogOpen(false)} className={isDark ? 'border-slate-600 text-slate-300' : 'border-gray-300 text-gray-700'}>
                    {t('cancel')}
                  </Button>
                  <Button onClick={handleCreateClient} className="bg-blue-600 hover:bg-blue-700 text-white">
                    {t('save')}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>

          {/* One-time credentials for a newly provisioned client (C-1/CL-01) */}
          <Dialog open={!!createdCreds} onOpenChange={(open) => !open && setCreatedCreds(null)}>
            <DialogContent className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
              <DialogHeader>
                <DialogTitle className={isDark ? 'text-white' : 'text-slate-900'}>
                  {createdCreds?.reset
                    ? (t('password_reset_done') || 'Password reset')
                    : (t('client_created') || 'Client created')}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <p className={`text-sm ${isDark ? 'text-slate-300' : 'text-gray-600'}`}>
                  {createdCreds?.email_delivered
                    ? (createdCreds?.reset
                      ? (t('new_password_emailed') || 'The new password was emailed to the client.')
                      : (t('credentials_emailed') || 'Login credentials were emailed to the client.'))
                    : (t('credentials_show_once') ||
                      'Share these login credentials with the client now — they will not be shown again. They must change the password on first login.')}
                </p>
                <div className={`rounded-md p-3 font-mono text-sm ${isDark ? 'bg-slate-900 text-slate-200' : 'bg-gray-100 text-gray-800'}`}>
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
                    className={isDark ? 'border-slate-600 text-slate-300' : 'border-gray-300 text-gray-700'}
                  >
                    {t('copy') || 'Copy'}
                  </Button>
                  <Button onClick={() => setCreatedCreds(null)} className="bg-blue-600 hover:bg-blue-700 text-white">
                    {t('done') || 'Done'}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>

          {/* AG-03: per-client feature toggles */}
          <Dialog open={!!featureClient} onOpenChange={(open) => !open && setFeatureClient(null)}>
            <DialogContent className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
              <DialogHeader>
                <DialogTitle className={isDark ? 'text-white' : 'text-slate-900'}>
                  {t('features') || 'Features'} — {featureClient?.business_name}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>
                  {t('feature_toggle_hint') || 'Enable or disable capabilities for this client. Features are on by default.'}
                </p>
                {TOGGLEABLE_FEATURES.map((f) => (
                  <div key={f} className="flex items-center justify-between gap-2">
                    <span className={isDark ? 'text-slate-200' : 'text-slate-800'}>{t(f) || f}</span>
                    <div className="flex gap-2">
                      <Button size="sm" disabled={featureBusy} onClick={() => handleSetFeature(f, true)} className="bg-green-600 hover:bg-green-700 text-white text-xs">
                        {t('enable') || 'Enable'}
                      </Button>
                      <Button size="sm" disabled={featureBusy} variant="outline" onClick={() => handleSetFeature(f, false)} className={isDark ? 'border-red-600 text-red-400 hover:bg-red-600/10 text-xs' : 'border-red-300 text-red-700 hover:bg-red-50 text-xs'}>
                        {t('disable') || 'Disable'}
                      </Button>
                    </div>
                  </div>
                ))}
                <div className="flex justify-end pt-2">
                  <Button onClick={() => setFeatureClient(null)} className="bg-blue-600 hover:bg-blue-700 text-white">
                    {t('done') || 'Done'}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        <div className={`overflow-x-auto rounded-lg border ${isDark ? 'border-slate-700' : 'border-gray-200'}`}>
          <table className="w-full text-sm">
            <thead className={isDark ? 'bg-slate-800' : 'bg-gray-50'}>
              <tr className={isDark ? 'text-slate-400' : 'text-gray-500'}>
                <th className="p-3 text-start">{t('business_name')}</th>
                <th className="p-3 text-start">{t('email')}</th>
                <th className="p-3 text-start">{t('phone')}</th>
                <th className="p-3 text-start">{t('subscription_fee')}</th>
                <th className="p-3 text-start">{t('status')}</th>
                <th className="p-3 text-start">{t('actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.id} className={`border-t ${isDark ? 'border-slate-700 text-slate-300' : 'border-gray-200 text-gray-700'}`}>
                  <td className="p-3">{c.business_name}</td>
                  <td className="p-3">{c.email}</td>
                  <td className="p-3">{c.phone}</td>
                  <td className="p-3">{formatMoney(c.subscription_fee || 0, language)}</td>
                  <td className="p-3">
                    <Badge className={c.is_active ? 'bg-green-600 text-white' : 'bg-red-600 text-white'}>
                      {c.is_active ? t('active') : t('inactive')}
                    </Badge>
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant={c.is_active ? 'destructive' : 'default'}
                        onClick={() => handleToggleClient(c.id)}
                        disabled={togglingId === c.id}
                        className={
                          c.is_active
                            ? 'bg-red-600 hover:bg-red-700 text-white text-xs'
                            : 'bg-green-600 hover:bg-green-700 text-white text-xs'
                        }
                      >
                        {togglingId === c.id
                          ? '...'
                          : c.is_active
                            ? (t('deactivate') || 'Deactivate')
                            : (t('activate') || 'Activate')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setFeatureClient(c)}
                        className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700 text-xs' : 'border-gray-300 text-gray-700 hover:bg-gray-100 text-xs'}
                      >
                        {t('features') || 'Features'}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleResetPassword(c.id)}
                        disabled={resettingId === c.id}
                        title={t('reset_password') || 'Reset password'}
                        className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700 text-xs' : 'border-gray-300 text-gray-700 hover:bg-gray-100 text-xs'}
                      >
                        {resettingId === c.id ? '...' : (t('reset_password') || 'Reset Password')}
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