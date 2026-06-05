import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import {
  getSallaConnection,
  connectSalla,
  getAggregatorConnection,
  connectAggregator,
  getChannelOrders,
  type SallaConnection,
  type AggregatorConnection,
  type ChannelOrder,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Globe, ShoppingCart, RefreshCw, Link2, CheckCircle2 } from 'lucide-react';

// Channel-order status → badge styling. The OMN order line is
// received → imported → fulfilled.
const STATUS_BADGE: Record<string, string> = {
  imported: 'bg-green-500/20 text-green-400',
  received: 'bg-amber-500/20 text-amber-400',
  fulfilled: 'bg-emerald-500/20 text-emerald-400',
};

export default function ChannelOrders() {
  const { t } = useLanguage();

  const [connection, setConnection] = useState<SallaConnection | null>(null);
  const [orders, setOrders] = useState<ChannelOrder[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);

  const [storeId, setStoreId] = useState('');
  const [webhookSecret, setWebhookSecret] = useState('');
  const [saving, setSaving] = useState(false);
  const [connectMsg, setConnectMsg] = useState<string | null>(null);

  // Aggregator (Deliverect-class) middleware connection (F-060).
  const [aggregator, setAggregator] = useState<AggregatorConnection | null>(null);
  const [locationId, setLocationId] = useState('');
  const [aggSecret, setAggSecret] = useState('');
  const [aggSaving, setAggSaving] = useState(false);
  const [aggMsg, setAggMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const [conn, agg, list] = await Promise.all([
        getSallaConnection(),
        getAggregatorConnection(),
        getChannelOrders(),
      ]);
      setConnection(conn);
      setStoreId(conn.store_id || '');
      setAggregator(agg);
      setLocationId(agg.location_id || '');
      setOrders(Array.isArray(list.items) ? list.items : []);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 403 means the account is not a client tenancy (omnichannel is client-scoped).
      if (status === 403) {
        setDenied(true);
      } else {
        // A real fetch failure must not masquerade as "no orders" (UX-02).
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleConnect() {
    if (!storeId.trim()) return;
    setSaving(true);
    setConnectMsg(null);
    try {
      const conn = await connectSalla(storeId.trim(), webhookSecret.trim() || undefined);
      setConnection(conn);
      setWebhookSecret('');
      setConnectMsg(t('salla_connected'));
      await load();
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        setConnectMsg(t('salla_store_in_use'));
      } else {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setConnectMsg(detail || t('salla_connect_failed'));
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleConnectAggregator() {
    if (!locationId.trim()) return;
    setAggSaving(true);
    setAggMsg(null);
    try {
      const conn = await connectAggregator(locationId.trim(), aggSecret.trim() || undefined);
      setAggregator(conn);
      setAggSecret('');
      setAggMsg(t('aggregator_connected'));
      await load();
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        setAggMsg(t('aggregator_location_in_use'));
      } else {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setAggMsg(detail || t('aggregator_connect_failed'));
      }
    } finally {
      setAggSaving(false);
    }
  }

  // ---- Loading state ----
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // ---- Permission-denied state (not a client tenancy) ----
  if (denied) {
    return <PermissionDenied />;
  }

  // ---- Error state (distinct from empty) ----
  if (error) {
    return <ErrorState message={t('channel_orders_load_error')} onRetry={load} />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Globe className="h-6 w-6 text-blue-400" />
            {t('online_orders')}
          </h2>
          <p className="text-slate-400 text-sm mt-1">{t('online_orders_desc')}</p>
        </div>
        <Button
          variant="outline"
          onClick={load}
          className="border-slate-600 text-slate-300 hover:bg-slate-700"
        >
          <RefreshCw className="h-4 w-4 mr-2" /> {t('refresh')}
        </Button>
      </div>

      {/* Salla connection (OMN-01) */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2 text-white font-semibold">
            <Link2 className="h-5 w-5 text-blue-400" />
            {t('salla_connection')}
            {connection?.connected && (
              <Badge className="bg-green-500/20 text-green-400">
                <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> {t('salla_connected_badge')}
              </Badge>
            )}
          </div>
          <p className="text-slate-400 text-sm">{t('salla_connection_hint')}</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              dir="ltr"
              value={storeId}
              onChange={(e) => setStoreId(e.target.value)}
              placeholder={t('salla_store_id')}
              className="bg-slate-900 border-slate-600 text-white"
            />
            <Input
              dir="ltr"
              type="password"
              value={webhookSecret}
              onChange={(e) => setWebhookSecret(e.target.value)}
              placeholder={
                connection?.webhook_secret_set
                  ? t('salla_webhook_secret_set')
                  : t('salla_webhook_secret')
              }
              className="bg-slate-900 border-slate-600 text-white"
            />
            <Button
              onClick={handleConnect}
              disabled={saving || !storeId.trim()}
              className="bg-blue-600 hover:bg-blue-700 text-white shrink-0"
            >
              {saving ? t('loading') : t('connect')}
            </Button>
          </div>
          {connectMsg && (
            <p className="text-sm text-slate-300" role="status">
              {connectMsg}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Delivery-aggregator connection (F-060) */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2 text-white font-semibold">
            <Link2 className="h-5 w-5 text-orange-400" />
            {t('aggregator_connection')}
            {aggregator?.connected && (
              <Badge className="bg-green-500/20 text-green-400">
                <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> {t('aggregator_connected_badge')}
              </Badge>
            )}
          </div>
          <p className="text-slate-400 text-sm">{t('aggregator_connection_hint')}</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              dir="ltr"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              placeholder={t('aggregator_location_id')}
              className="bg-slate-900 border-slate-600 text-white"
            />
            <Input
              dir="ltr"
              type="password"
              value={aggSecret}
              onChange={(e) => setAggSecret(e.target.value)}
              placeholder={
                aggregator?.webhook_secret_set
                  ? t('salla_webhook_secret_set')
                  : t('salla_webhook_secret')
              }
              className="bg-slate-900 border-slate-600 text-white"
            />
            <Button
              onClick={handleConnectAggregator}
              disabled={aggSaving || !locationId.trim()}
              className="bg-orange-600 hover:bg-orange-700 text-white shrink-0"
            >
              {aggSaving ? t('loading') : t('connect')}
            </Button>
          </div>
          {aggMsg && (
            <p className="text-sm text-slate-300" role="status">
              {aggMsg}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Imported orders: empty state vs table */}
      {orders.length === 0 ? (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-10 text-center">
            <ShoppingCart className="h-12 w-12 text-slate-600 mx-auto mb-3" />
            <h3 className="text-white font-semibold mb-1">{t('no_channel_orders')}</h3>
            <p className="text-slate-400 text-sm">{t('no_channel_orders_desc')}</p>
          </CardContent>
        </Card>
      ) : (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400">
                  <th className="text-start p-3">{t('order_number')}</th>
                  <th className="text-start p-3">{t('channel_provider')}</th>
                  <th className="text-start p-3">{t('customer')}</th>
                  <th className="text-start p-3">{t('total')}</th>
                  <th className="text-start p-3">{t('status')}</th>
                  <th className="text-start p-3">{t('invoice_number')}</th>
                  <th className="text-start p-3">{t('date')}</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id} className="border-b border-slate-700/50">
                    <td className="p-3 text-white">{o.external_reference || o.external_order_id}</td>
                    <td className="p-3 text-slate-300">{o.provider}</td>
                    <td className="p-3 text-slate-300">{o.customer_name || '—'}</td>
                    <td className="p-3 text-slate-300">
                      {o.total_amount != null ? `${o.total_amount} ${o.currency || ''}` : '—'}
                    </td>
                    <td className="p-3">
                      <Badge className={STATUS_BADGE[o.status] || 'bg-slate-500/20 text-slate-300'}>
                        {t(`channel_status_${o.status}`)}
                      </Badge>
                    </td>
                    <td className="p-3 text-slate-400">{o.transaction_id ?? '—'}</td>
                    <td className="p-3 text-slate-400">
                      {o.created_at ? new Date(o.created_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
