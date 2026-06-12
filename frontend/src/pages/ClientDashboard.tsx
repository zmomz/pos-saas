import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { client, getClientDashboard, getClientBranding, getTransactions, getClientSubscription, payClientSubscription, downloadSubscriptionInvoice, type SubscriptionStatus } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import StatCard from '@/components/dashboard/StatCard';
import { PageHeader, SectionHeading } from '@/components/dashboard/PageHeader';
import { DollarSign, ShoppingCart, TrendingUp, Package as PackageIcon, Monitor, ShoppingBag, BarChart3, Users, Download, AlertTriangle } from 'lucide-react';

interface DashboardStats {
  total_sales: number;
  today_sales: number;
  total_transactions: number;
  today_transactions: number;
  products_count: number;
}

interface Transaction {
  id: number;
  invoice_number: string;
  total_amount: number;
  payment_method: string;
  created_at: string;
}

export default function ClientDashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [brandName, setBrandName] = useState('');
  const [subscription, setSubscription] = useState<SubscriptionStatus | null>(null);
  const [paying, setPaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { t, language } = useLanguage();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [dashData, brandData, txData, subData] = await Promise.all([
        getClientDashboard(),
        getClientBranding().catch(() => null),
        getTransactions(1, 10),
        getClientSubscription().catch(() => null),
      ]);
      setStats(dashData);
      setBrandName(brandData?.company_name || '');
      setTransactions(Array.isArray(txData) ? txData : (txData?.items || txData?.transactions || []));
      setSubscription(subData);
    } catch (err) {
      console.error('Failed to load:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    await client.auth.logout();
    navigate('/');
  }

  async function handlePaySubscription() {
    setPaying(true);
    try {
      const updated = await payClientSubscription();
      setSubscription(updated);
    } catch (err) {
      console.error('Subscription payment failed:', err);
    } finally {
      setPaying(false);
    }
  }

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
        title={brandName || t('dashboard')}
        subtitle={t('recent_transactions')}
        actions={
          <Button onClick={() => navigate('/pos')} className="shadow-brand">
            <Monitor className="h-4 w-4" />
            {t('go_to_pos') || 'Open POS'}
          </Button>
        }
      />

      {/* Stats Cards */}
      <div data-tour="stats-section" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={DollarSign} tone="emerald" label={t('today_sales')} value={formatMoney(stats?.today_sales || 0, language)} />
        <StatCard icon={ShoppingCart} tone="sky" label={t('total_transactions')} value={stats?.total_transactions || 0} />
        <StatCard icon={TrendingUp} tone="violet" label={t('total_sales')} value={formatMoney(stats?.total_sales || 0, language)} />
        <StatCard icon={PackageIcon} tone="amber" label={t('products_count')} value={stats?.products_count || 0} />
      </div>

      {/* Quick Actions */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-3">
        <Button variant="outline" onClick={() => navigate('/products')}>
          <ShoppingBag className="h-4 w-4" />
          {t('manage_products') || 'Products'}
        </Button>
        <Button variant="outline" onClick={() => navigate('/reports')}>
          <BarChart3 className="h-4 w-4" />
          {t('reports_analytics') || 'Reports'}
        </Button>
        <Button variant="outline" onClick={() => navigate('/staff')}>
          <Users className="h-4 w-4" />
          {t('staff') || 'Staff'}
        </Button>
      </div>

      {/* Subscription panel (CL-04) */}
      {subscription && (subscription.subscription_fee > 0 || subscription.payments.length > 0) && (
        <section>
          <SectionHeading title={t('subscription')} />
          <Card className="rounded-2xl shadow-card">
            <CardContent className="p-5 space-y-3">
              {/* Dunning notice (CL-06 / PRN-09): overdue amount + grace deadline + pay */}
              {(subscription.subscription_status === 'past_due' ||
                subscription.subscription_status === 'dunning' ||
                subscription.subscription_status === 'suspended') && (
                <div
                  role="alert"
                  className={`flex items-start gap-3 rounded-xl border p-3 text-sm ${
                    subscription.subscription_status === 'suspended'
                      ? 'border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-300'
                      : 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-300'
                  }`}
                >
                  <AlertTriangle className="h-5 w-5 shrink-0" />
                  <div>
                    <p className="font-semibold">
                      {subscription.subscription_status === 'suspended'
                        ? t('subscription_suspended_notice')
                        : t('payment_overdue_notice')}
                    </p>
                    <p className="opacity-90">
                      {t('overdue_amount')}: {formatMoney(subscription.subscription_fee, language)}
                      {subscription.grace_deadline
                        ? ` · ${t('pay_before')} ${subscription.grace_deadline}`
                        : ''}
                    </p>
                  </div>
                </div>
              )}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-muted-foreground">{t('subscription_fee')}</p>
                  <p className="text-xl font-bold text-foreground">
                    {formatMoney(subscription.subscription_fee, language)} / {t(subscription.billing_cycle) || subscription.billing_cycle}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{t('next_billing')}</p>
                  <p className="text-foreground/80">{subscription.next_billing_date || '—'}</p>
                </div>
                <div>
                  <Badge className={subscription.subscription_status === 'active' ? 'bg-emerald-600 text-white' : subscription.subscription_status === 'suspended' ? 'bg-red-600 text-white' : 'bg-amber-500 text-white'}>
                    {subscription.subscription_status}
                  </Badge>
                </div>
                <Button
                  onClick={handlePaySubscription}
                  disabled={paying || subscription.subscription_fee <= 0}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  {paying ? t('loading') : (t('pay_now') || 'Pay now')}
                </Button>
              </div>
              {subscription.payments.length > 0 && (
                <div className="border-t border-border pt-3">
                  <p className="text-sm mb-2 text-muted-foreground">{t('payment_history')}</p>
                  <div className="space-y-1">
                    {subscription.payments.slice(0, 6).map((p) => (
                      <div key={p.id} className="flex items-center justify-between text-sm text-foreground/80">
                        <span>{p.period_start || (p.created_at ? p.created_at.slice(0, 10) : '')}</span>
                        <div className="flex items-center gap-3">
                          <span>{formatMoney(p.amount, language)}</span>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 gap-1"
                            onClick={() => downloadSubscriptionInvoice(p.id)}
                            title={t('download_invoice')}
                          >
                            <Download className="h-4 w-4" />
                            <span className="hidden sm:inline">{t('download_invoice')}</span>
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      )}

      {/* Recent Transactions */}
      <section>
        <SectionHeading title={t('recent_transactions')} />
        <div className="overflow-x-auto rounded-2xl border border-border bg-card shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="p-3 text-start font-medium">{t('invoice_number')}</th>
                <th className="p-3 text-start font-medium">{t('total')}</th>
                <th className="p-3 text-start font-medium">{t('payment_method')}</th>
                <th className="p-3 text-start font-medium">{t('status')}</th>
              </tr>
            </thead>
            <tbody>
              {transactions.length === 0 ? (
                <tr>
                  <td colSpan={4} className="p-6 text-center text-muted-foreground">
                    {t('empty_cart')}
                  </td>
                </tr>
              ) : (
                transactions.map((tx) => (
                  <tr key={tx.id} className="border-t border-border text-foreground/80 transition-colors hover:bg-muted/40">
                    <td className="p-3 font-mono">{tx.invoice_number}</td>
                    <td className="p-3">{formatMoney(tx.total_amount || 0, language)}</td>
                    <td className="p-3">
                      <Badge variant="secondary">{tx.payment_method}</Badge>
                    </td>
                    <td className="p-3">
                      <Badge className="bg-emerald-600 text-white">✓</Badge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
