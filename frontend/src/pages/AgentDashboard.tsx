import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { getAgentClients, getAgentBranding, getAgentRevenue, getAgentCommissionStatements, createNewClient, toggleClient, setClientZatca, setClientFeature, getClientFeatures, resetClientPassword, runDunning, getQuotaStatus, payQuota, saveQuotaCard, saveAgentMoyasarKeys, archiveClient, restoreClient, transferClient, exportClientData, deleteClient, type AgentRevenue, type CommissionStatement, type QuotaStatus } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney, formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';
import { Avatar } from '@/components/dashboard/Avatar';
import { usePageChrome } from '@/contexts/PageChromeContext';
import CountUp from '@/components/dashboard/rx/CountUp';
import ErrorState from '@/components/states/ErrorState';
import Gauge from '@/components/dashboard/rx/Gauge';
import Bar from '@/components/dashboard/rx/Bar';
import CardOnFileDialog, { type CardOnFileToken } from '@/components/billing/CardOnFileDialog';
import AgentMoyasarBanner from '@/components/billing/AgentMoyasarBanner';
import { Users, CreditCard, UserPlus, Palette, ShoppingBag, BarChart3, Box, Percent, Star, QrCode, Mail, Sliders, KeyRound, Store, Wallet, Link2, Archive, ArchiveRestore, ArrowRightLeft, Download, Trash2, MoreVertical } from 'lucide-react';
import { readableTextColor } from '@/lib/contrast';

interface ClientItem {
  id: number;
  business_name: string;
  email: string;
  phone: string;
  is_active: boolean;
  subscription_fee: number;
  zatca_enabled: boolean;
  archived_at?: string | null;
}

interface Branding {
  company_name: string;
  logo_url: string;
  primary_color: string;
}

