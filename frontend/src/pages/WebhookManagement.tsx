import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { client } from '@/lib/api';
import { toast } from 'sonner';
import { useLanguage } from '@/lib/i18n';
import { formatDateTime } from '@/lib/format';
import ErrorState from '@/components/states/ErrorState';
import EmptyState from '@/components/states/EmptyState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
import StatTile from '@/components/dashboard/StatTile';
import { Webhook, Plus, Play, Trash2, Edit, Copy, CheckCircle } from 'lucide-react';

interface WebhookItem {
  id: string;
  name: string;
  url: string;
  events: string[];
  secret_key?: string;
  is_active: boolean;
  last_triggered?: string;
  last_status?: string;
  created_at?: string;
}

interface DeliveryLog {
  id: string;
  webhook_id: string;
  webhook_name?: string;
  event: string;
  status_code?: number;
  response_time_ms?: number;
  success: boolean;
  created_at: string;
}

interface WebhookFormData {
  name: string;
  url: string;
  events: string[];
  secret_key: string;
}

const AVAILABLE_EVENTS = [
  'sale.completed',
  'sale.refunded',
  'product.created',
  'product.updated',
  'product.low_stock',
  'customer.created',
  'shift.opened',
  'shift.closed',
  'inventory.updated',
];

const emptyForm: WebhookFormData = {
  name: '',
  url: '',
  events: [],
  secret_key: '',
};

