import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { client, getMasterAgents, toggleAgent, getPackages, createAgent, addAgentSlots, getTaxRate, setGlobalTaxRate } from '@/lib/api';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { useTheme } from '@/contexts/ThemeContext';
import { Users, DollarSign, Package as PackageIcon, Activity, UserPlus, BarChart3, Settings, Shield } from 'lucide-react';

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
  const { t, language, setLanguage } = useLanguage();
  const { isDark } = useTheme();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [agentData, pkgData] = await Promise.all([getMasterAgents(), getPackages()]);
      setAgents(agentData?.agents || agentData || []);
      setPackages(pkgData?.items || pkgData || []);
    } catch (err) {
      console.error('Failed to load data:', err);
    } finally {
      setLoading(false);
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
  const totalRevenue = agents.reduce((sum, a) => sum + (a.used_slots * 50), 0);

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
              <p className={`text-sm ${isDark ? 'text-blue-300' : 'text-blue-600'}`}>{t('total_agents') || 'Total Agents'}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{totalAgents}</p>
            </div>
          </CardContent>
        </Card>

        <Card className={`${isDark ? 'bg-gradient-to-br from-green-900/40 to-slate-800 border-green-700/40' : 'bg-gradient-to-br from-green-50 to-white border-green-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-green-600/20' : 'bg-green-100'}`}>
              <DollarSign className={`h-6 w-6 ${isDark ? 'text-green-400' : 'text-green-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-green-300' : 'text-green-600'}`}>{t('total_revenue') || 'Total Revenue'}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{formatMoney(totalRevenue, language)}</p>
            </div>
          </CardContent>
        </Card>

        <Card className={`${isDark ? 'bg-gradient-to-br from-purple-900/40 to-slate-800 border-purple-700/40' : 'bg-gradient-to-br from-purple-50 to-white border-purple-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-purple-600/20' : 'bg-purple-100'}`}>
              <PackageIcon className={`h-6 w-6 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-purple-300' : 'text-purple-600'}`}>{t('active_packages') || 'Active Packages'}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{packages.length}</p>
            </div>
          </CardContent>
        </Card>

        <Card className={`${isDark ? 'bg-gradient-to-br from-emerald-900/40 to-slate-800 border-emerald-700/40' : 'bg-gradient-to-br from-emerald-50 to-white border-emerald-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-emerald-600/20' : 'bg-emerald-100'}`}>
              <Activity className={`h-6 w-6 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-emerald-300' : 'text-emerald-600'}`}>{t('system_health') || 'System Health'}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{activeAgents}/{totalAgents} {t('active') || 'Active'}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-3">
        <Button
          onClick={() => setCreateDialogOpen(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white"
        >
          <UserPlus className="h-4 w-4 mr-2" />
          {t('create_agent') || 'Add Agent'}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/packages')}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <Settings className="h-4 w-4 mr-2" />
          {t('package_management') || 'Manage Packages'}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/audit')}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <Shield className="h-4 w-4 mr-2" />
          {t('audit_log') || 'Audit Log'}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/notifications')}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <BarChart3 className="h-4 w-4 mr-2" />
          {t('notifications') || 'Notifications'}
        </Button>
        <Button
          variant="outline"
          onClick={openTaxDialog}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <DollarSign className="h-4 w-4 mr-2" />
          {t('tax_rate') || 'Tax Rate'}
        </Button>
      </div>

      {/* Package Overview */}
      <section>
        <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('packages')}</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {packages.map((pkg) => (
            <Card key={pkg.id} className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
              <CardHeader>
                <CardTitle className={isDark ? 'text-white' : 'text-slate-900'}>{pkg.name}</CardTitle>
              </CardHeader>
              <CardContent className={`space-y-2 text-sm ${isDark ? 'text-slate-300' : 'text-gray-600'}`}>
                <p>{t('client_slots')}: {pkg.client_slots}</p>
                <p>{t('wholesale_price')}: {formatMoney(pkg.wholesale_price || 0, language)}</p>
                <p>{t('retail_price')}: {formatMoney(pkg.retail_price_per_client || 0, language)}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Agents Table */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('agents')} ({agents.length})</h2>
          <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-green-600 hover:bg-green-700 text-white font-semibold">
                + {t('create_agent') || 'Create Agent'}
              </Button>
            </DialogTrigger>
            <DialogContent className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
              <DialogHeader>
                <DialogTitle className={isDark ? 'text-white' : 'text-slate-900'}>{t('create_agent') || 'Create Agent'}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className={`text-sm mb-1 block ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>{t('company_name')}</label>
                  <Input
                    placeholder={t('company_name')}
                    value={newAgentForm.company_name}
                    onChange={(e) => setNewAgentForm({ ...newAgentForm, company_name: e.target.value })}
                    className={isDark ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300 text-slate-900'}
                  />
                </div>
                <div>
                  <label className={`text-sm mb-1 block ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>{t('email')}</label>
                  <Input
                    placeholder={t('email')}
                    type="email"
                    value={newAgentForm.email}
                    onChange={(e) => setNewAgentForm({ ...newAgentForm, email: e.target.value })}
                    className={isDark ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300 text-slate-900'}
                  />
                </div>
                <div>
                  <label className={`text-sm mb-1 block ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>{t('phone')}</label>
                  <Input
                    placeholder={t('phone')}
                    value={newAgentForm.phone}
                    onChange={(e) => setNewAgentForm({ ...newAgentForm, phone: e.target.value })}
                    className={isDark ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300 text-slate-900'}
                  />
                </div>
                <div>
                  <label className={`text-sm mb-1 block ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>{t('package')}</label>
                  <Select
                    value={newAgentForm.package_id}
                    onValueChange={(v) => setNewAgentForm({ ...newAgentForm, package_id: v })}
                  >
                    <SelectTrigger className={isDark ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300 text-slate-900'}>
                      <SelectValue placeholder={t('select_package') || 'Select Package'} />
                    </SelectTrigger>
                    <SelectContent className={isDark ? 'bg-slate-800 border-slate-600' : 'bg-white border-gray-200'}>
                      {packages.map((pkg) => (
                        <SelectItem
                          key={pkg.id}
                          value={String(pkg.id)}
                          className={isDark ? 'text-white hover:bg-slate-700' : 'text-slate-900 hover:bg-gray-100'}
                        >
                          {pkg.name} ({pkg.client_slots} {t('slots')})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex gap-2 justify-end pt-2">
                  <Button
                    variant="outline"
                    onClick={() => setCreateDialogOpen(false)}
                    className={isDark ? 'border-slate-600 text-slate-300' : 'border-gray-300 text-gray-700'}
                  >
                    {t('cancel')}
                  </Button>
                  <Button
                    onClick={handleCreateAgent}
                    disabled={creating || !newAgentForm.company_name || !newAgentForm.email}
                    className="bg-green-600 hover:bg-green-700 text-white"
                  >
                    {creating ? t('loading') : (t('create_agent') || 'Create Agent')}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>

          {/* One-time credentials for a newly created agent (MA-01) */}
          <Dialog open={!!createdCreds} onOpenChange={(open) => !open && setCreatedCreds(null)}>
            <DialogContent className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
              <DialogHeader>
                <DialogTitle className={isDark ? 'text-white' : 'text-slate-900'}>
                  {t('agent_created') || 'Agent created'}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <p className={`text-sm ${isDark ? 'text-slate-300' : 'text-gray-600'}`}>
                  {t('credentials_show_once') ||
                    'Share these login credentials with the agent now — they will not be shown again. They must change the password on first login.'}
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

          {/* MA-04: add client slots to an agent's package */}
          <Dialog open={!!slotDialog} onOpenChange={(open) => !open && setSlotDialog(null)}>
            <DialogContent className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
              <DialogHeader>
                <DialogTitle className={isDark ? 'text-white' : 'text-slate-900'}>
                  {t('add_slots') || 'Add Slots'} — {slotDialog?.company}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className={`text-sm mb-1 block ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>
                    {t('slots') || 'Slots'}
                  </label>
                  <Input
                    type="number"
                    min={1}
                    value={slotAmount}
                    onChange={(e) => setSlotAmount(e.target.value)}
                    className={isDark ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300 text-slate-900'}
                  />
                </div>
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={() => setSlotDialog(null)} className={isDark ? 'border-slate-600 text-slate-300' : 'border-gray-300 text-gray-700'}>
                    {t('cancel')}
                  </Button>
                  <Button onClick={handleAddSlots} className="bg-blue-600 hover:bg-blue-700 text-white">
                    {t('add_slots') || 'Add Slots'}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>

          {/* MA-05: master global VAT/tax-rate setting */}
          <Dialog open={taxDialogOpen} onOpenChange={setTaxDialogOpen}>
            <DialogContent className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
              <DialogHeader>
                <DialogTitle className={isDark ? 'text-white' : 'text-slate-900'}>
                  {t('tax_rate') || 'Global Tax Rate'}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className={`text-sm mb-1 block ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>
                    {t('tax_rate') || 'Tax Rate'} (%)
                  </label>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    step="0.1"
                    value={taxInput}
                    onChange={(e) => setTaxInput(e.target.value)}
                    className={isDark ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300 text-slate-900'}
                  />
                </div>
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={() => setTaxDialogOpen(false)} className={isDark ? 'border-slate-600 text-slate-300' : 'border-gray-300 text-gray-700'}>
                    {t('cancel')}
                  </Button>
                  <Button onClick={handleSaveTax} disabled={savingTax} className="bg-green-600 hover:bg-green-700 text-white">
                    {savingTax ? t('loading') : (t('save') || 'Save')}
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
                <th className="p-3 text-start">{t('company_name')}</th>
                <th className="p-3 text-start">{t('email')}</th>
                <th className="p-3 text-start">{t('package')}</th>
                <th className="p-3 text-start">{t('slots')}</th>
                <th className="p-3 text-start">{t('status')}</th>
                <th className="p-3 text-start">{t('toggle')}</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id} className={`border-t ${isDark ? 'border-slate-700 text-slate-300' : 'border-gray-200 text-gray-700'}`}>
                  <td className="p-3">{agent.company_name}</td>
                  <td className="p-3">{agent.email}</td>
                  <td className="p-3">{agent.package_type}</td>
                  <td className="p-3">{agent.used_slots ?? 0}/{agent.package_type ?? 0}</td>
                  <td className="p-3">
                    <Badge className={agent.is_active ? 'bg-green-600 text-white' : 'bg-red-600 text-white'}>
                      {agent.is_active ? t('active') : t('inactive')}
                    </Badge>
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleToggle(agent.id)}
                        className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
                      >
                        {t('toggle')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => { setSlotDialog({ agentId: agent.id, company: agent.company_name }); setSlotAmount('1'); }}
                        className={isDark ? 'border-blue-600 text-blue-400 hover:bg-blue-600/10' : 'border-blue-300 text-blue-700 hover:bg-blue-50'}
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