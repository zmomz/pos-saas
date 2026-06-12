import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { client, getMasterAgents, toggleAgent, getPackages, createAgent, addAgentSlots, getTaxRate, setGlobalTaxRate, getMasterEconomics, type MasterEconomics } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import ErrorState from '@/components/states/ErrorState';
import StatCard from '@/components/dashboard/StatCard';
import { PageHeader, SectionHeading } from '@/components/dashboard/PageHeader';
import { Users, DollarSign, Package as PackageIcon, Activity, UserPlus, BarChart3, Settings, Shield, TrendingUp, TrendingDown, Store } from 'lucide-react';

interface Agent {
  id: number;
  company_name: string;
  email: string;
  // The backend returns package_type as the agent's TOTAL client-slot count
  // (add_agent_slots increments it). MA-03: display used/total from this field.
  package_type: number;
  used_slots: number;
  is_active: boolean;
}

interface Package {
  id: number;
  name: string;
  client_slots: number;
  wholesale_price: number;
  retail_price_per_client: number;
  features: string;
}

export default function MasterDashboard() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [packages, setPackages] = useState<Package[]>([]);
  const [loading, setLoading] = useState(true);
  // MA-08 platform economics — loaded independently of the agent list so an
  // economics failure renders its own error state instead of blanking the page.
  const [economics, setEconomics] = useState<MasterEconomics | null>(null);
  const [ecoLoading, setEcoLoading] = useState(true);
  const [ecoError, setEcoError] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newAgentForm, setNewAgentForm] = useState({
    company_name: '',
    email: '',
    phone: '',
    package_id: '',
  });
  const [creating, setCreating] = useState(false);
  // MA-04: add-slots dialog. MA-05: master global tax-rate dialog.
  const [slotDialog, setSlotDialog] = useState<{ agentId: number; company: string } | null>(null);
  const [slotAmount, setSlotAmount] = useState('1');
  const [taxDialogOpen, setTaxDialogOpen] = useState(false);
  const [taxInput, setTaxInput] = useState('15');
  const [savingTax, setSavingTax] = useState(false);
  // One-time agent login credentials surfaced after creation (MA-01) so the
  // returned temp password isn't lost.
  const [createdCreds, setCreatedCreds] = useState<
    { email: string; temp_password: string } | null
  >(null);
  const navigate = useNavigate();
  const { t, language } = useLanguage();

  useEffect(() => {
    loadData();
    loadEconomics();
  }, []);

  async function loadData() {
    try {
      const [agentData, pkgData] = await Promise.all([getMasterAgents(), getPackages()]);
      // API returns { items, total }; tolerate array/agents shapes too.
      setAgents(Array.isArray(agentData) ? agentData : (agentData?.items || agentData?.agents || []));
      setPackages(Array.isArray(pkgData) ? pkgData : (pkgData?.items || []));
    } catch (err) {
      console.error('Failed to load data:', err);
    } finally {
      setLoading(false);
    }
  }

  async function loadEconomics() {
    setEcoLoading(true);
    setEcoError(false);
    try {
      setEconomics(await getMasterEconomics());
    } catch (err) {
      console.error('Failed to load economics:', err);
      setEcoError(true);
    } finally {
      setEcoLoading(false);
    }
  }

  async function handleToggle(agentId: number) {
    try {
      await toggleAgent(agentId);
      setAgents((prev) =>
        prev.map((a) => (a.id === agentId ? { ...a, is_active: !a.is_active } : a))
      );
    } catch (err) {
      console.error('Toggle failed:', err);
    }
  }

  async function handleCreateAgent() {
    if (!newAgentForm.company_name || !newAgentForm.email) return;
    setCreating(true);
    try {
      const selectedPkg = packages.find((p) => p.id === Number(newAgentForm.package_id));
      const created = await createAgent({
        company_name: newAgentForm.company_name,
        email: newAgentForm.email,
        phone: newAgentForm.phone || undefined,
        package_id: newAgentForm.package_id ? Number(newAgentForm.package_id) : undefined,
        package_type: selectedPkg?.name || undefined,
      });
      setCreateDialogOpen(false);
      setNewAgentForm({ company_name: '', email: '', phone: '', package_id: '' });
      if (created?.temp_password) {
        setCreatedCreds({ email: created.email, temp_password: created.temp_password });
      }
      await loadData();
    } catch (err) {
      console.error('Create agent failed:', err);
    } finally {
      setCreating(false);
    }
  }

  async function handleAddSlots() {
    if (!slotDialog) return;
    const n = Number(slotAmount);
    if (!Number.isFinite(n) || n <= 0) return;
    try {
      await addAgentSlots(slotDialog.agentId, n);
      setSlotDialog(null);
      setSlotAmount('1');
      await loadData();
    } catch (err) {
      console.error('Add slots failed:', err);
    }
  }

  async function openTaxDialog() {
    try {
      const data = await getTaxRate();
      setTaxInput(String(data?.tax_rate ?? 15));
    } catch {
      setTaxInput('15');
    }
    setTaxDialogOpen(true);
  }

  async function handleSaveTax() {
    const rate = Number(taxInput);
    if (!Number.isFinite(rate) || rate < 0 || rate > 100) return;
    setSavingTax(true);
    try {
      await setGlobalTaxRate(rate);
      setTaxDialogOpen(false);
    } catch (err) {
      console.error('Save tax rate failed:', err);
    } finally {
      setSavingTax(false);
    }
  }

  async function handleLogout() {
    await client.auth.logout();
    navigate('/');
  }

  const totalAgents = agents.length;
  const activeAgents = agents.filter((a) => a.is_active).length;

  // Compact economics figures rendered as a uniform mini-stat row.
  const ecoCards = economics
    ? [
        { icon: TrendingUp, tone: 'emerald', label: t('mrr'), value: formatMoney(economics.mrr, language) },
        { icon: DollarSign, tone: 'brand', label: t('arr'), value: formatMoney(economics.arr, language) },
        { icon: Store, tone: 'sky', label: t('active_merchants'), value: `${economics.active_clients}/${economics.total_clients}` },
        { icon: TrendingDown, tone: 'rose', label: t('churn_rate'), value: `${(economics.churn_rate * 100).toFixed(1)}%` },
        { icon: DollarSign, tone: 'violet', label: t('platform_revenue'), value: formatMoney(economics.platform_revenue, language) },
        { icon: DollarSign, tone: 'emerald', label: t('collected'), value: formatMoney(economics.collected, language) },
      ]
    : [];

  const toneIcon: Record<string, string> = {
    emerald: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300',
    brand: 'bg-brand-500/15 text-brand-600 dark:text-brand-300',
    sky: 'bg-sky-500/15 text-sky-600 dark:text-sky-300',
    rose: 'bg-rose-500/15 text-rose-600 dark:text-rose-300',
    violet: 'bg-violet-500/15 text-violet-600 dark:text-violet-300',
  };

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
        title={t('dashboard')}
        subtitle={t('platform_economics')}
        actions={
          <Button onClick={() => setCreateDialogOpen(true)} className="shadow-brand">
            <UserPlus className="h-4 w-4" />
            {t('create_agent') || 'Add Agent'}
          </Button>
        }
      />

      {/* Stats */}
      <div data-tour="stats-section" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Users} tone="brand" label={t('total_agents') || 'Total Agents'} value={totalAgents} />
        <StatCard icon={DollarSign} tone="emerald" label={t('mrr')} value={formatMoney(economics?.mrr ?? 0, language)} />
        <StatCard icon={PackageIcon} tone="violet" label={t('active_packages') || 'Active Packages'} value={packages.length} />
        <StatCard icon={Activity} tone="sky" label={t('system_health') || 'System Health'} value={`${activeAgents}/${totalAgents} ${t('active') || 'Active'}`} />
      </div>

      {/* Quick Actions */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-3">
        <Button variant="outline" onClick={() => navigate('/packages')}>
          <Settings className="h-4 w-4" />
          {t('package_management') || 'Manage Packages'}
        </Button>
        <Button variant="outline" onClick={() => navigate('/audit')}>
          <Shield className="h-4 w-4" />
          {t('audit_log') || 'Audit Log'}
        </Button>
        <Button variant="outline" onClick={() => navigate('/notifications')}>
          <BarChart3 className="h-4 w-4" />
          {t('notifications') || 'Notifications'}
        </Button>
        <Button variant="outline" onClick={openTaxDialog}>
          <DollarSign className="h-4 w-4" />
          {t('tax_rate') || 'Tax Rate'}
        </Button>
      </div>

      {/* MA-08 / RSL-08: platform economics — MRR, ARR, active merchants, churn,
          platform revenue, and the revenue-by-agent leaderboard. */}
      <section>
        <SectionHeading title={t('platform_economics')} />
        {ecoLoading ? (
          <div className="animate-pulse py-8 text-center text-muted-foreground">{t('loading')}</div>
        ) : ecoError ? (
          <ErrorState onRetry={loadEconomics} />
        ) : economics && economics.total_clients === 0 && economics.collected === 0 ? (
          <Card className="rounded-2xl shadow-card">
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              {t('economics_empty')}
            </CardContent>
          </Card>
        ) : economics ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-4">
              {ecoCards.map((card, i) => {
                const Icon = card.icon;
                return (
                  <Card key={i} className="rounded-2xl shadow-card">
                    <CardContent className="p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${toneIcon[card.tone]}`}>
                          <Icon className="h-4 w-4" />
                        </span>
                        <p className="text-xs text-muted-foreground">{card.label}</p>
                      </div>
                      <p className="text-lg font-bold text-foreground">{card.value}</p>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            {/* RSL-08: revenue-by-agent leaderboard */}
            <div className="overflow-x-auto rounded-2xl border border-border bg-card shadow-card">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="p-3 text-start font-medium">{t('company_name')}</th>
                    <th className="p-3 text-start font-medium">{t('active_merchants')}</th>
                    <th className="p-3 text-start font-medium">{t('mrr')}</th>
                    <th className="p-3 text-start font-medium">{t('collected')}</th>
                    <th className="p-3 text-start font-medium">{t('platform_revenue')}</th>
                    <th className="p-3 text-start font-medium">{t('revenue_net_margin')}</th>
                  </tr>
                </thead>
                <tbody>
                  {economics.by_agent.map((a) => (
                    <tr key={a.agent_id} className="border-t border-border text-foreground/80 transition-colors hover:bg-muted/40">
                      <td className="p-3 font-medium text-foreground">{a.company_name}</td>
                      <td className="p-3">{a.active_clients}/{a.total_clients}</td>
                      <td className="p-3">{formatMoney(a.mrr, language)}</td>
                      <td className="p-3">{formatMoney(a.collected, language)}</td>
                      <td className="p-3">{formatMoney(a.master_owed, language)}</td>
                      <td className="p-3">{formatMoney(a.net, language)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </section>

      {/* Package Overview */}
      <section>
        <SectionHeading title={t('packages')} />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {packages.map((pkg) => (
            <Card key={pkg.id} className="rounded-2xl shadow-card transition-all hover:-translate-y-0.5 hover:shadow-brand">
              <CardHeader>
                <CardTitle className="text-base text-foreground">{pkg.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>{t('client_slots')}: <span className="font-medium text-foreground">{pkg.client_slots}</span></p>
                <p>{t('wholesale_price')}: <span className="font-medium text-foreground">{formatMoney(pkg.wholesale_price || 0, language)}</span></p>
                <p>{t('retail_price')}: <span className="font-medium text-foreground">{formatMoney(pkg.retail_price_per_client || 0, language)}</span></p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Agents Table */}
      <section>
        <SectionHeading
          title={`${t('agents')} (${agents.length})`}
          actions={
            <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
              <DialogTrigger asChild>
                <Button className="shadow-brand">
                  <UserPlus className="h-4 w-4" />
                  {t('create_agent') || 'Create Agent'}
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{t('create_agent') || 'Create Agent'}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <label className="text-sm mb-1 block text-muted-foreground">{t('company_name')}</label>
                    <Input
                      placeholder={t('company_name')}
                      value={newAgentForm.company_name}
                      onChange={(e) => setNewAgentForm({ ...newAgentForm, company_name: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="text-sm mb-1 block text-muted-foreground">{t('email')}</label>
                    <Input
                      placeholder={t('email')}
                      type="email"
                      value={newAgentForm.email}
                      onChange={(e) => setNewAgentForm({ ...newAgentForm, email: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="text-sm mb-1 block text-muted-foreground">{t('phone')}</label>
                    <Input
                      placeholder={t('phone')}
                      value={newAgentForm.phone}
                      onChange={(e) => setNewAgentForm({ ...newAgentForm, phone: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="text-sm mb-1 block text-muted-foreground">{t('package')}</label>
                    <Select
                      value={newAgentForm.package_id}
                      onValueChange={(v) => setNewAgentForm({ ...newAgentForm, package_id: v })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder={t('select_package') || 'Select Package'} />
                      </SelectTrigger>
                      <SelectContent>
                        {packages.map((pkg) => (
                          <SelectItem key={pkg.id} value={String(pkg.id)}>
                            {pkg.name} ({pkg.client_slots} {t('slots')})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex gap-2 justify-end pt-2">
                    <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                      {t('cancel')}
                    </Button>
                    <Button
                      onClick={handleCreateAgent}
                      disabled={creating || !newAgentForm.company_name || !newAgentForm.email}
                    >
                      {creating ? t('loading') : (t('create_agent') || 'Create Agent')}
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          }
        />

        {/* One-time credentials for a newly created agent (MA-01) */}
        <Dialog open={!!createdCreds} onOpenChange={(open) => !open && setCreatedCreds(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('agent_created') || 'Agent created'}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {t('credentials_show_once') ||
                  'Share these login credentials with the agent now — they will not be shown again. They must change the password on first login.'}
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

        {/* MA-04: add client slots to an agent's package */}
        <Dialog open={!!slotDialog} onOpenChange={(open) => !open && setSlotDialog(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('add_slots') || 'Add Slots'} — {slotDialog?.company}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <label className="text-sm mb-1 block text-muted-foreground">{t('slots') || 'Slots'}</label>
                <Input
                  type="number"
                  min={1}
                  value={slotAmount}
                  onChange={(e) => setSlotAmount(e.target.value)}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => setSlotDialog(null)}>{t('cancel')}</Button>
                <Button onClick={handleAddSlots}>{t('add_slots') || 'Add Slots'}</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* MA-05: master global VAT/tax-rate setting */}
        <Dialog open={taxDialogOpen} onOpenChange={setTaxDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('tax_rate') || 'Global Tax Rate'}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <label className="text-sm mb-1 block text-muted-foreground">{t('tax_rate') || 'Tax Rate'} (%)</label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step="0.1"
                  value={taxInput}
                  onChange={(e) => setTaxInput(e.target.value)}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => setTaxDialogOpen(false)}>{t('cancel')}</Button>
                <Button onClick={handleSaveTax} disabled={savingTax}>
                  {savingTax ? t('loading') : (t('save') || 'Save')}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        <div className="overflow-x-auto rounded-2xl border border-border bg-card shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="p-3 text-start font-medium">{t('company_name')}</th>
                <th className="p-3 text-start font-medium">{t('email')}</th>
                <th className="p-3 text-start font-medium">{t('package')}</th>
                <th className="p-3 text-start font-medium">{t('slots')}</th>
                <th className="p-3 text-start font-medium">{t('status')}</th>
                <th className="p-3 text-start font-medium">{t('toggle')}</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id} className="border-t border-border text-foreground/80 transition-colors hover:bg-muted/40">
                  <td className="p-3 font-medium text-foreground">{agent.company_name}</td>
                  <td className="p-3">{agent.email}</td>
                  <td className="p-3">{agent.package_type}</td>
                  <td className="p-3">{agent.used_slots ?? 0}/{agent.package_type ?? 0}</td>
                  <td className="p-3">
                    <Badge className={agent.is_active ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'}>
                      {agent.is_active ? t('active') : t('inactive')}
                    </Badge>
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => handleToggle(agent.id)}>
                        {t('toggle')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => { setSlotDialog({ agentId: agent.id, company: agent.company_name }); setSlotAmount('1'); }}
                        className="border-brand-300 text-brand-600 hover:bg-brand-50 dark:border-brand-500/40 dark:text-brand-300 dark:hover:bg-brand-500/10"
                      >
                        + {t('slots') || 'Slots'}
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