function generateSecret(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = 'whsec_';
  for (let i = 0; i < 32; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

export default function WebhookManagement() {
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [deliveryLogs, setDeliveryLogs] = useState<DeliveryLog[]>([]);
  const [logsError, setLogsError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedWebhook, setSelectedWebhook] = useState<WebhookItem | null>(null);
  const [formData, setFormData] = useState<WebhookFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'webhooks' | 'logs'>('webhooks');
  const [copied, setCopied] = useState(false);

  const { t, isRTL, language } = useLanguage();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const whRes = await client.entities.webhooks.query({ query: {}, limit: 100 });
      const whData = whRes.data;
      setWebhooks(Array.isArray(whData?.items) ? whData.items : Array.isArray(whData) ? whData : []);
    } catch (err: unknown) {
      console.error('Failed to load webhooks:', err);
      setWebhooks([]);
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 403 means the account lacks access to webhooks; show the in-page
      // permission state rather than a misleading empty list (UX-02).
      if (status === 403) {
        setDenied(true);
      } else {
        // A real fetch failure must not masquerade as "no webhooks" (UX-02).
        setError(true);
      }
      setLoading(false);
      return;
    }
    // ISSUE-020 (H24 / U5.1): the delivery-logs fetch used to swallow its 404 and
    // fall through to an empty list, so a missing endpoint looked identical to an
    // empty log. Surface the failure (logsError) so the tab renders a real error.
    setLogsError(false);
    try {
      const logRes = await client.apiCall.invoke({
        url: '/api/v1/production/webhooks/logs',
        method: 'GET',
        data: { limit: 50 },
      });
      const lData = logRes.data;
      setDeliveryLogs(Array.isArray(lData?.items) ? lData.items : Array.isArray(lData) ? lData : []);
    } catch (err) {
      console.error('Failed to load webhook delivery logs:', err);
      setDeliveryLogs([]);
      setLogsError(true);
    }
    setLoading(false);
  }

  function toggleEvent(event: string) {
    setFormData((prev) => ({
      ...prev,
      events: prev.events.includes(event) ? prev.events.filter((e) => e !== event) : [...prev.events, event],
    }));
  }

  async function handleAddWebhook() {
    setSubmitting(true);
    try {
      await client.entities.webhooks.create({
        data: {
          name: formData.name,
          url: formData.url,
          events: JSON.stringify(formData.events),
          secret_key: formData.secret_key || generateSecret(),
          is_active: true,
        },
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadData();
    } catch (err) {
      console.error('Failed to create webhook:', err);
      toast.error(t('action_failed'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEditWebhook() {
    if (!selectedWebhook) return;
    setSubmitting(true);
    try {
      await client.entities.webhooks.update({
        id: selectedWebhook.id,
        data: {
          name: formData.name,
          url: formData.url,
          events: JSON.stringify(formData.events),
          secret_key: formData.secret_key,
        },
      });
      setEditOpen(false);
      setSelectedWebhook(null);
      setFormData(emptyForm);
      await loadData();
    } catch (err) {
      console.error('Failed to update webhook:', err);
      toast.error(t('action_failed'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeleteWebhook() {
    if (!selectedWebhook) return;
    setSubmitting(true);
    try {
      await client.entities.webhooks.delete({ id: selectedWebhook.id });
      setDeleteOpen(false);
      setSelectedWebhook(null);
      await loadData();
    } catch (err) {
      console.error('Failed to delete webhook:', err);
      toast.error(t('action_failed'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTestWebhook(webhook: WebhookItem) {
    setTesting(webhook.id);
    try {
      await client.apiCall.invoke({
        url: '/api/v1/production/webhooks/test',
        method: 'POST',
        data: { webhook_id: webhook.id },
      });
    } catch (err) {
      console.error('Test failed:', err);
      toast.error(t('action_failed'));
    } finally {
      setTimeout(() => setTesting(null), 2000);
    }
  }

  function openEdit(webhook: WebhookItem) {
    setSelectedWebhook(webhook);
    let events: string[] = [];
    try {
      events = typeof webhook.events === 'string' ? JSON.parse(webhook.events) : webhook.events;
    } catch {
      events = [];
    }
    setFormData({
      name: webhook.name,
      url: webhook.url,
      events,
      secret_key: webhook.secret_key || '',
    });
    setEditOpen(true);
  }

  function copySecret(secret: string) {
    navigator.clipboard.writeText(secret);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label className="text-muted-foreground">{t('webhook_name_label')}</Label>
          <Input value={formData.name} onChange={(e) => setFormData((f) => ({ ...f, name: e.target.value }))} placeholder={t('webhook_name_placeholder')} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-muted-foreground">{t('webhook_url_label')}</Label>
          <Input value={formData.url} dir="ltr" onChange={(e) => setFormData((f) => ({ ...f, url: e.target.value }))} placeholder={t('webhook_url_placeholder')} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-muted-foreground">{t('webhook_secret_label')}</Label>
          <div className="flex gap-2">
            <Input value={formData.secret_key} dir="ltr" onChange={(e) => setFormData((f) => ({ ...f, secret_key: e.target.value }))} placeholder={t('webhook_secret_placeholder')} className="flex-1" />
            <Button type="button" variant="outline" onClick={() => setFormData((f) => ({ ...f, secret_key: generateSecret() }))}>{t('webhook_generate')}</Button>
          </div>
        </div>
        <div className="space-y-2">
          <Label className="text-muted-foreground">{t('webhook_events_label')}</Label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {AVAILABLE_EVENTS.map((event) => (
              <Label key={event} className="flex items-center gap-2 text-sm cursor-pointer">
                <Checkbox
                  checked={formData.events.includes(event)}
                  onCheckedChange={() => toggleEvent(event)}
                />
                {event}
              </Label>
            ))}
          </div>
        </div>
        <Button onClick={onSubmit} disabled={submitting || !formData.name || !formData.url || formData.events.length === 0} className="w-full shadow-brand">
          {submitting ? t('loading') : submitLabel}
        </Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64" dir={isRTL ? 'rtl' : 'ltr'}>
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  if (denied) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'}>
        <PermissionDenied />
      </div>
    );
  }

  if (error) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'}>
        <ErrorState onRetry={loadData} />
      </div>
    );
  }

  const logColumns: DataTableColumn<DeliveryLog>[] = [
    {
      header: t('webhook_col_time'),
      cell: (log) => (
        <span className="whitespace-nowrap text-xs tabular-nums" dir="ltr">{formatDateTime(log.created_at, language)}</span>
      ),
    },
    {
      header: t('webhook_col_webhook'),
      cell: (log) => <span className="text-foreground">{log.webhook_name || '—'}</span>,
    },
    {
      header: t('webhook_col_event'),
      cell: (log) => <Badge variant="secondary" className="text-xs">{log.event}</Badge>,
    },
    {
      header: t('status'),
      cell: (log) => (
        <span className={log.success ? 'pill-success' : 'pill-danger'}>
          {log.status_code || (log.success ? '200' : 'Failed')}
        </span>
      ),
    },
    {
      header: t('webhook_col_response'),
      cell: (log) => (
        <span className="text-muted-foreground">{log.response_time_ms ? `${log.response_time_ms}ms` : '—'}</span>
      ),
    },
  ];

  return (
    <div className="animate-fade-up space-y-6" dir={isRTL ? 'rtl' : 'ltr'}>
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Webhook className="h-[18px] w-[18px]" /></span>}
        title={t('webhook_tab_webhooks')}
        subtitle={`${webhooks.length} ${t('configured') || 'configured'}`}
      >
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button onClick={() => setFormData({ ...emptyForm, secret_key: generateSecret() })} className="h-11 rounded-[10px] shadow-brand">
              <Plus className="h-4 w-4 me-2" /> {t('webhook_add')}
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('webhook_add')}</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddWebhook, t('webhook_create'))}
          </DialogContent>
        </Dialog>
      </PageHeading>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatTile icon={Webhook} tone="brand" label={t('webhook_total')} value={webhooks.length} />
        <StatTile icon={CheckCircle} tone="success" label={t('active')} value={webhooks.filter((w) => w.is_active).length} />
        <StatTile
          icon={Play}
          tone="violet"
          label={t('webhook_deliveries_today')}
          value={deliveryLogs.filter((l) => {
            const d = new Date(l.created_at);
            const now = new Date();
            return d.toDateString() === now.toDateString();
          }).length}
        />
      </div>

      {/* Tabs */}
      <div className="dxr-seg">
        <button data-active={activeTab === 'webhooks'} onClick={() => setActiveTab('webhooks')}>
          {t('webhook_tab_webhooks')}
        </button>
        <button data-active={activeTab === 'logs'} onClick={() => setActiveTab('logs')}>
          {t('webhook_tab_logs')}
        </button>
      </div>

      {activeTab === 'webhooks' && (
        <>
          <div className="space-y-3">
            {webhooks.length === 0 ? (
              <EmptyState icon={Webhook} message={t('webhook_none')} />
            ) : (
              webhooks.map((webhook) => {
                let events: string[] = [];
                try {
                  events = typeof webhook.events === 'string' ? JSON.parse(webhook.events) : webhook.events;
                } catch {
                  events = [];
                }
                return (
                  <div key={webhook.id} className="dxr-tile">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <h3 className="text-foreground font-medium">{webhook.name}</h3>
                          <span className={webhook.is_active ? 'pill-success' : 'pill-danger'}>
                            {webhook.is_active ? t('active') : t('inactive')}
                          </span>
                        </div>
                        <p className="text-muted-foreground text-sm font-mono" dir="ltr">{webhook.url}</p>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {events.map((ev) => (
                            <Badge key={ev} variant="secondary" className="text-xs">{ev}</Badge>
                          ))}
                        </div>
                        {webhook.secret_key && (
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-xs text-muted-foreground font-mono" dir="ltr">{t('webhook_secret_prefix')} {webhook.secret_key.slice(0, 12)}...</span>
                            <button onClick={() => copySecret(webhook.secret_key!)} className="text-muted-foreground hover:text-foreground">
                              {copied ? <CheckCircle className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
                            </button>
                          </div>
                        )}
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" onClick={() => handleTestWebhook(webhook)} disabled={testing === webhook.id} className="text-xs text-success">
                          <Play className="h-3 w-3 me-1" /> {testing === webhook.id ? t('webhook_test_sent') : t('webhook_test')}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => openEdit(webhook)} className="text-xs">
                          <Edit className="h-3 w-3 me-1" /> {t('edit')}
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => { setSelectedWebhook(webhook); setDeleteOpen(true); }} className="text-xs">
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </>
      )}

      {activeTab === 'logs' && logsError && (
        <ErrorState message={t('webhook_logs_load_error')} onRetry={loadData} />
      )}

      {activeTab === 'logs' && !logsError && (
        <DataTable
          columns={logColumns}
          rows={deliveryLogs}
          rowKey={(l) => l.id}
          empty={<span className="text-muted-foreground">{t('webhook_logs_none')}</span>}
          className="rounded-lg border border-border"
        />
      )}

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('webhook_edit')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditWebhook, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('webhook_delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground">{t('webhook_delete_confirm')} <strong className="text-foreground">{selectedWebhook?.name}</strong>?</p>
          <div className="flex gap-3 pt-4">
            <Button variant="outline" onClick={() => setDeleteOpen(false)} className="flex-1">{t('cancel')}</Button>
            <Button variant="destructive" onClick={handleDeleteWebhook} disabled={submitting} className="flex-1">
              {submitting ? t('loading') : t('delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}