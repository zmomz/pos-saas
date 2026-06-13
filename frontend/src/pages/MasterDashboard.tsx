import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { client, getMasterAgents, toggleAgent, getPackages, createAgent, addAgentSlots, getTaxRate, setGlobalTaxRate, getMasterEconomics, getAuditLogs, type MasterEconomics } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import ErrorState from '@/components/states/ErrorState';
import StatTile, { StatBar } from '@/components/dashboard/StatTile';
import { PageHeader, SectionHeading } from '@/components/dashboard/PageHeader';
import { Avatar } from '@/components/dashboard/Avatar';
import { ActivityFeed } from '@/components/dashboard/ActivityFeed';
import { MrrTrendChart } from '@/components/dashboard/MrrTrendChart';
import { Users, DollarSign, Package as PackageIcon, Activity, UserPlus, BarChart3, Shield, TrendingUp, ArrowRight, Percent } from 'lucide-react';

// Audit row shape (mirrors AuditLog.tsx) for the activity feed + audit preview.
interface AuditEntry {
  id: string;
  user_email?: string;
  action: string;
  details?: string;
  created_at?: string;
}

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
  // Recent-activity + audit-preview cards (handoff). Best-effort; absent data
  // just renders the empty state.
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
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
    getAuditLogs()
      .then((d) => setAuditEntries(Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : []))
      .catch(() => setAuditEntries([]));
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
  // Slot-fill across the platform (handoff "Active Packages" bar): used vs total
  // client slots summed over every agent.
  const totalSlots = agents.reduce((s, a) => s + (a.package_type || 0), 0);
  const usedSlots = agents.reduce((s, a) => s + (a.used_slots || 0), 0);
  const slotPct = totalSlots > 0 ? Math.round((usedSlots / totalSlots) * 100) : 0;

  // Compact economics figures for the mini-grid inside the Platform Economics card.
  const ecoCells = economics
    ? [
        { k: t('mrr'), v: formatMoney(economics.mrr, language) },
        { k: t('arr'), v: formatMoney(economics.arr, language) },
        { k: t('active_merchants'), v: `${economics.active_clients}`, small: ` / ${economics.total_clients}` },
        { k: t('churn_rate'), v: `${(economics.churn_rate * 100).toFixed(1)}%` },
        { k: t('platform_revenue'), v: formatMoney(economics.platform_revenue, language) },
        { k: t('collected'), v: formatMoney(economics.collected, language) },
      ]
    : [];

  // Revenue-by-agent leaderboard, ranked by MRR, with each agent's share of the
  // total MRR driving the progress bar.
  const leaderboard = economics ? [...economics.by_agent].sort((a, b) => b.mrr - a.mrr) : [];
  const topMrr = leaderboard.reduce((m, a) => Math.max(m, a.mrr), 0);

  // Recent activity + audit preview from the audit log.
  const activityItems = auditEntries.slice(0, 5).map((e) => ({
    id: e.id,
    action: e.action,
    at: e.created_at,
    text: (
      <>
        {e.user_email ? <b className="font-semibold">{e.user_email}</b> : null}
        {e.user_email ? ' ' : ''}
        {e.details || e.action}
      </>
    ),
  }));

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

      {/* Stats — handoff stat tiles (swatch + big value + footer). */}
      <div data-tour="stats-section" className="grid grid-cols-1 gap-[18px] sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          icon={Users}
          tone="brand"
          label={t('total_agents') || 'Total Agents'}
          value={totalAgents}
          footer={
            <span className="inline-flex items-center gap-1.5 text-success">
              <span className="h-[7px] w-[7px] rounded-full bg-success" /> {activeAgents} {t('active') || 'active'}
            </span>
          }
        />
        <StatTile
          icon={DollarSign}
          tone="success"
          label={t('mrr')}
          value={formatMoney(economics?.mrr ?? 0, language)}
          footer={<span className="text-muted-foreground">{t('arr')} {formatMoney(economics?.arr ?? 0, language)}</span>}
        />
        <StatTile
          icon={PackageIcon}
          tone="violet"
          label={t('active_packages') || 'Active Packages'}
          value={packages.length}
          valueSmall={totalSlots > 0 ? `· ${usedSlots}/${totalSlots} ${t('slots') || 'slots'}` : undefined}
          footer={totalSlots > 0 ? <StatBar pct={slotPct} /> : <span className="text-muted-foreground">{t('packages')}</span>}
        />
        <StatTile
          icon={Activity}
          tone="sky"
          label={t('system_health') || 'System Health'}
          value={`${activeAgents}/${totalAgents}`}
          valueSmall={t('active') || 'active'}
          footer={
            <span className="inline-flex items-center gap-1.5 text-success">
              <span className="h-[7px] w-[7px] rounded-full bg-success" /> {t('all_systems_operational') || 'All systems operational'}
            </span>
          }
        />
      </div>

      {/* Quick Actions — handoff chips. */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-2.5">
        <button onClick={() => navigate('/packages')} className="chip-link">
          <PackageIcon className="h-4 w-4" /> {t('packages') || 'Packages'}
        </button>
        <button onClick={() => navigate('/audit')} className="chip-link">
          <Shield className="h-4 w-4" /> {t('audit_log') || 'Audit Log'}
        </button>
        <button onClick={() => navigate('/notifications')} className="chip-link">
          <BarChart3 className="h-4 w-4" /> {t('notifications') || 'Notifications'}
        </button>
        <button onClick={openTaxDialog} className="chip-link">
          <Percent className="h-4 w-4" /> {t('tax_rate') || 'Tax settings'}
        </button>
      </div>

      {/* MA-08 / RSL-08: Platform Economics — mini-grid + revenue-by-agent leaderboard. */}
      <Card className="rounded-2xl border-border shadow-card">
        <CardContent className="p-6">
          <div className="mb-3.5 flex items-center justify-between">
            <h2 className="text-base font-bold tracking-tight text-foreground">{t('platform_economics')}</h2>
            <span className="pill-success">
              <span className="h-[7px] w-[7px] rounded-full bg-current" /> {t('healthy') || 'Healthy'}
            </span>
          </div>

          {ecoLoading ? (
            <div className="animate-pulse py-8 text-center text-muted-foreground">{t('loading')}</div>
          ) : ecoError ? (
            <ErrorState onRetry={loadEconomics} />
          ) : economics && economics.total_clients === 0 && economics.collected === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">{t('economics_empty')}</p>
          ) : economics ? (
            <>
              {/* Mini-grid: hairline-separated cells (handoff `.mini-grid`). */}
              <div className="mb-[22px] grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-border md:grid-cols-3">
                {ecoCells.map((c, i) => (
                  <div key={i} className="bg-card p-4">
                    <div className="text-xs font-medium text-muted-foreground">{c.k}</div>
                    <div className="mt-1.5 text-[20px] font-extrabold tracking-tight tabular-nums text-foreground">
                      {c.v}
                      {c.small ? <small className="text-[13px] font-semibold text-muted-foreground">{c.small}</small> : null}
                    </div>
                  </div>
                ))}
              </div>

              <div className="mb-3.5 flex items-center justify-between">
                <h3 className="text-sm font-bold tracking-tight text-foreground">{t('revenue_by_agent') || 'Revenue by Agent'}</h3>
              </div>

              {/* Revenue-by-agent leaderboard. */}
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border text-[11.5px] font-bold uppercase tracking-wider text-muted-foreground/80">
                      <th className="w-9 py-2.5 pe-2 text-start" />
                      <th className="py-2.5 pe-3 text-start font-bold">{t('company_name') || 'Agent'}</th>
                      <th className="py-2.5 pe-3 text-start font-bold">{t('active_merchants') || 'Merchants'}</th>
                      <th className="py-2.5 pe-3 text-start font-bold">{t('mrr')}</th>
                      <th className="py-2.5 pe-3 text-start font-bold">{t('share') || 'Share'}</th>
                      <th className="py-2.5 text-start font-bold">{t('status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboard.map((a, i) => (
                      <tr key={a.agent_id} className="border-b border-border last:border-b-0 hover:bg-muted/40">
                        <td className={`py-3.5 pe-2 font-mono text-xs ${i < 5 ? 'font-bold text-gold-600' : 'text-muted-foreground'}`}>
                          {String(i + 1).padStart(2, '0')}
                        </td>
                        <td className="py-3.5 pe-3">
                          <div className="flex items-center gap-2.5">
                            <Avatar name={a.company_name} size={32} />
                            <span className="font-semibold text-foreground">{a.company_name}</span>
                          </div>
                        </td>
                        <td className="py-3.5 pe-3 tabular-nums text-foreground/80">{a.active_clients}/{a.total_clients}</td>
                        <td className="py-3.5 pe-3 font-bold tabular-nums text-foreground">{formatMoney(a.mrr, language)}</td>
                        <td className="py-3.5 pe-3">
                          <div className="h-[7px] w-[90px] overflow-hidden rounded bg-brand-100">
                            <span className="block h-full rounded bg-brand" style={{ width: `${topMrr > 0 ? Math.round((a.mrr / topMrr) * 100) : 0}%` }} />
                          </div>
                        </td>
                        <td className="py-3.5">
                          <span className={a.is_active ? 'pill-success' : 'pill-danger'}>
                            <span className="h-[7px] w-[7px] rounded-full bg-current" /> {a.is_active ? t('active') : t('inactive')}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>

      {/* Split: MRR trend chart + Recent Activity (handoff `.layout-split`). */}
      <div className="grid gap-[18px] lg:grid-cols-[1.55fr_1fr]">
        <Card className="rounded-2xl border-border shadow-card">
          <CardContent className="p-6">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-base font-bold tracking-tight text-foreground">{t('platform_mrr_trend') || 'Platform MRR · last 12 months'}</h2>
              <span className="pill-success">
                <TrendingUp className="h-[13px] w-[13px]" /> {t('trend') || 'Trend'}
              </span>
            </div>
            <MrrTrendChart current={economics?.mrr ?? 0} format={(n) => formatMoney(n, language)} />
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-border shadow-card">
          <CardContent className="p-6">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-base font-bold tracking-tight text-foreground">{t('recent_activity') || 'Recent Activity'}</h2>
              <button onClick={() => navigate('/audit')} className="inline-flex items-center gap-1 text-[13px] font-semibold text-brand-700">
                {t('view_all') || 'View all'} <ArrowRight className="h-[15px] w-[15px]" />
              </button>
            </div>
            <ActivityFeed items={activityItems} empty={t('no_recent_activity') || 'No recent activity.'} />
          </CardContent>
        </Card>
      </div>

      {/* Audit Log preview (handoff bottom card). */}
      <Card className="rounded-2xl border-border shadow-card">
        <CardContent className="p-6">
          <div className="mb-3.5 flex items-center justify-between">
            <h2 className="text-base font-bold tracking-tight text-foreground">{t('audit_log') || 'Audit Log'}</h2>
            <button onClick={() => navigate('/audit')} className="inline-flex items-center gap-1 text-[13px] font-semibold text-brand-700">
              {t('view_all') || 'View all entries'} <ArrowRight className="h-[15px] w-[15px]" />
            </button>
          </div>
          {auditEntries.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{t('no_audit_entries') || 'No audit entries yet.'}</p>
          ) : (
            auditEntries.slice(0, 5).map((e) => (
              <div key={e.id} className="flex items-center gap-3 border-b border-dashed border-border py-3 text-[13px] last:border-b-0">
                <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 font-mono text-[10.5px] text-muted-foreground">
                  {e.created_at ? new Date(e.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                </span>
                {e.user_email ? <b className="font-semibold text-foreground">{e.user_email}</b> : null}
                <span className="text-foreground/80">{e.details || e.action}</span>
              </div>
            ))
          )}
        </CardContent>
      </Card>

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
