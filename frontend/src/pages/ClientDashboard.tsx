import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { client, getClientDashboard, getClientBranding, getTransactions, getClientSubscription, payClientSubscription, downloadSubscriptionInvoice, type SubscriptionStatus } from '@/lib/api';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { useTheme } from '@/contexts/ThemeContext';
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
  const { t, language, setLanguage } = useLanguage();
  const { isDark } = useTheme();

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
      setTransactions(txData?.transactions || txData || []);
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
        <div className={`animate-pulse ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Enhanced Stats Cards */}
      <div data-tour="stats-section" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className={`${isDark ? 'bg-gradient-to-br from-green-900/40 to-slate-800 border-green-700/40' : 'bg-gradient-to-br from-green-50 to-white border-green-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-green-600/20' : 'bg-green-100'}`}>
              <DollarSign className={`h-6 w-6 ${isDark ? 'text-green-400' : 'text-green-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-green-300' : 'text-green-600'}`}>{t('today_sales')}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{formatMoney(stats?.today_sales || 0, language)}</p>
            </div>
          </CardContent>
        </Card>

        <Card className={`${isDark ? 'bg-gradient-to-br from-blue-900/40 to-slate-800 border-blue-700/40' : 'bg-gradient-to-br from-blue-50 to-white border-blue-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-blue-600/20' : 'bg-blue-100'}`}>
              <ShoppingCart className={`h-6 w-6 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-blue-300' : 'text-blue-600'}`}>{t('total_transactions')}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{stats?.total_transactions || 0}</p>
            </div>
          </CardContent>
        </Card>

        <Card className={`${isDark ? 'bg-gradient-to-br from-purple-900/40 to-slate-800 border-purple-700/40' : 'bg-gradient-to-br from-purple-50 to-white border-purple-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-purple-600/20' : 'bg-purple-100'}`}>
              <TrendingUp className={`h-6 w-6 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-purple-300' : 'text-purple-600'}`}>{t('total_sales')}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{formatMoney(stats?.total_sales || 0, language)}</p>
            </div>
          </CardContent>
        </Card>

        <Card className={`${isDark ? 'bg-gradient-to-br from-amber-900/40 to-slate-800 border-amber-700/40' : 'bg-gradient-to-br from-amber-50 to-white border-amber-200'}`}>
          <CardContent className="p-4 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${isDark ? 'bg-amber-600/20' : 'bg-amber-100'}`}>
              <PackageIcon className={`h-6 w-6 ${isDark ? 'text-amber-400' : 'text-amber-600'}`} />
            </div>
            <div>
              <p className={`text-sm ${isDark ? 'text-amber-300' : 'text-amber-600'}`}>{t('products_count')}</p>
              <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{stats?.products_count || 0}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-3">
        <Button
          onClick={() => navigate('/pos')}
          className="bg-blue-600 hover:bg-blue-700 text-white"
        >
          <Monitor className="h-4 w-4 mr-2" />
          {t('go_to_pos') || 'Open POS'}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/products')}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <ShoppingBag className="h-4 w-4 mr-2" />
          {t('manage_products') || 'Products'}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/reports')}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <BarChart3 className="h-4 w-4 mr-2" />
          {t('reports_analytics') || 'Reports'}
        </Button>
        <Button
          variant="outline"
          onClick={() => navigate('/staff')}
          className={isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}
        >
          <Users className="h-4 w-4 mr-2" />
          {t('staff') || 'Staff'}
        </Button>
      </div>

      {/* Subscription panel (CL-04) */}
      {subscription && (subscription.subscription_fee > 0 || subscription.payments.length > 0) && (
        <section>
          <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('subscription')}</h2>
          <Card className={isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}>
            <CardContent className="p-4 space-y-3">
              {/* Dunning notice (CL-06 / PRN-09): overdue amount + grace deadline + pay */}
              {(subscription.subscription_status === 'past_due' ||
                subscription.subscription_status === 'dunning' ||
                subscription.subscription_status === 'suspended') && (
                <div
                  role="alert"
                  className={`flex items-start gap-3 rounded-md border p-3 text-sm ${
                    subscription.subscription_status === 'suspended'
                      ? 'border-red-500/40 bg-red-500/10 text-red-300'
                      : 'border-amber-500/40 bg-amber-500/10 text-amber-300'
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
                  <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>{t('subscription_fee')}</p>
                  <p className={`text-xl font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>
                    {formatMoney(subscription.subscription_fee, language)} / {t(subscription.billing_cycle) || subscription.billing_cycle}
                  </p>
                </div>
                <div>
                  <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>{t('next_billing')}</p>
                  <p className={isDark ? 'text-slate-200' : 'text-slate-800'}>{subscription.next_billing_date || '—'}</p>
                </div>
                <div>
                  <Badge className={subscription.subscription_status === 'active' ? 'bg-green-600 text-white' : subscription.subscription_status === 'suspended' ? 'bg-red-600 text-white' : 'bg-amber-600 text-white'}>
                    {subscription.subscription_status}
                  </Badge>
                </div>
                <Button
                  onClick={handlePaySubscription}
                  disabled={paying || subscription.subscription_fee <= 0}
                  className="bg-green-600 hover:bg-green-700 text-white"
                >
                  {paying ? t('loading') : (t('pay_now') || 'Pay now')}
                </Button>
              </div>
              {subscription.payments.length > 0 && (
                <div className="border-t pt-3 border-slate-700/50">
                  <p className={`text-sm mb-2 ${isDark ? 'text-slate-400' : 'text-gray-500'}`}>{t('payment_history')}</p>
                  <div className="space-y-1">
                    {subscription.payments.slice(0, 6).map((p) => (
                      <div key={p.id} className={`flex items-center justify-between text-sm ${isDark ? 'text-slate-300' : 'text-gray-700'}`}>
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
        <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('recent_transactions')}</h2>
        <div className={`overflow-x-auto rounded-lg border ${isDark ? 'border-slate-700' : 'border-gray-200'}`}>
          <table className="w-full text-sm">
            <thead className={isDark ? 'bg-slate-800' : 'bg-gray-50'}>
              <tr className={isDark ? 'text-slate-400' : 'text-gray-500'}>
                <th className="p-3 text-start">{t('invoice_number')}</th>
                <th className="p-3 text-start">{t('total')}</th>
                <th className="p-3 text-start">{t('payment_method')}</th>
                <th className="p-3 text-start">{t('status')}</th>
              </tr>
            </thead>
            <tbody>
              {transactions.length === 0 ? (
                <tr>
                  <td colSpan={4} className={`p-6 text-center ${isDark ? 'text-slate-500' : 'text-gray-400'}`}>
                    {t('empty_cart')}
                  </td>
                </tr>
              ) : (
                transactions.map((tx) => (
                  <tr key={tx.id} className={`border-t ${isDark ? 'border-slate-700 text-slate-300' : 'border-gray-200 text-gray-700'}`}>
                    <td className="p-3 font-mono">{tx.invoice_number}</td>
                    <td className="p-3">{formatMoney(tx.total_amount || 0, language)}</td>
                    <td className="p-3">
                      <Badge className={isDark ? 'bg-slate-700 text-slate-300' : 'bg-gray-200 text-gray-700'}>{tx.payment_method}</Badge>
                    </td>
                    <td className="p-3">
                      <Badge className="bg-green-600 text-white">✓</Badge>
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