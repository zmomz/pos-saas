import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
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
import { formatMoney, formatDateTime } from '@/lib/format';
import { Globe, ShoppingCart, RefreshCw, Link2, CheckCircle2 } from 'lucide-react';

// Channel-order status → badge styling. The OMN order line is
// received → imported → fulfilled.
const STATUS_BADGE: Record<string, string> = {
  imported: 'pill-success',
  received: 'pill-warning',
  fulfilled: 'pill-success',
};

export default function ChannelOrders() {
  const { t, language } = useLanguage();

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

  const orderColumns: DataTableColumn<ChannelOrder>[] = [
    {
      key: 'order_number',
      header: t('order_number'),
      cell: (o) => (
        <span className="text-foreground">{o.external_reference || o.external_order_id}</span>
      ),
    },
    {
      key: 'provider',
      header: t('channel_provider'),
      cell: (o) => <span className="text-foreground/90">{o.provider}</span>,
    },
    {
      key: 'customer',
      header: t('customer'),
      cell: (o) => <span className="text-foreground/90">{o.customer_name || '—'}</span>,
    },
    {
      key: 'total',
      header: t('total'),
      cell: (o) => (
        <span className="text-foreground/90 tabular-nums">
          {o.total_amount != null ? formatMoney(o.total_amount, language) : '—'}
        </span>
      ),
    },
    {
      key: 'status',
      header: t('status'),
      cell: (o) => (
        <Badge className={STATUS_BADGE[o.status] || 'pill-muted'}>
          {t(`channel_status_${o.status}`)}
        </Badge>
      ),
    },
    {
      key: 'invoice_number',
      header: t('invoice_number'),
      cell: (o) => <span className="text-muted-foreground">{o.transaction_id ?? '—'}</span>,
    },
    {
      key: 'date',
      header: t('date'),
      cell: (o) => (
        <span className="text-muted-foreground tabular-nums">
          {o.created_at ? formatDateTime(o.created_at, language) : '—'}
        </span>
      ),
    },
  ];

  // ---- Loading state ----
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-foreground animate-pulse">{t('loading')}</div>
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
    <div className="animate-fade-up space-y-6">
      {/* Header */}
      <PageHeading
        title={t('online_orders')}
        subtitle={t('online_orders_desc')}
        icon={
          <span className="dxr-sw dxr-sw-brand h-10 w-10">
            <Globe className="h-[18px] w-[18px]" />
          </span>
        }
      >
        <Button
          variant="outline"
          onClick={load}
          className="border-input text-foreground/90 hover:bg-muted"
        >
          <RefreshCw className="h-4 w-4 me-2" /> {t('refresh')}
        </Button>
      </PageHeading>

      {/* Salla connection (OMN-01) */}
      <Card className="bg-card border-border">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2 text-foreground font-semibold">
            <Link2 className="h-5 w-5 text-brand-400" />
            {t('salla_connection')}
            {connection?.connected && (
              <Badge className="pill-success">
                <CheckCircle2 className="h-3.5 w-3.5 me-1" /> {t('salla_connected_badge')}
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground text-sm">{t('salla_connection_hint')}</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              dir="ltr"
              value={storeId}
              onChange={(e) => setStoreId(e.target.value)}
              placeholder={t('salla_store_id')}
              className="bg-background border-input text-foreground"
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
              className="bg-background border-input text-foreground"
            />
            <Button
              onClick={handleConnect}
              disabled={saving || !storeId.trim()}
              className="shrink-0"
            >
              {saving ? t('loading') : t('connect')}
            </Button>
          </div>
          {connectMsg && (
            <p className="text-sm text-foreground/90" role="status">
              {connectMsg}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Delivery-aggregator connection (F-060) */}
      <Card className="bg-card border-border">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2 text-foreground font-semibold">
            <Link2 className="h-5 w-5 text-warning" />
            {t('aggregator_connection')}
            {aggregator?.connected && (
              <Badge className="pill-success">
                <CheckCircle2 className="h-3.5 w-3.5 me-1" /> {t('aggregator_connected_badge')}
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground text-sm">{t('aggregator_connection_hint')}</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              dir="ltr"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              placeholder={t('aggregator_location_id')}
              className="bg-background border-input text-foreground"
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
              className="bg-background border-input text-foreground"
            />
            <Button
              onClick={handleConnectAggregator}
              variant="warning"
              disabled={aggSaving || !locationId.trim()}
              className="shrink-0"
            >
              {aggSaving ? t('loading') : t('connect')}
            </Button>
          </div>
          {aggMsg && (
            <p className="text-sm text-foreground/90" role="status">
              {aggMsg}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Imported orders: empty state vs table */}
      {orders.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="p-10 text-center">
            <ShoppingCart className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-1">{t('no_channel_orders')}</h3>
            <p className="text-muted-foreground text-sm">{t('no_channel_orders_desc')}</p>
          </CardContent>
        </Card>
      ) : (
        <Card className="bg-card border-border">
          <CardContent className="p-0">
            <DataTable<ChannelOrder>
              className="text-sm"
              rowKey={(o) => o.id}
              rows={orders}
              columns={orderColumns}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
