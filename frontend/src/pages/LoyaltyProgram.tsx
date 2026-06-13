import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { client } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Gift, Star, Users, Settings, Plus, Minus } from 'lucide-react';

interface LoyaltyConfig {
  id?: string;
  points_per_sar: number;
  redemption_rate: number;
  min_points_redeem: number;
  is_active: boolean;
}

interface CustomerLoyalty {
  id: string;
  customer_name: string;
  customer_id: string;
  points_balance: number;
  total_earned: number;
  total_redeemed: number;
  last_activity?: string;
}

interface PointsTransaction {
  id: string;
  customer_name?: string;
  type: string;
  points: number;
  description?: string;
  created_at: string;
}

const defaultConfig: LoyaltyConfig = {
  points_per_sar: 1,
  redemption_rate: 0.1,
  min_points_redeem: 100,
  is_active: true,
};

export default function LoyaltyProgram() {
  const [config, setConfig] = useState<LoyaltyConfig>(defaultConfig);
  const [customerBalances, setCustomerBalances] = useState<CustomerLoyalty[]>([]);
  const [transactions, setTransactions] = useState<PointsTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [configEditing, setConfigEditing] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerLoyalty | null>(null);
  const [adjustPoints, setAdjustPoints] = useState('');
  const [adjustType, setAdjustType] = useState<'add' | 'deduct'>('add');
  const [adjustReason, setAdjustReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<'balances' | 'history'>('balances');

  const { t } = useLanguage();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const configRes = await client.apiCall.invoke({
        url: '/api/v1/production/loyalty/config',
        method: 'GET',
        data: {},
      });
      if (configRes.data && configRes.data.points_per_sar != null) {
        setConfig(configRes.data);
      }
    } catch {
      // Use defaults
    }
    try {
      const balancesRes = await client.apiCall.invoke({
        url: '/api/v1/production/loyalty/balances',
        method: 'GET',
        data: {},
      });
      const bData = balancesRes.data;
      setCustomerBalances(Array.isArray(bData?.items) ? bData.items : Array.isArray(bData) ? bData : []);
    } catch {
      setCustomerBalances([]);
    }
    try {
      const txRes = await client.apiCall.invoke({
        url: '/api/v1/production/loyalty/transactions',
        method: 'GET',
        data: { limit: 50 },
      });
      const tData = txRes.data;
      setTransactions(Array.isArray(tData?.items) ? tData.items : Array.isArray(tData) ? tData : []);
    } catch {
      setTransactions([]);
    }
    setLoading(false);
  }

  async function handleSaveConfig() {
    setSubmitting(true);
    try {
      await client.apiCall.invoke({
        url: '/api/v1/production/loyalty/config',
        method: 'POST',
        data: config,
      });
      setConfigEditing(false);
    } catch (err) {
      console.error('Failed to save loyalty config:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAdjustPoints() {
    if (!selectedCustomer) return;
    setSubmitting(true);
    try {
      await client.apiCall.invoke({
        url: '/api/v1/production/loyalty/adjust',
        method: 'POST',
        data: {
          customer_id: selectedCustomer.customer_id,
          type: adjustType,
          points: parseInt(adjustPoints) || 0,
          reason: adjustReason,
        },
      });
      setAdjustOpen(false);
      setAdjustPoints('');
      setAdjustReason('');
      await loadData();
    } catch (err) {
      console.error('Failed to adjust points:', err);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <Users className="h-8 w-8 text-brand-400" />
            <div>
              <p className="text-slate-400 text-sm">Members</p>
              <p className="text-2xl font-bold text-white">{customerBalances.length}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <Star className="h-8 w-8 text-yellow-400" />
            <div>
              <p className="text-slate-400 text-sm">Total Points Outstanding</p>
              <p className="text-2xl font-bold text-yellow-400">
                {customerBalances.reduce((sum, c) => sum + (c.points_balance || 0), 0).toLocaleString()}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <Gift className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-slate-400 text-sm">Program Status</p>
              <Badge className={config.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}>
                {config.is_active ? 'Active' : 'Inactive'}
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Configuration */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-white flex items-center gap-2">
            <Settings className="h-5 w-5 text-slate-400" />
            Program Configuration
          </CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setConfigEditing(!configEditing)}
            className="border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            {configEditing ? t('cancel') : 'Edit'}
          </Button>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Points per SAR spent</label>
              {configEditing ? (
                <Input type="number" value={config.points_per_sar} onChange={(e) => setConfig((c) => ({ ...c, points_per_sar: parseFloat(e.target.value) || 0 }))} className="bg-slate-700 border-slate-600 text-white" />
              ) : (
                <p className="text-white font-medium text-lg">{config.points_per_sar}</p>
              )}
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Redemption Rate (SAR/point)</label>
              {configEditing ? (
                <Input type="number" step="0.01" value={config.redemption_rate} onChange={(e) => setConfig((c) => ({ ...c, redemption_rate: parseFloat(e.target.value) || 0 }))} className="bg-slate-700 border-slate-600 text-white" />
              ) : (
                <p className="text-white font-medium text-lg">{config.redemption_rate}</p>
              )}
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Min Points to Redeem</label>
              {configEditing ? (
                <Input type="number" value={config.min_points_redeem} onChange={(e) => setConfig((c) => ({ ...c, min_points_redeem: parseInt(e.target.value) || 0 }))} className="bg-slate-700 border-slate-600 text-white" />
              ) : (
                <p className="text-white font-medium text-lg">{config.min_points_redeem}</p>
              )}
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Status</label>
              {configEditing ? (
                <Button
                  size="sm"
                  onClick={() => setConfig((c) => ({ ...c, is_active: !c.is_active }))}
                  className={config.is_active ? 'bg-green-600 hover:bg-green-700 text-white' : 'bg-red-600 hover:bg-red-700 text-white'}
                >
                  {config.is_active ? 'Active' : 'Inactive'}
                </Button>
              ) : (
                <Badge className={config.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}>
                  {config.is_active ? 'Active' : 'Inactive'}
                </Badge>
              )}
            </div>
          </div>
          {configEditing && (
            <Button onClick={handleSaveConfig} disabled={submitting} className="mt-4 bg-brand-600 hover:bg-brand-700 text-white">
              {submitting ? t('loading') : t('save_changes')}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Tabs */}
      <div className="flex gap-2">
        <Button variant={activeTab === 'balances' ? 'default' : 'outline'} onClick={() => setActiveTab('balances')} className={activeTab === 'balances' ? 'bg-brand-600 text-white' : 'border-slate-600 text-slate-300'}>
          Customer Balances
        </Button>
        <Button variant={activeTab === 'history' ? 'default' : 'outline'} onClick={() => setActiveTab('history')} className={activeTab === 'history' ? 'bg-brand-600 text-white' : 'border-slate-600 text-slate-300'}>
          Points History
        </Button>
      </div>

      {activeTab === 'balances' && (
        <div className="overflow-x-auto rounded-lg border border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-800">
              <tr className="text-slate-400">
                <th className="p-3 text-start">Customer</th>
                <th className="p-3 text-start">Balance</th>
                <th className="p-3 text-start">Total Earned</th>
                <th className="p-3 text-start">Total Redeemed</th>
                <th className="p-3 text-start">Last Activity</th>
                <th className="p-3 text-start">Actions</th>
              </tr>
            </thead>
            <tbody>
              {customerBalances.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-slate-500">No loyalty members yet</td>
                </tr>
              ) : (
                customerBalances.map((cust) => (
                  <tr key={cust.id} className="border-t border-slate-700 text-slate-300">
                    <td className="p-3 text-white font-medium">{cust.customer_name}</td>
                    <td className="p-3">
                      <span className="text-yellow-400 font-bold">{cust.points_balance?.toLocaleString()}</span> pts
                    </td>
                    <td className="p-3 text-green-400">{cust.total_earned?.toLocaleString()}</td>
                    <td className="p-3 text-red-400">{cust.total_redeemed?.toLocaleString()}</td>
                    <td className="p-3">{cust.last_activity ? new Date(cust.last_activity).toLocaleDateString() : '—'}</td>
                    <td className="p-3">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => { setSelectedCustomer(cust); setAdjustOpen(true); }}
                        className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                      >
                        Adjust
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'history' && (
        <div className="overflow-x-auto rounded-lg border border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-800">
              <tr className="text-slate-400">
                <th className="p-3 text-start">Date</th>
                <th className="p-3 text-start">Customer</th>
                <th className="p-3 text-start">Type</th>
                <th className="p-3 text-start">Points</th>
                <th className="p-3 text-start">Description</th>
              </tr>
            </thead>
            <tbody>
              {transactions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-slate-500">No transactions yet</td>
                </tr>
              ) : (
                transactions.map((tx) => (
                  <tr key={tx.id} className="border-t border-slate-700 text-slate-300">
                    <td className="p-3">{new Date(tx.created_at).toLocaleDateString()}</td>
                    <td className="p-3 text-white">{tx.customer_name || '—'}</td>
                    <td className="p-3">
                      <Badge className={tx.type === 'earned' || tx.type === 'add' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}>
                        {tx.type}
                      </Badge>
                    </td>
                    <td className="p-3">
                      <span className={tx.type === 'earned' || tx.type === 'add' ? 'text-green-400' : 'text-red-400'}>
                        {tx.type === 'earned' || tx.type === 'add' ? '+' : '-'}{tx.points}
                      </span>
                    </td>
                    <td className="p-3">{tx.description || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Adjust Points Dialog */}
      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Adjust Points - {selectedCustomer?.customer_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex gap-2">
              <Button
                onClick={() => setAdjustType('add')}
                className={adjustType === 'add' ? 'bg-green-600 text-white flex-1' : 'bg-slate-700 text-slate-300 flex-1'}
              >
                <Plus className="h-4 w-4 mr-1" /> Add Points
              </Button>
              <Button
                onClick={() => setAdjustType('deduct')}
                className={adjustType === 'deduct' ? 'bg-red-600 text-white flex-1' : 'bg-slate-700 text-slate-300 flex-1'}
              >
                <Minus className="h-4 w-4 mr-1" /> Deduct Points
              </Button>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Points</label>
              <Input type="number" value={adjustPoints} onChange={(e) => setAdjustPoints(e.target.value)} placeholder="0" className="bg-slate-700 border-slate-600 text-white" />
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Reason</label>
              <Input value={adjustReason} onChange={(e) => setAdjustReason(e.target.value)} placeholder="Manual adjustment reason" className="bg-slate-700 border-slate-600 text-white" />
            </div>
            <Button onClick={handleAdjustPoints} disabled={submitting || !adjustPoints} className="w-full bg-brand-600 hover:bg-brand-700 text-white">
              {submitting ? t('loading') : 'Confirm Adjustment'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}