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
  DialogTrigger,
} from '@/components/ui/dialog';
import { client } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import ErrorState from '@/components/states/ErrorState';
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
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedWebhook, setSelectedWebhook] = useState<WebhookItem | null>(null);
  const [formData, setFormData] = useState<WebhookFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'webhooks' | 'logs'>('webhooks');
  const [copied, setCopied] = useState(false);

  const { t } = useLanguage();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const whRes = await client.entities.webhooks.query({ query: {}, limit: 100 });
      const whData = whRes.data;
      setWebhooks(Array.isArray(whData?.items) ? whData.items : Array.isArray(whData) ? whData : []);
    } catch {
      setWebhooks([]);
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
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Name *</label>
          <Input value={formData.name} onChange={(e) => setFormData((f) => ({ ...f, name: e.target.value }))} placeholder="My Webhook" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Endpoint URL *</label>
          <Input value={formData.url} onChange={(e) => setFormData((f) => ({ ...f, url: e.target.value }))} placeholder="https://example.com/webhook" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Secret Key</label>
          <div className="flex gap-2">
            <Input value={formData.secret_key} onChange={(e) => setFormData((f) => ({ ...f, secret_key: e.target.value }))} placeholder="Auto-generated if empty" className="bg-slate-700 border-slate-600 text-white flex-1" />
            <Button type="button" variant="outline" onClick={() => setFormData((f) => ({ ...f, secret_key: generateSecret() }))} className="border-slate-600 text-slate-300 hover:bg-slate-700">Generate</Button>
          </div>
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-2 block">Events *</label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {AVAILABLE_EVENTS.map((event) => (
              <label key={event} className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer hover:text-white">
                <input
                  type="checkbox"
                  checked={formData.events.includes(event)}
                  onChange={() => toggleEvent(event)}
                  className="rounded border-slate-600 bg-slate-700"
                />
                {event}
              </label>
            ))}
          </div>
        </div>
        <Button onClick={onSubmit} disabled={submitting || !formData.name || !formData.url || formData.events.length === 0} className="w-full bg-brand-600 hover:bg-brand-700 text-white">
          {submitting ? t('loading') : submitLabel}
        </Button>
      </div>
    );
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
            <Webhook className="h-8 w-8 text-brand-400" />
            <div>
              <p className="text-slate-400 text-sm">Total Webhooks</p>
              <p className="text-2xl font-bold text-white">{webhooks.length}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <CheckCircle className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-slate-400 text-sm">Active</p>
              <p className="text-2xl font-bold text-green-400">{webhooks.filter((w) => w.is_active).length}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <Play className="h-8 w-8 text-purple-400" />
            <div>
              <p className="text-slate-400 text-sm">Deliveries Today</p>
              <p className="text-2xl font-bold text-purple-400">
                {deliveryLogs.filter((l) => {
                  const d = new Date(l.created_at);
                  const now = new Date();
                  return d.toDateString() === now.toDateString();
                }).length}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        <Button variant={activeTab === 'webhooks' ? 'default' : 'outline'} onClick={() => setActiveTab('webhooks')} className={activeTab === 'webhooks' ? 'bg-brand-600 text-white' : 'border-slate-600 text-slate-300'}>
          Webhooks
        </Button>
        <Button variant={activeTab === 'logs' ? 'default' : 'outline'} onClick={() => setActiveTab('logs')} className={activeTab === 'logs' ? 'bg-brand-600 text-white' : 'border-slate-600 text-slate-300'}>
          Delivery Logs
        </Button>
      </div>

      {activeTab === 'webhooks' && (
        <>
          <div className="flex justify-end">
            <Dialog open={addOpen} onOpenChange={setAddOpen}>
              <DialogTrigger asChild>
                <Button onClick={() => setFormData({ ...emptyForm, secret_key: generateSecret() })} className="bg-brand-600 hover:bg-brand-700 text-white">
                  <Plus className="h-4 w-4 mr-2" /> Add Webhook
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="text-white">Add Webhook</DialogTitle>
                </DialogHeader>
                {renderForm(handleAddWebhook, 'Create Webhook')}
              </DialogContent>
            </Dialog>
          </div>

          <div className="space-y-3">
            {webhooks.length === 0 ? (
              <Card className="bg-slate-800 border-slate-700">
                <CardContent className="p-8 text-center">
                  <Webhook className="h-12 w-12 text-slate-600 mx-auto mb-3" />
                  <p className="text-slate-400">No webhooks configured yet</p>
                </CardContent>
              </Card>
            ) : (
              webhooks.map((webhook) => {
                let events: string[] = [];
                try {
                  events = typeof webhook.events === 'string' ? JSON.parse(webhook.events) : webhook.events;
                } catch {
                  events = [];
                }
                return (
                  <Card key={webhook.id} className="bg-slate-800 border-slate-700">
                    <CardContent className="p-4">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <h3 className="text-white font-medium">{webhook.name}</h3>
                            <Badge className={webhook.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}>
                              {webhook.is_active ? 'Active' : 'Inactive'}
                            </Badge>
                          </div>
                          <p className="text-slate-400 text-sm font-mono">{webhook.url}</p>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {events.map((ev) => (
                              <Badge key={ev} className="bg-slate-700 text-slate-300 text-xs">{ev}</Badge>
                            ))}
                          </div>
                          {webhook.secret_key && (
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-xs text-slate-500 font-mono">Secret: {webhook.secret_key.slice(0, 12)}...</span>
                              <button onClick={() => copySecret(webhook.secret_key!)} className="text-slate-400 hover:text-white">
                                {copied ? <CheckCircle className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
                              </button>
                            </div>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => handleTestWebhook(webhook)} disabled={testing === webhook.id} className="border-green-600/50 text-green-400 hover:bg-green-600/20 text-xs">
                            <Play className="h-3 w-3 mr-1" /> {testing === webhook.id ? 'Sent!' : 'Test'}
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => openEdit(webhook)} className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs">
                            <Edit className="h-3 w-3 mr-1" /> Edit
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => { setSelectedWebhook(webhook); setDeleteOpen(true); }} className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs">
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
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
        <div className="overflow-x-auto rounded-lg border border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-800">
              <tr className="text-slate-400">
                <th className="p-3 text-start">Time</th>
                <th className="p-3 text-start">Webhook</th>
                <th className="p-3 text-start">Event</th>
                <th className="p-3 text-start">Status</th>
                <th className="p-3 text-start">Response Time</th>
              </tr>
            </thead>
            <tbody>
              {deliveryLogs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-slate-500">No delivery logs</td>
                </tr>
              ) : (
                deliveryLogs.map((log) => (
                  <tr key={log.id} className="border-t border-slate-700 text-slate-300">
                    <td className="p-3">{new Date(log.created_at).toLocaleString()}</td>
                    <td className="p-3 text-white">{log.webhook_name || '—'}</td>
                    <td className="p-3"><Badge className="bg-slate-700 text-slate-300 text-xs">{log.event}</Badge></td>
                    <td className="p-3">
                      <Badge className={log.success ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}>
                        {log.status_code || (log.success ? '200' : 'Failed')}
                      </Badge>
                    </td>
                    <td className="p-3">{log.response_time_ms ? `${log.response_time_ms}ms` : '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-white">Edit Webhook</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditWebhook, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Delete Webhook</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">Are you sure you want to delete <strong>{selectedWebhook?.name}</strong>?</p>
          <div className="flex gap-3 pt-4">
            <Button variant="outline" onClick={() => setDeleteOpen(false)} className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700">{t('cancel')}</Button>
            <Button onClick={handleDeleteWebhook} disabled={submitting} className="flex-1 bg-red-600 hover:bg-red-700 text-white">
              {submitting ? t('loading') : 'Delete'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}