export default function AgentDashboard() {
  const [clients, setClients] = useState<ClientItem[]>([]);
  const [remainingSlots, setRemainingSlots] = useState(0);
  const [totalClients, setTotalClients] = useState(0);
  // M8 (issue-215): the archived book is loaded lazily and kept separate from the
  // live `clients` so the KPI tiles always reflect active merchants, never the
  // archived view.
  const [clientView, setClientView] = useState<'active' | 'archived'>('active');
  const [archivedClients, setArchivedClients] = useState<ClientItem[]>([]);
  const [archivedLoading, setArchivedLoading] = useState(false);
  const [lifecycleBusyId, setLifecycleBusyId] = useState<number | null>(null);
  const [transferTarget, setTransferTarget] = useState<ClientItem | null>(null);
  const [transferEmail, setTransferEmail] = useState('');
  const [transferBusy, setTransferBusy] = useState(false);
  const [archiveConfirm, setArchiveConfirm] = useState<ClientItem | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<ClientItem | null>(null);
  const [branding, setBranding] = useState<Branding | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newClientForm, setNewClientForm] = useState({ business_name: '', email: '', phone: '', subscription_fee: '', billing_cycle: 'monthly' });
  const [featureClient, setFeatureClient] = useState<ClientItem | null>(null);
  const [featureBusy, setFeatureBusy] = useState(false);
  const [panelClientId, setPanelClientId] = useState<number | null>(null);
  // Real per-client feature flags, keyed by client id. Hydrated from the backend
  // so the right-rail switches reflect actual state instead of assuming "all on".
  const [featureState, setFeatureState] = useState<Record<number, Record<string, boolean>>>({});
  const [featureLoadingId, setFeatureLoadingId] = useState<number | null>(null);
  const [featureLoadError, setFeatureLoadError] = useState<number | null>(null);
  const [createdCreds, setCreatedCreds] = useState<
    { email: string; temp_password: string; email_delivered: boolean; reset?: boolean } | null
  >(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [resettingId, setResettingId] = useState<number | null>(null);
  const [zatcaTogglingId, setZatcaTogglingId] = useState<number | null>(null);
  const [zatcaError, setZatcaError] = useState<string | null>(null);
  const [revenue, setRevenue] = useState<AgentRevenue | null>(null);
  const [revenueLoading, setRevenueLoading] = useState(true);
  const [revenueError, setRevenueError] = useState(false);
  const [statements, setStatements] = useState<CommissionStatement[]>([]);
  const [statementsLoading, setStatementsLoading] = useState(true);
  const [statementsError, setStatementsError] = useState(false);
  const [dunningBusy, setDunningBusy] = useState(false);
  const [dunningResult, setDunningResult] = useState<string | null>(null);
  // Rail 1: the agent's quota (what the agent pays the platform).
  const [quota, setQuota] = useState<QuotaStatus | null>(null);
  const [quotaLoading, setQuotaLoading] = useState(true);
  const [quotaError, setQuotaError] = useState(false);
  const [payingQuota, setPayingQuota] = useState(false);
  const [quotaCardOpen, setQuotaCardOpen] = useState(false);
  // Rail 2: connect the agent's own Moyasar account.
  const [moyasarForm, setMoyasarForm] = useState({ secret_key: '', publishable_key: '', webhook_secret: '' });
  const [savingMoyasar, setSavingMoyasar] = useState(false);
  const navigate = useNavigate();
  const { t, language } = useLanguage();

  useEffect(() => {
    loadData();
    loadRevenue();
    loadStatements();
    loadQuota();
  }, []);

  // M8: fetch the archived book the first time the agent opens that view.
  useEffect(() => {
    if (clientView === 'archived') loadArchived();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientView]);

  async function loadQuota() {
    setQuotaLoading(true);
    setQuotaError(false);
    try {
      setQuota(await getQuotaStatus());
    } catch (err) {
      console.error('Failed to load quota:', err);
      setQuotaError(true);
    } finally {
      setQuotaLoading(false);
    }
  }

  async function handleSaveQuotaCard(token: CardOnFileToken) {
    await saveQuotaCard({ token: token.token, last4: token.last4, brand: token.brand });
    await loadQuota();
  }

  async function handlePayQuota() {
    setPayingQuota(true);
    try {
      setQuota(await payQuota());
      toast.success(t('pay_renew_quota') || 'Quota paid');
    } catch (err) {
      console.error('Pay quota failed:', err);
      toast.error(err instanceof Error ? err.message : (t('error') || 'Payment failed'));
    } finally {
      setPayingQuota(false);
    }
  }

  async function handleSaveMoyasar(e: React.FormEvent) {
    e.preventDefault();
    setSavingMoyasar(true);
    try {
      const result = await saveAgentMoyasarKeys({
        secret_key: moyasarForm.secret_key,
        publishable_key: moyasarForm.publishable_key || undefined,
        webhook_secret: moyasarForm.webhook_secret || undefined,
      });
      if (result.valid) {
        toast.success(t('moyasar_saved_valid') || 'Moyasar account connected.');
      } else {
        toast.warning(result.detail || t('moyasar_saved_invalid') || 'Keys saved, but could not be verified.');
      }
      setMoyasarForm({ secret_key: '', publishable_key: '', webhook_secret: '' });
      await loadQuota();
    } catch (err) {
      console.error('Save Moyasar keys failed:', err);
      toast.error(err instanceof Error ? err.message : (t('moyasar_save_failed') || 'Could not save Moyasar keys.'));
    } finally {
      setSavingMoyasar(false);
    }
  }

  function mapClient(c: Awaited<ReturnType<typeof getAgentClients>>['items'][number]): ClientItem {
    return {
      id: c.id,
      business_name: c.business_name,
      email: c.email,
      phone: c.phone ?? '',
      is_active: c.is_active,
      subscription_fee: c.subscription_fee ?? 0,
      zatca_enabled: c.zatca_enabled,
      archived_at: c.archived_at ?? null,
    };
  }

  async function loadData() {
    setLoading(true);
    setLoadError(false);
    try {
      // The merchant book (slots/clients KPIs) is the hard dependency — a failure
      // here must surface honestly (H4) rather than render a fabricated all-zero
      // book. The branding chrome degrades on its own.
      const clientData = await getAgentClients();
      setClients((clientData?.items || []).map(mapClient));
      setRemainingSlots(clientData?.remaining_slots ?? 0);
      setTotalClients(clientData?.total ?? clientData?.items?.length ?? 0);
      setBranding(await getAgentBranding().catch(() => null));
    } catch (err) {
      console.error('Failed to load:', err);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  // M8: load the archived book on demand (and after a lifecycle action). Kept
  // separate from `clients` so KPI tiles never count archived merchants.
  async function loadArchived() {
    setArchivedLoading(true);
    try {
      const data = await getAgentClients(0, 50, true);
      setArchivedClients((data?.items || []).map(mapClient));
    } catch (err) {
      console.error('Failed to load archived:', err);
    } finally {
      setArchivedLoading(false);
    }
  }

  async function loadRevenue() {
    setRevenueLoading(true);
    setRevenueError(false);
    try {
      setRevenue(await getAgentRevenue());
    } catch (err) {
      console.error('Failed to load revenue:', err);
      setRevenueError(true);
    } finally {
      setRevenueLoading(false);
    }
  }

  async function loadStatements() {
    setStatementsLoading(true);
    setStatementsError(false);
    try {
      const data = await getAgentCommissionStatements();
      setStatements(data.statements || []);
    } catch (err) {
      console.error('Failed to load commission statements:', err);
      setStatementsError(true);
    } finally {
      setStatementsLoading(false);
    }
  }

  async function handleRunDunning() {
    setDunningBusy(true);
    setDunningResult(null);
    try {
      const result = await runDunning();
      setDunningResult(`${t('dunning_done')}: ${result.processed} · ${t('recovered')} ${result.recovered} · ${t('suspended')} ${result.suspended}`);
      await loadData();
    } catch (err) {
      console.error('Failed to run dunning:', err);
      setDunningResult(t('dunning_failed'));
    } finally {
      setDunningBusy(false);
    }
  }

  async function handleCreateClient() {
    setCreateError(null);
    try {
      const created = await createNewClient({
        business_name: newClientForm.business_name,
        email: newClientForm.email,
        phone: newClientForm.phone,
        subscription_fee: newClientForm.subscription_fee ? Number(newClientForm.subscription_fee) : undefined,
      });
      setDialogOpen(false);
      setNewClientForm({ business_name: '', email: '', phone: '', subscription_fee: '', billing_cycle: 'monthly' });
      if (created?.temp_password) {
        setCreatedCreds({ email: created.email, temp_password: created.temp_password, email_delivered: !!created.email_delivered });
      }
      loadData();
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setCreateError(detail || (err instanceof Error ? err.message : 'Create client failed'));
      console.error('Create client failed:', err);
    }
  }

  async function handleToggleClient(clientId: number) {
    setTogglingId(clientId);
    try {
      await toggleClient(clientId);
      setClients((prev) => prev.map((c) => (c.id === clientId ? { ...c, is_active: !c.is_active } : c)));
    } catch (err) {
      console.error('Toggle client failed:', err);
    } finally {
      setTogglingId(null);
    }
  }

  // M8 (issue-215): merchant lifecycle — archive / restore / transfer / export / delete.
  async function handleArchive(c: ClientItem) {
    setArchiveConfirm(null);
    setLifecycleBusyId(c.id);
    try {
      await archiveClient(c.id);
      toast.success(t('archive_merchant') || 'Merchant archived');
      await Promise.all([loadData(), loadArchived()]);
    } catch (err) {
      console.error('Archive client failed:', err);
      toast.error(t('archive_failed') || 'Could not archive the merchant.');
    } finally {
      setLifecycleBusyId(null);
    }
  }

  async function handleRestore(c: ClientItem) {
    setLifecycleBusyId(c.id);
    try {
      await restoreClient(c.id);
      toast.success(t('restore_merchant') || 'Merchant restored');
      await Promise.all([loadData(), loadArchived()]);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      console.error('Restore client failed:', err);
      toast.error(detail || t('restore_failed') || 'Could not restore the merchant.');
    } finally {
      setLifecycleBusyId(null);
    }
  }

  async function handleTransfer() {
    if (!transferTarget) return;
    const email = transferEmail.trim();
    if (!email) return;
    setTransferBusy(true);
    try {
      await transferClient(transferTarget.id, email);
      toast.success(t('transfer_merchant') || 'Merchant transferred');
      setTransferTarget(null);
      setTransferEmail('');
      await Promise.all([loadData(), clientView === 'archived' ? loadArchived() : Promise.resolve()]);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      console.error('Transfer client failed:', err);
      toast.error(detail || t('merchant_transfer_failed') || 'Could not transfer the merchant.');
    } finally {
      setTransferBusy(false);
    }
  }

  async function handleExport(c: ClientItem) {
    setLifecycleBusyId(c.id);
    try {
      const data = await exportClientData(c.id);
      // Trigger a client-side download of the JSON snapshot.
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `merchant-${c.id}-export.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(t('export_merchant') || 'Export downloaded');
    } catch (err) {
      console.error('Export client failed:', err);
      toast.error(t('merchant_export_failed') || 'Could not export the merchant.');
    } finally {
      setLifecycleBusyId(null);
    }
  }

  async function handleDelete(c: ClientItem) {
    setDeleteConfirm(null);
    setLifecycleBusyId(c.id);
    try {
      await deleteClient(c.id);
      toast.success(t('delete_merchant') || 'Merchant deleted');
      await Promise.all([loadData(), loadArchived()]);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      console.error('Delete client failed:', err);
      toast.error(detail || t('delete_failed') || 'Could not delete the merchant.');
    } finally {
      setLifecycleBusyId(null);
    }
  }

  async function handleResetPassword(clientId: number) {
    setResettingId(clientId);
    try {
      const result = await resetClientPassword(clientId);
      setCreatedCreds({ email: result.email, temp_password: result.temp_password, email_delivered: !!result.email_delivered, reset: true });
    } catch (err) {
      console.error('Reset client password failed:', err);
    } finally {
      setResettingId(null);
    }
  }

  async function handleToggleZatca(clientId: number) {
    setZatcaTogglingId(clientId);
    setZatcaError(null);
    try {
      const result = await setClientZatca(clientId);
      setClients((prev) => prev.map((c) => (c.id === clientId ? { ...c, zatca_enabled: result.zatca_enabled } : c)));
    } catch (err) {
      console.error('Toggle ZATCA failed:', err);
      setZatcaError(t('zatca_toggle_failed') || 'Could not change ZATCA status. Please try again.');
    } finally {
      setZatcaTogglingId(null);
    }
  }

  async function loadClientFeatures(clientId: number) {
    setFeatureLoadingId(clientId);
    setFeatureLoadError((prev) => (prev === clientId ? null : prev));
    try {
      const data = await getClientFeatures(clientId);
      setFeatureState((prev) => ({ ...prev, [clientId]: data.features }));
    } catch (err) {
      console.error('Failed to load client features:', err);
      setFeatureLoadError(clientId);
    } finally {
      setFeatureLoadingId((prev) => (prev === clientId ? null : prev));
    }
  }

  async function handleSetFeature(featureName: string, isEnabled: boolean) {
    if (!featureClient) return;
    const clientId = featureClient.id;
    setFeatureBusy(true);
    try {
      await setClientFeature(clientId, featureName, isEnabled);
      // Keep the right-rail panel in sync if this client's flags are cached.
      setFeatureState((prev) =>
        prev[clientId] ? { ...prev, [clientId]: { ...prev[clientId], [featureName]: isEnabled } } : prev
      );
    } catch (err) {
      console.error('Set feature failed:', err);
      toast.error(t('feature_toggle_failed') || 'Could not change the feature. Please try again.');
    } finally {
      setFeatureBusy(false);
    }
  }

  async function handleToggleFeatureInline(client: ClientItem, featureName: string, next: boolean) {
    setFeatureState((prev) => ({ ...prev, [client.id]: { ...prev[client.id], [featureName]: next } }));
    try {
      await setClientFeature(client.id, featureName, next);
    } catch (err) {
      console.error('Set feature failed:', err);
      setFeatureState((prev) => ({ ...prev, [client.id]: { ...prev[client.id], [featureName]: !next } }));
      toast.error(t('feature_toggle_failed') || 'Could not change the feature. Please try again.');
    }
  }

  const TOGGLEABLE_FEATURES = ['inventory', 'discounts', 'loyalty', 'zatca', 'email_receipts'];
  const FEATURE_META: Record<string, { icon: typeof Box; tone: string; label: string; desc: string }> = {
    inventory: { icon: Box, tone: 'dxr-sw-brand', label: t('inventory') || 'Inventory', desc: t('stock_tracking') || 'Stock tracking' },
    discounts: { icon: Percent, tone: 'dxr-sw-success', label: t('discounts') || 'Discounts', desc: t('codes_promos') || 'Codes & promos' },
    loyalty: { icon: Star, tone: 'dxr-sw-gold', label: t('loyalty') || 'Loyalty program', desc: t('points_rewards') || 'Points & rewards' },
    zatca: { icon: QrCode, tone: 'dxr-sw-sky', label: t('zatca') || 'ZATCA e-invoice', desc: t('qr_receipts') || 'QR receipts' },
    email_receipts: { icon: Mail, tone: 'dxr-sw-violet', label: t('email_receipts') || 'Email receipts', desc: t('auto_send') || 'Auto-send' },
  };

  const slotCapacity = remainingSlots + totalClients;
  const activeClients = clients.filter((c) => c.is_active);
  const totalMonthlyRevenue = activeClients.reduce((sum, c) => sum + (c.subscription_fee || 0), 0);
  // M8: the table shows the live book or the archived book; KPIs above always use
  // the live `clients` so switching views never misrepresents the headline numbers.
  const archivedView = clientView === 'archived';
  const tableClients = archivedView ? archivedClients : clients;
  const panelClient = clients.find((c) => c.id === panelClientId) || clients[0] || null;
  const brandColor = branding?.primary_color || '#1488a6';
  // Preview foreground derived from the brand the same way the runtime theme
  // flips ink (#243 AC3) — a pale brand shows dark ink, never invisible white.
  const previewFg = readableTextColor(brandColor);
  const previewChipBg = previewFg === '#ffffff' ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.08)';
  const previewChipRing = previewFg === '#ffffff' ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.12)';

  // Hydrate the selected client's real feature flags the first time its panel is
  // shown. Without this the switches would fabricate an all-on state per client.
  const panelClientFeatureId = panelClient?.id ?? null;
  useEffect(() => {
    if (panelClientFeatureId == null) return;
    if (featureState[panelClientFeatureId]) return;
    if (featureLoadingId === panelClientFeatureId) return;
    loadClientFeatures(panelClientFeatureId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panelClientFeatureId]);

  // The agent keeps 100% of his merchants' subscription revenue (no platform cut
  // here — the platform's cut is the agent's quota, Rail 1). So there is no
  // owed/net split anymore; the collected total is the agent's money.
  const collected = revenue?.collected ?? 0;
  const subsPct = clients.length > 0 ? Math.round((activeClients.length / clients.length) * 100) : 0;
  const quotaFee = quota?.quota_price ?? 0;
  const hasRevenue = !!revenue && revenue.payments > 0;

  usePageChrome(
    {
      subtitle: `${branding?.company_name ? `${branding.company_name} · ` : ''}${clients.length} ${t('clients')} · ${activeClients.length} ${t('active_subscriptions') || 'active subscriptions'}`,
      primaryAction: (
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRunDunning} disabled={dunningBusy} title={t('run_billing_hint')} className="h-11 rounded-[10px]">
            {dunningBusy ? t('loading') : (t('run_billing_cycle') || 'Run billing')}
          </Button>
          <Button onClick={() => setDialogOpen(true)} className="h-11 rounded-[10px] shadow-brand">
            <UserPlus className="h-4 w-4" />
            {t('create_client') || 'Add Client'}
          </Button>
        </div>
      ),
      paletteGroups: [
        {
          label: t('cmd_quick_actions'),
          items: [
            { icon: UserPlus, label: t('create_client') || 'Add Client', kbd: 'C', onSelect: () => setDialogOpen(true) },
            { icon: CreditCard, label: t('run_billing_cycle') || 'Run billing', onSelect: handleRunDunning },
            { icon: Palette, label: t('brand_editor') || 'Branding', onSelect: () => navigate('/branding') },
            { icon: ShoppingBag, label: t('products') || 'Products', onSelect: () => navigate('/products') },
            { icon: BarChart3, label: t('reports') || 'Reports', onSelect: () => navigate('/reports') },
          ],
        },
      ],
    },
    [language, branding?.company_name, clients.length, activeClients.length, dunningBusy]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-pulse text-muted-foreground">{t('loading')}</div>
      </div>
    );
  }

  // H4 — the merchant book failed to load. Tell the truth with a retry rather
  // than rendering an all-zero book that reads as a real (empty) agent.
  if (loadError) {
    return <ErrorState onRetry={loadData} />;
  }

  return (
    <div className="animate-fade-up space-y-5">
      {/* No bespoke in-body header here (#243): the shell (usePageChrome) owns
          the page title/subtitle and the Run-billing primary action, so a
          second <h1> + Run-billing button would duplicate both. */}
      {dunningResult && <p role="status" className="text-sm text-muted-foreground">{dunningResult}</p>}

      {/* Fail-closed (#235): an unconnected Moyasar stalls the whole merchant book.
          Gated on a successful quota load so a load error never fakes the state. */}
      {quota && <AgentMoyasarBanner connected={quota.has_moyasar_account} audience="agent" />}

      {/* Top bento — revenue spotlight + gauge + KPI chips */}
      <div data-tour="stats-section" className="grid gap-4 lg:auto-rows-[116px] lg:grid-cols-12">
        {/* Revenue & margin spotlight */}
        <section className="dxr-tile dxr-ink flex flex-col lg:col-span-8 lg:row-span-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="dxr-eyebrow">{t('revenue_commission') || 'Revenue & Margin'}</div>
              <div className="mt-2 text-[clamp(28px,3.4vw,40px)] font-extrabold leading-none tracking-tight tabular-nums">
                <CountUp value={hasRevenue ? collected : totalMonthlyRevenue} prefix="⃁ " />
              </div>
              <div className="mt-1.5 text-[13px] text-white/65">{t('revenue_collected') || 'Collected'} · {activeClients.length} {t('active_subscriptions') || 'subscriptions'}</div>
            </div>
            <div className="text-end">
              <div className="dxr-eyebrow">{t('subscription_payments') || 'Payments'}</div>
              <div className="mt-1 text-[28px] font-extrabold tabular-nums text-white">{revenue?.payments ?? 0}</div>
            </div>
          </div>

          <div className="mt-auto">
            {revenueLoading ? (
              <div className="animate-pulse py-2 text-sm text-white/60">{t('loading')}</div>
            ) : revenueError ? (
              <div role="alert" className="flex flex-col items-start gap-2">
                <p className="text-sm text-[hsl(6_70%_80%)]">{t('revenue_load_error') || 'Could not load revenue.'}</p>
                <Button variant="secondary" size="sm" onClick={loadRevenue}>{t('retry') || 'Retry'}</Button>
              </div>
            ) : !hasRevenue ? (
              <p className="py-2 text-sm text-white/60">{t('revenue_empty') || 'No settled subscription payments yet.'}</p>
            ) : (
              <>
                <div className="flex h-8 overflow-hidden rounded-[10px]">
                  <div className="flex items-center bg-gradient-to-r from-brand-500 to-brand-600 px-3 text-[12px] font-extrabold text-white" style={{ width: '100%' }}>
                    {t('revenue_collected') || 'Collected'} · {formatMoney(collected, language)}
                  </div>
                </div>
                <div className="mt-2.5 flex gap-4 text-[12px] text-white/65">
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-brand-500" />{t('revenue_collected') || 'Collected (your revenue)'}</span>
                </div>
              </>
            )}
          </div>
        </section>

        {/* Active subscriptions gauge */}
        <section className="dxr-tile dxr-hover lg:col-span-4 lg:row-span-2">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-[14px] font-extrabold">{t('active_subscriptions') || 'Active Subscriptions'}</h2>
            <CreditCard className="h-4 w-4 text-muted-foreground" />
          </div>
          <Gauge pct={subsPct} center={activeClients.length} caption={`/ ${clients.length} ${t('clients') || 'clients'}`} />
        </section>

        {/* KPI chips */}
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('total_clients') || 'Total Clients'}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums"><CountUp value={clients.length} /></div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{activeClients.length} {t('active') || 'active'}</div>
        </section>
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('revenue_collected') || 'Collected'}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums text-success">{formatMoney(collected, language)}</div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{t('this_cycle') || 'this billing cycle'}</div>
        </section>
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('quota_fee') || 'Quota fee'}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums text-warning">{formatMoney(quotaFee, language)}</div>
          <div className="mt-auto text-[11.5px] text-muted-foreground">{quota?.quota_cycle ? (t(quota.quota_cycle) || quota.quota_cycle) : (t('due_to_master') || 'due to platform')}</div>
        </section>
        <section className="dxr-tile dxr-hover flex flex-col lg:col-span-3 lg:row-span-1">
          <div className="text-[12.5px] font-semibold text-muted-foreground">{t('remaining_slots')}</div>
          <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums">{remainingSlots} {t('of')} {slotCapacity}</div>
          <div className="mt-auto pt-2">
            <Bar pct={slotCapacity > 0 ? Math.round((remainingSlots / slotCapacity) * 100) : 0} barClassName="bg-gradient-to-r from-warning to-gold-600" />
          </div>
        </section>
      </div>

      {/* Quick actions */}
      <div data-tour="quick-actions" className="flex flex-wrap gap-2.5">
        <button onClick={() => navigate('/branding')} className="chip-link"><Palette className="h-4 w-4" /> {t('brand_editor') || 'Branding'}</button>
        <button onClick={() => navigate('/products')} className="chip-link"><ShoppingBag className="h-4 w-4" /> {t('products') || 'Products'}</button>
        <button onClick={() => navigate('/reports')} className="chip-link"><BarChart3 className="h-4 w-4" /> {t('reports') || 'Reports'}</button>
      </div>

      {zatcaError && (
        <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">{zatcaError}</div>
      )}

      {/* Clients + right rail */}
      <div className="grid items-start gap-[18px] lg:grid-cols-[1fr_320px]">
        {/* Client list */}
        <div className="dxr-tile p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-5">
            <h2 className="text-[16px] font-extrabold tracking-tight">{t('clients')} <span className="text-muted-foreground">({tableClients.length})</span></h2>
            {/* M8: live book ⇄ archived book. */}
            <div className="dxr-seg" role="tablist" aria-label={t('clients')}>
              <button type="button" role="tab" aria-selected={!archivedView} data-active={!archivedView} onClick={() => setClientView('active')}>{t('active') || 'Active'}</button>
              <button type="button" role="tab" aria-selected={archivedView} data-active={archivedView} onClick={() => setClientView('archived')}>{t('archived') || 'Archived'}</button>
            </div>
          </div>
          <div className="overflow-x-auto px-2 pb-2">
            <table className="w-full">
              <thead>
                <tr className="text-[10.5px] font-bold uppercase tracking-wider text-muted-foreground/80">
                  <th className="px-3 py-2.5 text-start">{t('business_name') || 'Client'}</th>
                  <th className="px-3 py-2.5 text-start">{t('subscription_fee') || 'Fee'}</th>
                  <th className="px-3 py-2.5 text-start">{t('status')}</th>
                  <th className="px-3 py-2.5 text-start">{t('zatca_status') || 'ZATCA'}</th>
                  <th className="px-3 py-2.5 text-end">{t('actions') || 'Actions'}</th>
                </tr>
              </thead>
              <tbody>
                {tableClients.map((c) => (
                  <tr key={c.id} className={cn('border-t border-border/70 transition-colors hover:bg-muted/40', !archivedView && panelClient?.id === c.id && 'bg-brand-50/60 dark:bg-brand-500/10')}>
                    <td className="px-3 py-3">
                      {archivedView ? (
                        <span className="flex items-center gap-2.5 text-start">
                          <Avatar name={c.business_name} size={34} />
                          <span className="min-w-0">
                            <b className="block truncate font-semibold text-foreground">{c.business_name}</b>
                            <span className="block truncate text-[11.5px] text-muted-foreground">{c.email}</span>
                          </span>
                        </span>
                      ) : (
                        <button type="button" onClick={() => setPanelClientId(c.id)} className="flex items-center gap-2.5 text-start" title={t('manage_features') || 'Manage features'}>
                          <Avatar name={c.business_name} size={34} />
                          <span className="min-w-0">
                            <b className="block truncate font-semibold text-foreground">{c.business_name}</b>
                            <span className="block truncate text-[11.5px] text-muted-foreground">{c.email}</span>
                          </span>
                        </button>
                      )}
                    </td>
                    <td className="px-3 py-3 font-semibold tabular-nums">{formatMoney(c.subscription_fee || 0, language)}</td>
                    <td className="px-3 py-3">
                      {archivedView ? (
                        <span className="pill-muted" title={c.archived_at ? formatDate(c.archived_at, language) : undefined}><Archive className="h-3 w-3" /> {t('archived') || 'Archived'}</span>
                      ) : (
                        <span className={c.is_active ? 'pill-success' : 'pill-danger'}><span className="h-[7px] w-[7px] rounded-full bg-current" /> {c.is_active ? t('active') : t('inactive')}</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <span className={c.zatca_enabled ? 'pill-sky' : 'pill-muted'}>{c.zatca_enabled ? (t('zatca_on') || 'On') : (t('zatca_off') || 'Off')}</span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        {archivedView ? (
                          <>
                            <button type="button" onClick={() => handleRestore(c)} disabled={lifecycleBusyId === c.id} title={t('restore_merchant') || 'Restore'} className="inline-flex items-center gap-1.5 rounded-lg bg-success/10 px-2.5 py-1.5 text-xs font-semibold text-success transition-colors hover:bg-success/15 disabled:opacity-50">
                              {lifecycleBusyId === c.id ? '…' : <><ArchiveRestore className="h-3.5 w-3.5" /> {t('restore') || 'Restore'}</>}
                            </button>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <button type="button" title={t('more_actions') || 'More actions'} className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700"><MoreVertical className="h-4 w-4" /></button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => handleExport(c)}><Download className="h-4 w-4" /> {t('export_merchant') || 'Export data'}</DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem className="text-danger focus:text-danger" onClick={() => setDeleteConfirm(c)}><Trash2 className="h-4 w-4" /> {t('delete_merchant') || 'Delete merchant'}</DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </>
                        ) : (
                          <>
                            <button type="button" onClick={() => handleToggleClient(c.id)} disabled={togglingId === c.id} title={c.is_active ? (t('deactivate') || 'Deactivate') : (t('activate') || 'Activate')} className={cn('rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50', c.is_active ? 'bg-danger/10 text-danger hover:bg-danger/15' : 'bg-success/10 text-success hover:bg-success/15')}>
                              {togglingId === c.id ? '…' : c.is_active ? (t('deactivate') || 'Deactivate') : (t('activate') || 'Activate')}
                            </button>
                            <button type="button" onClick={() => setFeatureClient(c)} title={t('features') || 'Features'} className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700"><Sliders className="h-4 w-4" /></button>
                            <button type="button" onClick={() => handleResetPassword(c.id)} disabled={resettingId === c.id} title={t('reset_password') || 'Reset password'} className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700 disabled:opacity-50">{resettingId === c.id ? <span className="text-xs">…</span> : <KeyRound className="h-4 w-4" />}</button>
                            <button type="button" onClick={() => handleToggleZatca(c.id)} disabled={zatcaTogglingId === c.id} title={c.zatca_enabled ? (t('disable_zatca') || 'Disable ZATCA') : (t('enable_zatca') || 'Enable ZATCA')} className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700 disabled:opacity-50">{zatcaTogglingId === c.id ? <span className="text-xs">…</span> : <QrCode className="h-4 w-4" />}</button>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <button type="button" title={t('more_actions') || 'More actions'} disabled={lifecycleBusyId === c.id} className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-muted-foreground transition-colors hover:border-brand hover:text-brand-700 disabled:opacity-50">{lifecycleBusyId === c.id ? <span className="text-xs">…</span> : <MoreVertical className="h-4 w-4" />}</button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => { setTransferTarget(c); setTransferEmail(''); }}><ArrowRightLeft className="h-4 w-4" /> {t('transfer_merchant') || 'Transfer merchant'}</DropdownMenuItem>
                                <DropdownMenuItem onClick={() => handleExport(c)}><Download className="h-4 w-4" /> {t('export_merchant') || 'Export data'}</DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem className="text-danger focus:text-danger" onClick={() => setArchiveConfirm(c)}><Archive className="h-4 w-4" /> {t('archive_merchant') || 'Archive merchant'}</DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {tableClients.length === 0 && (
                  <tr><td colSpan={5} className="py-8 text-center text-sm text-muted-foreground">{archivedView ? (archivedLoading ? (t('loading') || 'Loading…') : (t('no_archived_clients') || 'No archived merchants.')) : (t('no_clients') || 'No clients yet.')}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right rail */}
        <div className="flex flex-col gap-[18px]">
          <div className="dxr-tile">
            <h2 className="mb-1 text-sm font-extrabold tracking-tight">{t('feature_overrides') || 'Feature overrides'}</h2>
            {panelClient ? (
              <>
                <div className="mb-1.5 flex items-center gap-2">
                  <Avatar name={panelClient.business_name} size={26} />
                  <b className="text-[13px] font-semibold text-foreground">{panelClient.business_name}</b>
                </div>
                {!featureState[panelClient.id] && featureLoadError === panelClient.id ? (
                  <div role="alert" className="flex flex-col items-start gap-2 py-3">
                    <p className="text-sm text-danger">{t('feature_load_error')}</p>
                    <Button variant="outline" size="sm" onClick={() => loadClientFeatures(panelClient.id)}>{t('retry')}</Button>
                  </div>
                ) : !featureState[panelClient.id] ? (
                  <p className="animate-pulse py-4 text-sm text-muted-foreground">{t('loading')}</p>
                ) : (
                  TOGGLEABLE_FEATURES.map((f) => {
                    const meta = FEATURE_META[f];
                    const Icon = meta?.icon || Box;
                    const flags = featureState[panelClient.id];
                    const checked = flags?.[f] ?? true;
                    return (
                      <div key={f} className="flex items-center justify-between gap-3 border-b border-dashed border-border py-3 last:border-b-0">
                        <div className="flex items-center gap-2.5">
                          <span className={cn('dxr-sw h-8 w-8', meta?.tone || 'bg-muted text-muted-foreground')}><Icon className="h-4 w-4" /></span>
                          <div>
                            <b className="block text-[13.5px] font-semibold text-foreground">{meta?.label || (t(f) || f)}</b>
                            <span className="block text-[11.5px] text-muted-foreground">{meta?.desc}</span>
                          </div>
                        </div>
                        <Switch checked={checked} disabled={!flags} onCheckedChange={(v) => handleToggleFeatureInline(panelClient, f, v)} />
                      </div>
                    );
                  })
                )}
              </>
            ) : (
              <p className="py-4 text-sm text-muted-foreground">{t('select_client_features') || 'Select a client to manage features.'}</p>
            )}
          </div>

          {/* White-label preview */}
          <div className="dxr-tile">
            <h2 className="mb-3 text-sm font-extrabold tracking-tight">{t('your_white_label') || 'Your white-label look'}</h2>
            <div className="overflow-hidden rounded-xl border border-border">
              <div data-testid="wl-preview-header" className="flex h-16 items-center gap-2.5 px-4" style={{ background: brandColor, color: previewFg }}>
                <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg" style={{ background: previewChipBg, boxShadow: `0 0 0 1px ${previewChipRing}` }}><Store className="h-4 w-4" /></span>
                <b className="text-sm">{branding?.company_name || t('app_name')}</b>
              </div>
              <div className="flex flex-col gap-2.5 bg-card p-4">
                <div className="h-[9px] w-[70%] rounded bg-muted" />
                <div className="h-[9px] w-[90%] rounded bg-muted" />
                <div className="h-[9px] w-[50%] rounded bg-muted" />
                <div className="mt-1 h-[30px] w-[120px] rounded-md" style={{ background: brandColor }} />
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <span className="h-[26px] w-[26px] rounded-md ring-1 ring-black/10" style={{ background: brandColor }} />
              <span className="h-[26px] w-[26px] rounded-md bg-gold ring-1 ring-black/10" />
              <span className="h-[26px] w-[26px] rounded-md bg-brand-800 ring-1 ring-black/10" />
            </div>
            <Button onClick={() => navigate('/branding')} className="mt-4 w-full shadow-brand"><Palette className="h-4 w-4" /> {t('edit_branding') || 'Edit branding'}</Button>
          </div>
        </div>
      </div>

      {/* Commission statements */}
      <section className="dxr-tile" data-testid="commission-statements">
        <div className="mb-3.5 flex items-center justify-between">
          <h2 className="text-[16px] font-extrabold tracking-tight">{t('commission_statements') || 'Commission statements'}</h2>
          <span className="text-[12.5px] text-muted-foreground">{t('per_billing_period') || 'Per billing period'}</span>
        </div>
        {statementsLoading ? (
          <div className="animate-pulse py-4 text-sm text-muted-foreground">{t('loading')}</div>
        ) : statementsError ? (
          <div role="alert" className="flex flex-col items-start gap-2">
            <p className="text-sm text-danger">{t('statements_load_error') || 'Could not load statements.'}</p>
            <Button variant="outline" size="sm" onClick={loadStatements}>{t('retry') || 'Retry'}</Button>
          </div>
        ) : statements.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">{t('statements_empty') || 'No commission statements yet.'}</p>
        ) : (
          <div className="space-y-4">
            {statements.map((stmt) => (
              <div key={`${stmt.period_start}-${stmt.period_end}`} className="overflow-hidden rounded-xl border border-border">
                <div className="flex flex-wrap items-center justify-between gap-2 bg-muted/40 px-4 py-2.5">
                  <div className="text-sm font-semibold text-foreground">{stmt.period_start} <span className="text-muted-foreground">→</span> {stmt.period_end}</div>
                  <div className="flex items-center gap-4 text-[12.5px] tabular-nums">
                    <span className="text-muted-foreground">{t('revenue_collected') || 'Collected'}: <span className="font-semibold text-foreground">{formatMoney(stmt.collected, language)}</span></span>
                    <span className="text-muted-foreground">{t('subscription_payments') || 'Payments'}: <span className="font-semibold text-foreground">{stmt.payments}</span></span>
                  </div>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-[12px] text-muted-foreground">
                      <th className="px-4 py-2 text-start font-medium">{t('client') || 'Client'}</th>
                      <th className="px-4 py-2 text-end font-medium">{t('revenue_collected') || 'Collected'}</th>
                      <th className="px-4 py-2 text-end font-medium">{t('subscription_payments') || 'Payments'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stmt.by_client.map((line) => (
                      <tr key={line.client_id} className="border-b border-border last:border-0">
                        <td className="px-4 py-2 text-foreground">{line.business_name || `#${line.client_id}`}</td>
                        <td className="px-4 py-2 text-end tabular-nums text-foreground">{formatMoney(line.collected, language)}</td>
                        <td className="px-4 py-2 text-end tabular-nums text-muted-foreground">{line.payments}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Billing: agent quota (Rail 1) + connect own Moyasar (Rail 2) */}
      <div className="grid items-start gap-[18px] lg:grid-cols-2">
        {/* Your quota (Rail 1 — what the agent pays the platform) */}
        <section className="dxr-tile" data-testid="agent-quota">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-[16px] font-extrabold tracking-tight"><span className="dxr-sw dxr-sw-gold h-7 w-7"><Wallet className="h-4 w-4" /></span>{t('your_quota') || 'Your quota'}</h2>
            {quota?.quota_status && (
              <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold', quota.quota_status === 'active' ? 'bg-success/10 text-success' : quota.quota_status === 'suspended' ? 'bg-danger/10 text-danger' : 'bg-warning/15 text-warning')}>
                <span className="h-1.5 w-1.5 rounded-full bg-current" />{t(quota.quota_status) || quota.quota_status}
              </span>
            )}
          </div>
          {quotaLoading ? (
            <div className="animate-pulse py-4 text-sm text-muted-foreground">{t('loading')}</div>
          ) : quotaError ? (
            <div role="alert" className="flex flex-col items-start gap-2">
              <p className="text-sm text-danger">{t('quota_load_error') || 'Could not load quota status.'}</p>
              <Button variant="outline" size="sm" onClick={loadQuota}>{t('retry') || 'Retry'}</Button>
            </div>
          ) : (
            <>
              <div className="flex items-end justify-between">
                <div>
                  <div className="text-xs text-muted-foreground">{t('quota_fee') || 'Quota fee'}</div>
                  <div className="mt-1 text-2xl font-extrabold tracking-tight tabular-nums">{formatMoney(quota?.quota_price ?? 0, language)}</div>
                  <div className="text-[11.5px] text-muted-foreground">/ {quota?.quota_cycle ? (t(quota.quota_cycle) || quota.quota_cycle) : '—'}</div>
                </div>
                <div className="text-end">
                  <div className="text-xs text-muted-foreground">{t('next_quota_payment') || 'Next quota payment'}</div>
                  <div className="mt-1 font-semibold tabular-nums">{quota?.next_quota_billing_date ? formatDate(quota.next_quota_billing_date, language) : '—'}</div>
                </div>
              </div>

              {/* Quota card-on-file (paid through the platform account) */}
              <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/40 px-3 py-2.5">
                <div className="flex items-center gap-2.5">
                  <span className="dxr-sw dxr-sw-brand h-8 w-8"><CreditCard className="h-4 w-4" /></span>
                  <div>
                    <div className="text-[12.5px] font-semibold text-foreground">{t('card_on_file') || 'Card on file'}</div>
                    {quota?.has_card ? (
                      <div className="text-[11.5px] text-muted-foreground">•••• {quota.card_last4}{quota.card_brand ? ` · ${quota.card_brand}` : ''}</div>
                    ) : (
                      <div className="text-[11.5px] text-muted-foreground">{t('no_card_on_file') || 'No card on file'}</div>
                    )}
                  </div>
                </div>
                <Button variant="outline" size="sm" onClick={() => setQuotaCardOpen(true)}>
                  {quota?.has_card ? (t('update') || 'Update') : (t('add_card') || 'Add card')}
                </Button>
              </div>

              <Button onClick={handlePayQuota} disabled={payingQuota || !quota?.has_card || (quota?.quota_price ?? 0) <= 0} className="mt-3 w-full shadow-brand">
                {payingQuota ? t('loading') : (t('pay_renew_quota') || 'Pay / renew quota')}
              </Button>

              {quota && quota.payments.length > 0 && (
                <div className="mt-4 border-t border-border pt-3">
                  <p className="mb-2 text-sm text-muted-foreground">{t('quota_payments') || 'Recent quota payments'}</p>
                  <div className="space-y-1">
                    {quota.payments.slice(0, 6).map((p, i) => (
                      <div key={p.reference || i} className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">{p.period_start ? formatDate(p.period_start, language) : (p.billing_cycle ? (t(p.billing_cycle) || p.billing_cycle) : '—')}</span>
                        <span className="font-semibold tabular-nums">{formatMoney(p.amount, language)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </section>

        {/* Connect your Moyasar account (Rail 2 — collects from his merchants) */}
        <section className="dxr-tile" data-testid="agent-moyasar">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-[16px] font-extrabold tracking-tight"><span className="dxr-sw dxr-sw-violet h-7 w-7"><Link2 className="h-4 w-4" /></span>{t('connect_moyasar') || 'Connect your Moyasar account'}</h2>
            <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold', quota?.has_moyasar_account ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground')}>
              <span className="h-1.5 w-1.5 rounded-full bg-current" />{quota?.has_moyasar_account ? (t('account_connected') || 'Connected') : (t('not_connected') || 'Not connected')}
            </span>
          </div>
          <p className="mb-3 text-sm text-muted-foreground">{t('moyasar_connect_hint') || 'Connect your own Moyasar account to collect subscription payments from your merchants.'}</p>
          <form onSubmit={handleSaveMoyasar} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="moyasar-secret">{t('moyasar_secret_key') || 'Secret key'}</Label>
              <Input id="moyasar-secret" type="password" autoComplete="off" placeholder="sk_…" value={moyasarForm.secret_key} onChange={(e) => setMoyasarForm({ ...moyasarForm, secret_key: e.target.value })} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="moyasar-pub">{t('moyasar_publishable_key') || 'Publishable key'}</Label>
              <Input id="moyasar-pub" autoComplete="off" placeholder="pk_…" value={moyasarForm.publishable_key} onChange={(e) => setMoyasarForm({ ...moyasarForm, publishable_key: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="moyasar-webhook">{t('moyasar_webhook_secret') || 'Webhook secret'}</Label>
              <Input id="moyasar-webhook" type="password" autoComplete="off" value={moyasarForm.webhook_secret} onChange={(e) => setMoyasarForm({ ...moyasarForm, webhook_secret: e.target.value })} />
            </div>
            <Button type="submit" disabled={savingMoyasar || !moyasarForm.secret_key} className="w-full shadow-brand">
              {savingMoyasar ? t('loading') : (t('connect_moyasar') || 'Connect account')}
            </Button>
          </form>
        </section>
      </div>

      {/* ===== Dialogs ===== */}
      <CardOnFileDialog
        open={quotaCardOpen}
        onOpenChange={setQuotaCardOpen}
        onSave={handleSaveQuotaCard}
        publishableKey={quota?.moyasar_publishable_key}
        titleKey="card_on_file"
      />

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogTrigger asChild><span className="hidden" /></DialogTrigger>
        <DialogContent>
          <DialogHeader><DialogTitle>{t('create_client')}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <Input placeholder={t('business_name')} value={newClientForm.business_name} onChange={(e) => setNewClientForm({ ...newClientForm, business_name: e.target.value })} />
            <Input placeholder={t('email')} value={newClientForm.email} onChange={(e) => setNewClientForm({ ...newClientForm, email: e.target.value })} />
            <Input placeholder={t('phone')} value={newClientForm.phone} onChange={(e) => setNewClientForm({ ...newClientForm, phone: e.target.value })} />
            <div className="flex gap-2">
              <Input type="number" min={0} step="0.01" placeholder={t('subscription_fee')} value={newClientForm.subscription_fee} onChange={(e) => setNewClientForm({ ...newClientForm, subscription_fee: e.target.value })} className="flex-1" />
              <Select value={newClientForm.billing_cycle} onValueChange={(v) => setNewClientForm({ ...newClientForm, billing_cycle: v })}>
                <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">{t('monthly') || 'Monthly'}</SelectItem>
                  <SelectItem value="yearly">{t('yearly') || 'Yearly'}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {createError && <p className="text-sm text-danger">{createError}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDialogOpen(false)}>{t('cancel')}</Button>
              <Button onClick={handleCreateClient}>{t('save')}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!createdCreds} onOpenChange={(open) => !open && setCreatedCreds(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{createdCreds?.reset ? (t('password_reset_done') || 'Password reset') : (t('client_created') || 'Client created')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {createdCreds?.email_delivered
                ? (createdCreds?.reset ? (t('new_password_emailed') || 'The new password was emailed to the client.') : (t('credentials_emailed') || 'Login credentials were emailed to the client.'))
                : (t('credentials_show_once') || 'Share these login credentials with the client now — they will not be shown again. They must change the password on first login.')}
            </p>
            <div className="rounded-xl bg-muted p-3 font-mono text-sm text-foreground">
              <div>{t('email')}: {createdCreds?.email}</div>
              <div>{t('password') || 'Password'}: {createdCreds?.temp_password}</div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { if (createdCreds) navigator.clipboard?.writeText(`Email: ${createdCreds.email}\nPassword: ${createdCreds.temp_password}`); }}>{t('copy') || 'Copy'}</Button>
              <Button onClick={() => setCreatedCreds(null)}>{t('done') || 'Done'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!featureClient} onOpenChange={(open) => !open && setFeatureClient(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t('features') || 'Features'} — {featureClient?.business_name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('feature_toggle_hint') || 'Enable or disable capabilities for this client. Features are on by default.'}</p>
            {TOGGLEABLE_FEATURES.map((f) => (
              <div key={f} className="flex items-center justify-between gap-2">
                <span className="text-foreground/90">{t(f) || f}</span>
                <div className="flex gap-2">
                  <Button size="sm" variant="success" disabled={featureBusy} onClick={() => handleSetFeature(f, true)} className="text-xs">{t('enable') || 'Enable'}</Button>
                  <Button size="sm" variant="outline-danger" disabled={featureBusy} onClick={() => handleSetFeature(f, false)} className="text-xs">{t('disable') || 'Disable'}</Button>
                </div>
              </div>
            ))}
            <div className="flex justify-end pt-2"><Button onClick={() => setFeatureClient(null)}>{t('done') || 'Done'}</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      {/* M8: transfer a merchant to another agent (by the destination agent's email). */}
      <Dialog open={!!transferTarget} onOpenChange={(open) => { if (!open) { setTransferTarget(null); setTransferEmail(''); } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t('transfer_merchant') || 'Transfer merchant'}{transferTarget ? ` — ${transferTarget.business_name}` : ''}</DialogTitle></DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => { e.preventDefault(); handleTransfer(); }}
          >
            <p className="text-sm text-muted-foreground">{t('transfer_merchant_desc') || 'Hand this merchant to another agent. Their catalog, customers and sales move with them.'}</p>
            <div className="space-y-1.5">
              <Label htmlFor="transfer-email">{t('destination_agent_email') || "Destination agent's email"}</Label>
              <Input id="transfer-email" type="email" autoFocus required value={transferEmail} onChange={(e) => setTransferEmail(e.target.value)} placeholder="agent@example.com" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" onClick={() => { setTransferTarget(null); setTransferEmail(''); }}>{t('cancel') || 'Cancel'}</Button>
              <Button type="submit" disabled={transferBusy || !transferEmail.trim()} className="shadow-brand"><ArrowRightLeft className="h-4 w-4" /> {transferBusy ? (t('loading') || 'Loading…') : (t('transfer') || 'Transfer')}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* M8: confirm archive (reversible) and post-retention delete (irreversible). */}
      <AlertDialog open={!!archiveConfirm} onOpenChange={(open) => !open && setArchiveConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('archive_merchant') || 'Archive merchant'}{archiveConfirm ? ` — ${archiveConfirm.business_name}` : ''}</AlertDialogTitle>
            <AlertDialogDescription>{t('confirm_archive_merchant') || 'Archive this merchant? Its login is blocked and its slot is freed. You can restore it anytime.'}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel') || 'Cancel'}</AlertDialogCancel>
            <AlertDialogAction onClick={() => archiveConfirm && handleArchive(archiveConfirm)}>{t('archive') || 'Archive'}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!deleteConfirm} onOpenChange={(open) => !open && setDeleteConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('delete_merchant') || 'Delete merchant'}{deleteConfirm ? ` — ${deleteConfirm.business_name}` : ''}</AlertDialogTitle>
            <AlertDialogDescription>{t('confirm_delete_merchant') || 'Permanently delete this archived merchant? This cannot be undone.'}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel') || 'Cancel'}</AlertDialogCancel>
            <AlertDialogAction className="bg-danger text-danger-foreground hover:bg-danger/90" onClick={() => deleteConfirm && handleDelete(deleteConfirm)}>{t('delete') || 'Delete'}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
