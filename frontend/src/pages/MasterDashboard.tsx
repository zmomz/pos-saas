import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getMasterAgents, toggleAgent, getPackages, createAgent, addAgentSlots, getTaxRate, setGlobalTaxRate, getMasterEconomics, getAuditLogs, type MasterEconomics } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';
import ErrorState from '@/components/states/ErrorState';
import CountUp from '@/components/dashboard/rx/CountUp';
import Gauge from '@/components/dashboard/rx/Gauge';
import Bar from '@/components/dashboard/rx/Bar';
import { usePageChrome } from '@/contexts/PageChromeContext';
import {
  Users, DollarSign, Package as PackageIcon, Activity, UserPlus, BarChart3, Shield,
  TrendingUp, TrendingDown, ArrowRight, ChevronRight, Percent, AlertTriangle, Check,
} from 'lucide-react';

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
  package_type: number;
  used_slots: number;
  is_active: boolean;
}

interface Package {
  id: number;
  name: string;
  client_slots: number;
  wholesale_price: number;
  suggested_retail_price: number;
  features: string;
}

// Avatar gradient palette for leaderboard rows — token-based (no raw hex).
const AV_GRADS = [
  'bg-gradient-to-br from-brand-500 to-brand-700',
  'bg-gradient-to-br from-violet to-violet-700',
  'bg-gradient-to-br from-sky to-sky-700',
  'bg-gradient-to-br from-gold to-gold-600',
  'bg-gradient-to-br from-danger to-danger-700',
  'bg-gradient-to-br from-brand-300 to-brand-500',
];

function initials(name: string) {
  return name.split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';
}

