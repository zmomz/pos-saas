import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { client } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatNumber, formatDate } from '@/lib/format';
import ErrorState from '@/components/states/ErrorState';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile from '@/components/dashboard/StatTile';
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
import { Gift, Star, Users, Settings, Plus, Minus } from 'lucide-react';

interface LoyaltyConfig {
  id?: string;
  points_per_sar: number;
  redemption_rate: number;
  min_points_redeem: number;
  points_expiry_days: number;
  is_active: boolean;
}

interface CustomerLoyalty {
  id: string;
  customer_name: string;
  customer_id: string;
  points_balance: number;
  available_points?: number;
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
  points_expiry_days: 0,
  is_active: true,
};

export default function LoyaltyProgram() {
  const [config, setConfig] = useState<LoyaltyConfig>(defaultConfig);
  const [customerBalances, setCustomerBalances] = useState<CustomerLoyalty[]>([]);
  const [transactions, setTransactions] = useState<PointsTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [configEditing, setConfigEditing] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerLoyalty | null>(null);
  const [adjustPoints, setAdjustPoints] = useState('');
  const [adjustType, setAdjustType] = useState<'add' | 'deduct'>('add');
  const [adjustReason, setAdjustReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<'balances' | 'history'>('balances');

  const { t, language } = useLanguage();
  const tt = (key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  };

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setLoadError(false);
    try {
      // ISSUE-020 (C4 / U3.8): these endpoints were each wrapped in a swallowing
      // catch, so a missing/failing one rendered the same empty view as a healthy
      // empty program. Load them under one try/catch and surface a real error
      // (ErrorState) on any failure instead of silently faking "no data".
      const configRes = await client.apiCall.invoke({
        url: '/api/v1/production/loyalty/config',
        method: 'GET',
        data: {},
      });
      if (configRes.data && configRes.data.points_per_sar != null) {
        setConfig(configRes.data);
      }
      const balancesRes = await client.apiCall.invoke({
        url: '/api/v1/production/loyalty/balances',
        method: 'GET',
        data: {},
      });
      const bData = balancesRes.data;
      setCustomerBalances(Array.isArray(bData?.items) ? bData.items : Array.isArray(bData) ? bData : []);
      const txRes = await client.apiCall.invoke({
        url: '/api/v1/production/loyalty/transactions',
        method: 'GET',
        data: { limit: 50 },
      });
      const tData = txRes.data;
      setTransactions(Array.isArray(tData?.items) ? tData.items : Array.isArray(tData) ? tData : []);
    } catch (err) {
      console.error('Failed to load loyalty data:', err);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
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
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  if (loadError) {
    return <ErrorState message={t('loyalty_load_error')} onRetry={loadData} />;
  }

  const balanceColumns: DataTableColumn<CustomerLoyalty>[] = [
    {
      key: 'customer',
      header: tt('customer', 'Customer'),
      cell: (cust) => <span className="text-foreground font-medium">{cust.customer_name}</span>,
    },
    {
      key: 'balance',
      header: tt('balance', 'Balance'),
      cell: (cust) => (
        <span className="text-foreground/90">
          <span className="text-gold-600 font-bold tabular-nums">{formatNumber(cust.points_balance ?? 0, language, 0)}</span> {tt('pts', 'pts')}
        </span>
      ),
    },
    {
      key: 'available',
      header: tt('available', 'Available'),
      cell: (cust) => (
        <span className="text-foreground/90">
          <span className="text-brand font-bold tabular-nums">
            {formatNumber((cust.available_points ?? cust.points_balance) ?? 0, language, 0)}
          </span> {tt('pts', 'pts')}
        </span>
      ),
    },
    {
      key: 'total_earned',
      header: tt('total_earned', 'Total Earned'),
      cell: (cust) => <span className="text-success tabular-nums">{formatNumber(cust.total_earned ?? 0, language, 0)}</span>,
    },
    {
      key: 'total_redeemed',
      header: tt('total_redeemed', 'Total Redeemed'),
      cell: (cust) => <span className="text-danger tabular-nums">{formatNumber(cust.total_redeemed ?? 0, language, 0)}</span>,
    },
    {
      key: 'last_activity',
      header: tt('last_activity', 'Last Activity'),
      cell: (cust) => (
        <span className="text-foreground/90 tabular-nums">{cust.last_activity ? formatDate(cust.last_activity, language) : '—'}</span>
      ),
    },
    {
      key: 'actions',
      header: tt('actions', 'Actions'),
      cell: (cust) => (
        <Button
          size="sm"
          variant="outline"
          onClick={() => { setSelectedCustomer(cust); setAdjustOpen(true); }}
          className="text-xs"
        >
          {tt('adjust', 'Adjust')}
        </Button>
      ),
    },
  ];

  const historyColumns: DataTableColumn<PointsTransaction>[] = [
    {
      key: 'date',
      header: tt('date', 'Date'),
      cell: (tx) => <span className="text-foreground/90 tabular-nums">{formatDate(tx.created_at, language)}</span>,
    },
    {
      key: 'customer',
      header: tt('customer', 'Customer'),
      cell: (tx) => <span className="text-foreground">{tx.customer_name || '—'}</span>,
    },
    {
      key: 'type',
      header: tt('type', 'Type'),
      cell: (tx) => (
        <span className={tx.type === 'earned' || tx.type === 'add' ? 'pill-success' : 'pill-danger'}>
          {tx.type}
        </span>
      ),
    },
    {
      key: 'points',
      header: tt('points', 'Points'),
      cell: (tx) => (
        <span className={`tabular-nums ${tx.type === 'earned' || tx.type === 'add' ? 'text-success' : 'text-danger'}`}>
          {tx.type === 'earned' || tx.type === 'add' ? '+' : '-'}{tx.points}
        </span>
      ),
    },
    {
      key: 'description',
      header: tt('description', 'Description'),
      cell: (tx) => <span className="text-foreground/90">{tx.description || '—'}</span>,
    },
  ];

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Gift className="h-[18px] w-[18px]" /></span>}
        title={tt('loyalty_program', 'Loyalty Program')}
        subtitle={`${customerBalances.length} ${tt('members', 'Members')}`}
      />

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile icon={Users} label={tt('members', 'Members')} value={customerBalances.length} tone="brand" />
        <StatTile
          icon={Star}
          label={tt('total_points_outstanding', 'Total Points Outstanding')}
          value={formatNumber(customerBalances.reduce((sum, c) => sum + (c.points_balance || 0), 0), language, 0)}
          tone="gold"
        />
        <StatTile
          icon={Gift}
          label={tt('program_status', 'Program Status')}
          value={config.is_active ? tt('active', 'Active') : tt('inactive', 'Inactive')}
          tone={config.is_active ? 'success' : 'warning'}
        />
      </div>

      {/* Configuration */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-foreground flex items-center gap-2">
            <Settings className="h-5 w-5 text-muted-foreground" />
            {tt('program_configuration', 'Program Configuration')}
          </CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setConfigEditing(!configEditing)}
          >
            {configEditing ? t('cancel') : tt('edit', 'Edit')}
          </Button>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            <div>
              <Label className="text-xs block mb-1">{tt('points_per_sar_spent', 'Points per ⃁ spent')}</Label>
              {configEditing ? (
                <Input type="number" value={config.points_per_sar} onChange={(e) => setConfig((c) => ({ ...c, points_per_sar: parseFloat(e.target.value) || 0 }))} />
              ) : (
                <p className="text-foreground font-medium text-lg tabular-nums">{config.points_per_sar}</p>
              )}
            </div>
            <div>
              <Label className="text-xs block mb-1">{tt('redemption_rate', 'Redemption Rate (⃁/point)')}</Label>
              {configEditing ? (
                <Input type="number" step="0.01" value={config.redemption_rate} onChange={(e) => setConfig((c) => ({ ...c, redemption_rate: parseFloat(e.target.value) || 0 }))} />
              ) : (
                <p className="text-foreground font-medium text-lg tabular-nums">{config.redemption_rate}</p>
              )}
            </div>
            <div>
              <Label className="text-xs block mb-1">{tt('min_points_to_redeem', 'Min Points to Redeem')}</Label>
              {configEditing ? (
                <Input type="number" value={config.min_points_redeem} onChange={(e) => setConfig((c) => ({ ...c, min_points_redeem: parseInt(e.target.value) || 0 }))} />
              ) : (
                <p className="text-foreground font-medium text-lg tabular-nums">{config.min_points_redeem}</p>
              )}
            </div>
            <div>
              <Label className="text-xs block mb-1">{tt('points_expiry_days', 'Points Expiry (days, 0 = never)')}</Label>
              {configEditing ? (
                <Input type="number" value={config.points_expiry_days} onChange={(e) => setConfig((c) => ({ ...c, points_expiry_days: parseInt(e.target.value) || 0 }))} />
              ) : (
                <p className="text-foreground font-medium text-lg tabular-nums">{config.points_expiry_days ? config.points_expiry_days : tt('never', 'Never')}</p>
              )}
            </div>
            <div>
              <Label className="text-xs block mb-1">{tt('status', 'Status')}</Label>
              {configEditing ? (
                <Button
                  size="sm"
                  variant={config.is_active ? 'success' : 'danger'}
                  onClick={() => setConfig((c) => ({ ...c, is_active: !c.is_active }))}
                >
                  {config.is_active ? tt('active', 'Active') : tt('inactive', 'Inactive')}
                </Button>
              ) : (
                <span className={config.is_active ? 'pill-success' : 'pill-danger'}>
                  {config.is_active ? tt('active', 'Active') : tt('inactive', 'Inactive')}
                </span>
              )}
            </div>
          </div>
          {configEditing && (
            <Button onClick={handleSaveConfig} disabled={submitting} className="mt-4">
              {submitting ? t('loading') : t('save_changes')}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Tabs */}
      <div className="dxr-seg">
        <button data-active={activeTab === 'balances'} onClick={() => setActiveTab('balances')}>
          {tt('customer_balances', 'Customer Balances')}
        </button>
        <button data-active={activeTab === 'history'} onClick={() => setActiveTab('history')}>
          {tt('points_history', 'Points History')}
        </button>
      </div>

      {activeTab === 'balances' && (
        <div className="rounded-lg border border-border">
          <DataTable<CustomerLoyalty>
            columns={balanceColumns}
            rows={customerBalances}
            rowKey={(cust) => cust.id}
            empty={tt('no_loyalty_members', 'No loyalty members yet')}
          />
        </div>
      )}

      {activeTab === 'history' && (
        <div className="rounded-lg border border-border">
          <DataTable<PointsTransaction>
            columns={historyColumns}
            rows={transactions}
            rowKey={(tx) => tx.id}
            empty={tt('no_transactions', 'No transactions yet')}
          />
        </div>
      )}

      {/* Adjust Points Dialog */}
      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{tt('adjust_points', 'Adjust Points')} - {selectedCustomer?.customer_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex gap-2">
              <Button
                onClick={() => setAdjustType('add')}
                variant={adjustType === 'add' ? 'success' : 'secondary'}
                className="flex-1"
              >
                <Plus className="h-4 w-4 me-1" /> {tt('add_points', 'Add Points')}
              </Button>
              <Button
                onClick={() => setAdjustType('deduct')}
                variant={adjustType === 'deduct' ? 'danger' : 'secondary'}
                className="flex-1"
              >
                <Minus className="h-4 w-4 me-1" /> {tt('deduct_points', 'Deduct Points')}
              </Button>
            </div>
            <div>
              <Label className="mb-1 block">{tt('points', 'Points')}</Label>
              <Input type="number" value={adjustPoints} onChange={(e) => setAdjustPoints(e.target.value)} placeholder="0" />
            </div>
            <div>
              <Label className="mb-1 block">{tt('reason', 'Reason')}</Label>
              <Input value={adjustReason} onChange={(e) => setAdjustReason(e.target.value)} placeholder={tt('manual_adjustment_reason', 'Manual adjustment reason')} />
            </div>
            <Button onClick={handleAdjustPoints} disabled={submitting || !adjustPoints} className="w-full">
              {submitting ? t('loading') : tt('confirm_adjustment', 'Confirm Adjustment')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}