export default function MasterDashboard() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [packages, setPackages] = useState<Package[]>([]);
  const [loading, setLoading] = useState(true);
  const [economics, setEconomics] = useState<MasterEconomics | null>(null);
  const [ecoLoading, setEcoLoading] = useState(true);
  const [ecoError, setEcoError] = useState(false);
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newAgentForm, setNewAgentForm] = useState({ company_name: '', email: '', phone: '', package_id: '' });
  const [creating, setCreating] = useState(false);
  const [slotDialog, setSlotDialog] = useState<{ agentId: number; company: string } | null>(null);
  const [slotAmount, setSlotAmount] = useState('1');
  const [taxDialogOpen, setTaxDialogOpen] = useState(false);
  const [taxInput, setTaxInput] = useState('15');
  const [savingTax, setSavingTax] = useState(false);
  const [createdCreds, setCreatedCreds] = useState<{ email: string; temp_password: string } | null>(null);
  const navigate = useNavigate();
  const { t, tt, language } = useLanguage();

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
      setAgents(Array.isArray(agentData) ? agentData : (agentData?.items || agentData?.agents || []));
      setPackages((Array.isArray(pkgData?.items) ? pkgData.items : []) as unknown as Package[]);
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
      setAgents((prev) => prev.map((a) => (a.id === agentId ? { ...a, is_active: !a.is_active } : a)));
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
      if (created?.temp_password) setCreatedCreds({ email: created.email, temp_password: created.temp_password });
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

  // ---- derived ----
  const totalAgents = agents.length;
  const activeAgents = agents.filter((a) => a.is_active).length;
  const totalSlots = agents.reduce((s, a) => s + (a.package_type || 0), 0);
  const usedSlots = agents.reduce((s, a) => s + (a.used_slots || 0), 0);
  const slotPct = totalSlots > 0 ? Math.round((usedSlots / totalSlots) * 100) : 0;
  const healthPct = totalAgents > 0 ? Math.round((activeAgents / totalAgents) * 100) : 0;

  const leaderboard = economics ? [...economics.by_agent].sort((a, b) => b.mrr - a.mrr) : [];
  const topMrr = leaderboard.reduce((m, a) => Math.max(m, a.mrr), 0);

  // Inactive / near-cap signals for the "needs attention" rail.
  const suspended = agents.filter((a) => !a.is_active);
  const nearCap = agents.filter((a) => a.package_type > 0 && a.used_slots / a.package_type >= 0.9);

  // Live MRR scalar from the backend. There is no historical series yet, so the
  // hero shows an explicit "no history" state rather than a synthesized trend.
  const mrr = economics?.mrr ?? 0;

  const paletteGroups = [
    {
      label: tt('cmd_quick_actions', 'Quick actions'),
      items: [
        { icon: UserPlus, label: tt('create_agent', 'Create agent'), kbd: 'C', onSelect: () => setCreateDialogOpen(true) },
        { icon: Percent, label: tt('tax_rate', 'Edit global tax rate'), onSelect: openTaxDialog },
        { icon: PackageIcon, label: tt('packages', 'Manage packages'), onSelect: () => navigate('/packages') },
        { icon: Shield, label: tt('audit_log', 'Audit log'), onSelect: () => navigate('/audit') },
      ],
    },
  ];

  usePageChrome(
    {
      subtitle: `${t('platform_economics')} · ${tt('all_agents_revenue', 'all agents and revenue')}`,
      primaryAction: (
        <Button onClick={() => setCreateDialogOpen(true)} className="h-11 rounded-[10px] shadow-brand">
          <UserPlus className="h-4 w-4" />
          {tt('create_agent', 'Create Agent')}
        </Button>
      ),
      paletteGroups,
    },
    [language]
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
      {/* BENTO */}
      <div data-tour="stats-section" className="grid gap-4 lg:auto-rows-[116px] lg:grid-cols-12">

        {/* HERO — MRR spotlight */}
        <section className="dxr-tile dxr-ink flex flex-col lg:col-span-8 lg:row-span-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="dxr-eyebrow">{tt('platform_mrr', 'Platform MRR')}</div>
              {/* H4 — economics is a distinct fetch from the agent list; if it
                  fails the headline must say so, never render a fabricated ⃁ 0. */}
              {ecoError ? (
                <>
                  <div className="mt-2 text-[clamp(32px,4vw,46px)] font-extrabold leading-none tracking-tight">—</div>
                  <div className="mt-3 flex items-center gap-2.5 text-[13px] text-white/70">
                    <span>{tt('economics_unavailable', 'Revenue data unavailable.')}</span>
                    <button onClick={loadEconomics} className="font-bold text-cyan underline-offset-2 hover:underline">{t('retry')}</button>
                  </div>
                </>
              ) : (
                <>
                  <div className="mt-2 text-[clamp(32px,4vw,46px)] font-extrabold leading-none tracking-tight tabular-nums">
                    <CountUp value={mrr} prefix="⃁ " />
                  </div>
                  <div className="mt-3 flex items-center gap-2.5 text-[13px] text-white/70">
                    <span>{t('arr')} <b className="text-white">{formatMoney(economics?.arr ?? 0, language)}</b></span>
                  </div>
                </>
              )}
            </div>
          </div>
          <div className="mt-auto flex h-[150px] items-end">
            <p className="text-[12.5px] text-white/55">{tt('mrr_trend_history_unavailable', 'Trend history not available yet.')}</p>
          </div>
        </section>

        {/* Slots filled gauge */}
        <section className="dxr-tile dxr-hover lg:col-span-4 lg:row-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-[14px] font-extrabold">{tt('slots_filled', 'Slots Filled')}</h2>
            <span className="pill-success"><span className="h-1.5 w-1.5 rounded-full bg-current" />{tt('healthy', 'Healthy')}</span>
          </div>
          <Gauge
            pct={slotPct}
            center={<CountUp value={slotPct} suffix="%" />}
            caption={`${usedSlots} / ${totalSlots} ${tt('slots', 'slots')}`}
          />
        </section>

        {/* Active merchants mini */}
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-4 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{tt('active_merchants', 'Active Merchants')}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums">{ecoError ? '—' : <CountUp value={economics?.active_clients ?? 0} />}</div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{ecoError ? `${totalAgents} ${tt('agents', 'agents')}` : `${economics?.total_clients ?? 0} ${tt('total', 'total')} · ${totalAgents} ${tt('agents', 'agents')}`}</div>
        </section>

        {/* KPI chips — economics-derived chips show "—" on a failed economics fetch (H4), never a fabricated 0. */}
        <KpiChip label={tt('total_agents', 'Total Agents')} value={<CountUp value={totalAgents} />} delta={{ dir: 'up', text: `${activeAgents} ${tt('active', 'active')}` }} foot={`${totalSlots} ${tt('slots', 'slots')} total`} />
        <KpiChip label={t('arr')} value={ecoError ? '—' : <CountUp value={economics?.arr ?? 0} prefix="⃁ " />} foot={tt('annual_run_rate', 'annual run-rate')} />
        <KpiChip label={tt('churn_rate', 'Churn Rate')} value={ecoError ? '—' : <CountUp value={(economics?.churn_rate ?? 0) * 100} decimals={1} suffix="%" />} foot={ecoError ? '' : `${economics?.churned_clients ?? 0} ${tt('churned', 'churned')}`} />
        <KpiChip label={tt('collected', 'Collected')} value={ecoError ? '—' : <CountUp value={economics?.collected ?? 0} prefix="⃁ " />} foot={ecoError ? '' : `${tt('platform_revenue', 'platform rev')} ${formatMoney(economics?.platform_revenue ?? 0, language)}`} />

        {/* Leaderboard */}
        <section className="dxr-tile lg:col-span-8 lg:row-span-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[16px] font-extrabold tracking-tight">{tt('revenue_by_agent', 'Revenue by Agent')}</h2>
            <button onClick={() => navigate('/audit')} className="inline-flex items-center gap-1 text-[13px] font-bold text-brand-700">{tt('view_all', 'View all')} <ArrowRight className="h-[15px] w-[15px]" /></button>
          </div>
          {ecoLoading ? (
            <div className="animate-pulse py-10 text-center text-muted-foreground">{t('loading')}</div>
          ) : ecoError ? (
            <ErrorState onRetry={loadEconomics} />
          ) : leaderboard.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">{t('economics_empty')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-[10.5px] font-bold uppercase tracking-wider text-muted-foreground/80">
                    <th className="w-8 pb-2.5 text-start" />
                    <th className="pb-2.5 pe-3 text-start">{tt('company_name', 'Agent')}</th>
                    <th className="pb-2.5 pe-3 text-start">{tt('active_merchants', 'Merchants')}</th>
                    <th className="pb-2.5 pe-3 text-start">{t('mrr')}</th>
                    <th className="pb-2.5 pe-3 text-start">{tt('share', 'Share')}</th>
                    <th className="pb-2.5 text-start">{t('status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboard.map((a, i) => (
                    <tr key={a.agent_id} className="border-t border-border/70 transition-colors hover:bg-muted/40">
                      <td className={cn('py-3 pe-2 font-mono text-[12px] font-bold', i < 5 ? 'text-gold-600' : 'text-muted-foreground')}>{String(i + 1).padStart(2, '0')}</td>
                      <td className="py-3 pe-3">
                        <div className="flex items-center gap-2.5">
                          <span className={cn('flex h-8 w-8 items-center justify-center rounded-[10px] text-[12px] font-extrabold text-white', AV_GRADS[i % AV_GRADS.length])}>{initials(a.company_name)}</span>
                          <span className="font-bold">{a.company_name}</span>
                        </div>
                      </td>
                      <td className="py-3 pe-3 tabular-nums text-muted-foreground">{a.active_clients}/{a.total_clients}</td>
                      <td className="py-3 pe-3 font-extrabold tabular-nums">{formatMoney(a.mrr, language)}</td>
                      <td className="py-3 pe-3"><div className="w-[90px]"><Bar pct={topMrr > 0 ? Math.round((a.mrr / topMrr) * 100) : 0} /></div></td>
                      <td className="py-3"><span className={a.is_active ? 'pill-success' : 'pill-danger'}><span className="h-1.5 w-1.5 rounded-full bg-current" />{a.is_active ? t('active') : t('inactive')}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Needs attention */}
        <section className="dxr-tile lg:col-span-4 lg:row-span-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[16px] font-extrabold tracking-tight">{tt('needs_attention', 'Needs Attention')}</h2>
            <span className="pill-danger tabular-nums">{suspended.length + nearCap.length}</span>
          </div>
          <div className="space-y-2.5">
            {suspended.slice(0, 2).map((a) => (
              <div key={a.id} className="dxr-insight cursor-pointer" onClick={() => handleToggle(a.id)}>
                <div className="dxr-sw dxr-sw-danger h-[34px] w-[34px]"><AlertTriangle className="h-[17px] w-[17px]" /></div>
                <div className="min-w-0">
                  <div className="text-[13.5px] font-bold">{a.company_name} {tt('paused', 'paused')}</div>
                  <div className="text-[12px] text-muted-foreground">{tt('reactivate_account', 'Tap to reactivate account')}</div>
                </div>
                <ChevronRight className="ms-auto h-[17px] w-[17px] self-center text-muted-foreground" />
              </div>
            ))}
            {nearCap.slice(0, 2).map((a) => (
              <div key={`cap-${a.id}`} className="dxr-insight cursor-pointer" onClick={() => { setSlotDialog({ agentId: a.id, company: a.company_name }); setSlotAmount('5'); }}>
                <div className="dxr-sw dxr-sw-warning h-[34px] w-[34px]"><PackageIcon className="h-[17px] w-[17px]" /></div>
                <div className="min-w-0">
                  <div className="text-[13.5px] font-bold">{a.company_name} {tt('near_slot_cap', 'near slot cap')}</div>
                  <div className="text-[12px] text-muted-foreground">{a.used_slots}/{a.package_type} {tt('slots_used', 'slots used')} · {tt('add_slots', 'add slots')}</div>
                </div>
                <ChevronRight className="ms-auto h-[17px] w-[17px] self-center text-muted-foreground" />
              </div>
            ))}
            <div className="dxr-insight cursor-pointer" onClick={openTaxDialog}>
              <div className="dxr-sw dxr-sw-sky h-[34px] w-[34px]"><Percent className="h-[17px] w-[17px]" /></div>
              <div className="min-w-0">
                <div className="text-[13.5px] font-bold">{tt('review_tax_rate', 'Review global tax rate')}</div>
                <div className="text-[12px] text-muted-foreground">{tt('vat_compliance', 'VAT applied platform-wide')}</div>
              </div>
              <ChevronRight className="ms-auto h-[17px] w-[17px] self-center text-muted-foreground" />
            </div>
            {suspended.length === 0 && nearCap.length === 0 && (
              <p className="px-1 py-4 text-[13px] text-muted-foreground">{tt('all_systems_operational', 'All systems operational.')}</p>
            )}
          </div>
          <Button variant="outline" className="mt-4 w-full" onClick={() => navigate('/audit')}>{tt('review_all_signals', 'Review all signals')}</Button>
        </section>

        {/* Activity timeline */}
        <section className="dxr-tile lg:col-span-8 lg:row-span-3">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[16px] font-extrabold tracking-tight">{tt('recent_activity', 'Recent Activity')}</h2>
            <button onClick={() => navigate('/audit')} className="inline-flex items-center gap-1 text-[13px] font-bold text-brand-700">{tt('audit_log', 'Audit log')} <ArrowRight className="h-[15px] w-[15px]" /></button>
          </div>
          {auditEntries.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{tt('no_recent_activity', 'No recent activity.')}</p>
          ) : (
            <div>
              {auditEntries.slice(0, 6).map((e, i, arr) => (
                <div key={e.id} className="flex gap-3 py-2.5">
                  <div className="flex flex-col items-center">
                    <span className="z-[1] h-2.5 w-2.5 rounded-full bg-brand ring-4 ring-brand-50 dark:ring-brand-500/15" />
                    {i < arr.length - 1 && <span className="my-0.5 -mb-2.5 w-0.5 flex-1 bg-border" />}
                  </div>
                  <div className="min-w-0 pb-1">
                    <div className="text-[13px] text-foreground/80">
                      {e.user_email && <b className="font-bold text-foreground">{e.user_email}</b>}{' '}
                      {e.details || e.action}
                    </div>
                    <div className="mt-0.5 font-mono text-[10.5px] text-muted-foreground">
                      {e.created_at ? new Date(e.created_at).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* System health gauge */}
        <section className="dxr-tile dxr-hover lg:col-span-4 lg:row-span-3">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-[14px] font-extrabold">{tt('system_health', 'System Health')}</h2>
            <span className="pill-success"><span className="h-1.5 w-1.5 rounded-full bg-current" />{tt('operational', 'Operational')}</span>
          </div>
          <Gauge
            pct={healthPct}
            size={104}
            center={`${activeAgents}/${totalAgents}`}
            caption={tt('agents_online', 'agents online')}
          />
        </section>
      </div>

      {/* Packages overview */}
      {packages.length > 0 && (
        <section>
          <h2 className="mb-3 text-[16px] font-extrabold tracking-tight">{t('packages')}</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {packages.map((pkg) => (
              <div key={pkg.id} className="rounded-2xl border border-border bg-card p-5 shadow-sm transition-transform hover:-translate-y-0.5">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-extrabold">{pkg.name}</h3>
                  <span className="dxr-sw dxr-sw-brand h-9 w-9"><PackageIcon className="h-[18px] w-[18px]" /></span>
                </div>
                <div className="mt-3 space-y-1.5 text-sm text-muted-foreground">
                  <p>{t('client_slots')}: <span className="font-semibold tabular-nums text-foreground">{pkg.client_slots}</span></p>
                  <p>{t('wholesale_price')}: <span className="font-semibold text-foreground">{formatMoney(pkg.wholesale_price || 0, language)}</span></p>
                  <p>{t('retail_price')}: <span className="font-semibold text-foreground">{formatMoney(pkg.suggested_retail_price || 0, language)}</span></p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ===== Dialogs (unchanged behaviour) ===== */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogTrigger asChild><span className="hidden" /></DialogTrigger>
        <DialogContent>
          <DialogHeader><DialogTitle>{tt('create_agent', 'Create Agent')}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">{t('company_name')}</label>
              <Input placeholder={t('company_name')} value={newAgentForm.company_name} onChange={(e) => setNewAgentForm({ ...newAgentForm, company_name: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">{t('email')}</label>
              <Input placeholder={t('email')} type="email" value={newAgentForm.email} onChange={(e) => setNewAgentForm({ ...newAgentForm, email: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">{t('phone')}</label>
              <Input placeholder={t('phone')} value={newAgentForm.phone} onChange={(e) => setNewAgentForm({ ...newAgentForm, phone: e.target.value })} />
            </div>
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">{t('package')}</label>
              <Select value={newAgentForm.package_id} onValueChange={(v) => setNewAgentForm({ ...newAgentForm, package_id: v })}>
                <SelectTrigger><SelectValue placeholder={tt('select_package', 'Select Package')} /></SelectTrigger>
                <SelectContent>
                  {packages.map((pkg) => (
                    <SelectItem key={pkg.id} value={String(pkg.id)}>{pkg.name} ({pkg.client_slots} {t('slots')})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>{t('cancel')}</Button>
              <Button onClick={handleCreateAgent} disabled={creating || !newAgentForm.company_name || !newAgentForm.email}>{creating ? t('loading') : (tt('create_agent', 'Create Agent'))}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!createdCreds} onOpenChange={(open) => !open && setCreatedCreds(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{tt('agent_created', 'Agent created')}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{tt('credentials_show_once', 'Share these login credentials with the agent now — they will not be shown again.')}</p>
            <div className="rounded-xl bg-muted p-3 font-mono text-sm text-foreground">
              <div>{t('email')}: {createdCreds?.email}</div>
              <div>{tt('password', 'Password')}: {createdCreds?.temp_password}</div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { if (createdCreds) navigator.clipboard?.writeText(`Email: ${createdCreds.email}\nPassword: ${createdCreds.temp_password}`); }}>{tt('copy', 'Copy')}</Button>
              <Button onClick={() => setCreatedCreds(null)}>{tt('done', 'Done')}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!slotDialog} onOpenChange={(open) => !open && setSlotDialog(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{tt('add_slots', 'Add Slots')} — {slotDialog?.company}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">{tt('slots', 'Slots')}</label>
              <Input type="number" min={1} value={slotAmount} onChange={(e) => setSlotAmount(e.target.value)} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setSlotDialog(null)}>{t('cancel')}</Button>
              <Button onClick={handleAddSlots}>{tt('add_slots', 'Add Slots')}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={taxDialogOpen} onOpenChange={setTaxDialogOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{tt('tax_rate', 'Global Tax Rate')}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">{tt('tax_rate', 'Tax Rate')} (%)</label>
              <Input type="number" min={0} max={100} step="0.1" value={taxInput} onChange={(e) => setTaxInput(e.target.value)} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setTaxDialogOpen(false)}>{t('cancel')}</Button>
              <Button onClick={handleSaveTax} disabled={savingTax}>{savingTax ? t('loading') : (tt('save', 'Save'))}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Compact KPI chip tile (1-row bento cell).
function KpiChip({
  label, value, delta, foot,
}: {
  label: string;
  value: ReactNode;
  delta?: { dir: 'up' | 'down' | 'flat'; text: string };
  foot?: string;
}) {
  return (
    <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
      <div className="flex items-center justify-between">
        <div className="text-[12.5px] font-semibold text-muted-foreground">{label}</div>
        {delta && (
          <span className={cn('dxr-delta', delta.dir === 'up' ? 'dxr-delta-up' : delta.dir === 'down' ? 'dxr-delta-down' : 'dxr-delta-flat')}>
            {delta.dir === 'up' ? <TrendingUp className="h-3 w-3" /> : delta.dir === 'down' ? <TrendingDown className="h-3 w-3" /> : null}
            {delta.text}
          </span>
        )}
      </div>
      <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums">{value}</div>
    </section>
  );
}
