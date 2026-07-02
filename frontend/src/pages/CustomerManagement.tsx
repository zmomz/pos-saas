import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { undoableAction } from '@/lib/undo';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchField } from '@/components/ui/search-field';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
  getCustomers,
  createCustomer,
  updateCustomer,
  deleteCustomer,
  exportCustomerData,
  eraseCustomerData,
  getCustomerInsights,
  getConsentHistory,
  getRetentionPolicy,
  setRetentionPolicy,
  enforceRetentionPolicy,
  type CustomerInsights,
  type ConsentEvent,
} from '@/lib/api';
import ErrorState from '@/components/states/ErrorState';
import LoadingState from '@/components/states/LoadingState';
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile from '@/components/dashboard/StatTile';
import { useLanguage } from '@/lib/i18n';
import { useBulkSelection } from '@/hooks/useBulkSelection';
import SavedFilterBar from '@/components/dashboard/rx/SavedFilterBar';
import { useSavedFilters } from '@/hooks/useSavedFilters';
import { formatMoney, formatDateTime } from '@/lib/format';
import { Plus, Users, UserPlus, Download, ShieldOff, BarChart3, Tag, History, ShieldCheck } from 'lucide-react';

interface Customer {
  id: string;
  name: string;
  phone?: string;
  email?: string;
  vat_number?: string;
  address?: string;
  notes?: string;
  total_purchases?: number;
  visit_count?: number;
  marketing_consent?: boolean;
  tags?: string[];
  pii_erased_at?: string | null;
  created_at?: string;
}

interface CustomerFormData {
  name: string;
  phone: string;
  email: string;
  vat_number: string;
  address: string;
  notes: string;
  marketing_consent: boolean;
  // Edited as a comma-separated string; split into the tags array on submit.
  tags: string;
}

// #273 — the filter combination a saved view captures for the Customers book.
interface CustomerFilterPreset {
  search: string;
  tagFilter: string;
}

const emptyForm: CustomerFormData = {
  name: '',
  phone: '',
  email: '',
  vat_number: '',
  address: '',
  notes: '',
  marketing_consent: false,
  tags: '',
};

// Comma-separated input <-> tags array (CRM-04 / F-039).
function parseTags(value: string): string[] {
  return value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

export default function CustomerManagement() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  // #273 (Productivity — global-search deep-linking): a ⌘K hit lands here with a
  // ?q= seed identifying the record; pre-fill the search so it narrows to it.
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(() => searchParams.get('q') ?? '');
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [eraseOpen, setEraseOpen] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [formData, setFormData] = useState<CustomerFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState('');
  const [tagFilter, setTagFilter] = useState<string>('');
  // #273 (Productivity follow-up) — the saved-filter machinery, first wired on
  // Products, extended to the Customers book: pin a search+segment combination
  // under a name and re-apply it in one click. Preset captures both dimensions.
  const savedFilters = useSavedFilters<CustomerFilterPreset>('dxr.savedfilters.customers');

  // CRM-04 (F-039): per-customer computed insights dialog.
  const [insightsOpen, setInsightsOpen] = useState(false);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsError, setInsightsError] = useState(false);
  const [insights, setInsights] = useState<CustomerInsights | null>(null);

  // M7·Compliance (#272): per-customer PDPL consent trail dialog.
  const [consentOpen, setConsentOpen] = useState(false);
  const [consentLoading, setConsentLoading] = useState(false);
  const [consentError, setConsentError] = useState(false);
  const [consentEvents, setConsentEvents] = useState<ConsentEvent[]>([]);

  // M7·Compliance (#272): tenant-wide dormant-PII retention policy dialog.
  const [retentionOpen, setRetentionOpen] = useState(false);
  const [retentionLoading, setRetentionLoading] = useState(false);
  const [retentionError, setRetentionError] = useState(false);
  const [retentionDays, setRetentionDays] = useState('');
  const [retentionUpdatedAt, setRetentionUpdatedAt] = useState<string | null>(null);
  const [retentionSaving, setRetentionSaving] = useState(false);
  const [retentionNotice, setRetentionNotice] = useState('');

  const { t, tt, language } = useLanguage();

  useEffect(() => {
    loadCustomers();
  }, []);

  async function loadCustomers() {
    setLoading(true);
    setLoadError(false);
    try {
      const data = await getCustomers();
      setCustomers(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load customers:', err);
      setCustomers([]);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  // Every distinct tag in use, for the segment filter chips (CRM-04 / F-039).
  const allTags = Array.from(
    new Set(customers.flatMap((c) => (Array.isArray(c.tags) ? c.tags : []))),
  ).sort((a, b) => a.localeCompare(b));

  const filteredCustomers = customers.filter((c) => {
    const term = search.toLowerCase();
    const matchesSearch =
      c.name?.toLowerCase().includes(term) ||
      c.phone?.toLowerCase().includes(term) ||
      c.email?.toLowerCase().includes(term);
    const matchesTag = !tagFilter || (Array.isArray(c.tags) && c.tags.includes(tagFilter));
    return matchesSearch && matchesTag;
  });

  // #231 (Productivity — bulk ops): multi-row selection for batch actions via the
  // shared useBulkSelection hook. The list is unpaginated, so the "page" is the
  // whole filtered set; the bulk bar surfaces once anything is selected.
  const {
    selectedIds,
    allPageSelected,
    isSelected,
    toggle: toggleSelect,
    toggleAllOnPage: toggleSelectAllOnPage,
    clear: clearSelection,
  } = useBulkSelection<string>(filteredCustomers.map((c) => c.id));

  function handleFormChange(field: keyof CustomerFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddCustomer() {
    setSubmitting(true);
    try {
      await createCustomer({
        name: formData.name,
        phone: formData.phone || undefined,
        email: formData.email || undefined,
        vat_number: formData.vat_number || undefined,
        address: formData.address || undefined,
        notes: formData.notes || undefined,
        marketing_consent: formData.marketing_consent,
        tags: parseTags(formData.tags),
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadCustomers();
    } catch (err) {
      console.error('Failed to create customer:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openEdit(customer: Customer) {
    setSelectedCustomer(customer);
    setFormData({
      name: customer.name,
      phone: customer.phone || '',
      email: customer.email || '',
      vat_number: customer.vat_number || '',
      address: customer.address || '',
      notes: customer.notes || '',
      marketing_consent: !!customer.marketing_consent,
      tags: Array.isArray(customer.tags) ? customer.tags.join(', ') : '',
    });
    setEditOpen(true);
  }

  async function handleEditCustomer() {
    if (!selectedCustomer) return;
    setSubmitting(true);
    try {
      await updateCustomer(selectedCustomer.id, {
        name: formData.name,
        phone: formData.phone || undefined,
        email: formData.email || undefined,
        vat_number: formData.vat_number || undefined,
        address: formData.address || undefined,
        notes: formData.notes || undefined,
        marketing_consent: formData.marketing_consent,
        tags: parseTags(formData.tags),
      });
      setEditOpen(false);
      setSelectedCustomer(null);
      setFormData(emptyForm);
      await loadCustomers();
    } catch (err) {
      console.error('Failed to update customer:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openDelete(customer: Customer) {
    setSelectedCustomer(customer);
    setDeleteOpen(true);
  }

  // #231 (Productivity — undo): deleting a customer is deferred behind an undo
  // window. We drop the row optimistically and only hit the server once the
  // window elapses; an undo cancels the commit outright so a mis-click never
  // reaches the backend and no restore round-trip is needed.
  function handleDeleteCustomer() {
    if (!selectedCustomer) return;
    const customer = selectedCustomer;
    setDeleteOpen(false);
    setSelectedCustomer(null);
    // Optimistic removal; the server still holds the row until (and unless) the
    // deferred commit fires, so a refetch reliably restores it on undo.
    setCustomers((prev) => prev.filter((c) => c.id !== customer.id));
    undoableAction({
      message: tt('customer_deleted', 'Customer deleted'),
      undoLabel: tt('action_undo', 'Undo'),
      onUndo: () => {
        loadCustomers();
      },
      onCommit: async () => {
        try {
          await deleteCustomer(customer.id);
          await loadCustomers();
        } catch (err) {
          console.error('Failed to delete customer:', err);
          // Commit failed — restore the row so the operator isn't misled.
          loadCustomers();
        }
      },
    });
  }

  // #231 (Productivity — bulk ops + undo): delete every selected customer in one
  // action. Mirrors the single-row delete: rows drop optimistically and the
  // deletes are deferred behind the undo window, so an undo cancels the whole
  // batch before it reaches the server and no restore round-trip is needed.
  function handleBulkDelete() {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    clearSelection();
    setCustomers((prev) => prev.filter((c) => !ids.includes(c.id)));
    undoableAction({
      message: `${ids.length} ${tt('customers_deleted', 'customers deleted')}`,
      undoLabel: tt('action_undo', 'Undo'),
      onUndo: () => {
        loadCustomers();
      },
      onCommit: async () => {
        try {
          await Promise.all(ids.map((id) => deleteCustomer(id)));
          await loadCustomers();
        } catch (err) {
          console.error('Failed to bulk-delete customers:', err);
          // Commit failed — restore the rows so the operator isn't misled.
          loadCustomers();
        }
      },
    });
  }

  // PDPL (SEC-05): download everything held about the customer as JSON.
  async function handleExportData(customer: Customer) {
    setActionError('');
    try {
      const bundle = await exportCustomerData(customer.id);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `customer-${customer.id}-data-export.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export customer data:', err);
      setActionError(t('export_failed'));
    }
  }

  function openErase(customer: Customer) {
    setActionError('');
    setSelectedCustomer(customer);
    setEraseOpen(true);
  }

  // PDPL (SEC-05): tombstone the customer's PII (row retained for fiscal records).
  async function handleEraseCustomer() {
    if (!selectedCustomer) return;
    setSubmitting(true);
    setActionError('');
    try {
      await eraseCustomerData(selectedCustomer.id);
      setEraseOpen(false);
      setSelectedCustomer(null);
      await loadCustomers();
    } catch (err) {
      console.error('Failed to erase customer PII:', err);
      setActionError(t('erase_failed'));
    } finally {
      setSubmitting(false);
    }
  }

  // CRM-04 (F-039): open the computed insights dialog for a customer. Renders
  // its own loading / error (with retry) / data states.
  async function openInsights(customer: Customer) {
    setSelectedCustomer(customer);
    setInsights(null);
    setInsightsError(false);
    setInsightsOpen(true);
    await loadInsights(customer.id);
  }

  async function loadInsights(customerId: string) {
    setInsightsLoading(true);
    setInsightsError(false);
    try {
      const data = await getCustomerInsights(customerId);
      setInsights(data);
    } catch (err) {
      console.error('Failed to load customer insights:', err);
      setInsightsError(true);
    } finally {
      setInsightsLoading(false);
    }
  }

  // M7·Compliance (#272): open the PDPL consent trail for a customer. Lazily
  // fetched on open so the list mount is untouched. Renders loading/error/data.
  async function openConsent(customer: Customer) {
    setSelectedCustomer(customer);
    setConsentEvents([]);
    setConsentError(false);
    setConsentOpen(true);
    await loadConsent(customer.id);
  }

  async function loadConsent(customerId: string) {
    setConsentLoading(true);
    setConsentError(false);
    try {
      const data = await getConsentHistory(customerId);
      setConsentEvents(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      console.error('Failed to load consent history:', err);
      setConsentError(true);
    } finally {
      setConsentLoading(false);
    }
  }

  // M7·Compliance (#272): open the tenant retention policy. Lazily fetched.
  async function openRetention() {
    setRetentionNotice('');
    setRetentionError(false);
    setRetentionOpen(true);
    await loadRetention();
  }

  async function loadRetention() {
    setRetentionLoading(true);
    setRetentionError(false);
    try {
      const policy = await getRetentionPolicy();
      setRetentionDays(
        policy?.customer_pii_retention_days != null
          ? String(policy.customer_pii_retention_days)
          : '',
      );
      setRetentionUpdatedAt(policy?.updated_at ?? null);
    } catch (err) {
      console.error('Failed to load retention policy:', err);
      setRetentionError(true);
    } finally {
      setRetentionLoading(false);
    }
  }

  // Arm (positive day count) or disable (blank ⇒ null) the retention window.
  async function handleSaveRetention() {
    setRetentionSaving(true);
    setRetentionNotice('');
    try {
      const trimmed = retentionDays.trim();
      const days = trimmed === '' ? null : Number(trimmed);
      const policy = await setRetentionPolicy(days);
      setRetentionDays(
        policy?.customer_pii_retention_days != null
          ? String(policy.customer_pii_retention_days)
          : '',
      );
      setRetentionUpdatedAt(policy?.updated_at ?? null);
      setRetentionNotice(t('retention_saved'));
    } catch (err) {
      console.error('Failed to save retention policy:', err);
      setRetentionNotice(t('retention_save_failed'));
    } finally {
      setRetentionSaving(false);
    }
  }

  // Run the sweep now: minimize PII on every customer past the window.
  async function handleEnforceRetention() {
    setRetentionSaving(true);
    setRetentionNotice('');
    try {
      const result = await enforceRetentionPolicy();
      setRetentionNotice(`${result.erased_count} ${t('retention_swept_suffix')}`);
      await loadCustomers();
    } catch (err) {
      console.error('Failed to enforce retention policy:', err);
      setRetentionNotice(t('retention_save_failed'));
    } finally {
      setRetentionSaving(false);
    }
  }

  function segmentLabel(segment?: string): string {
    switch (segment) {
      case 'vip':
        return t('seg_vip');
      case 'at_risk':
        return t('seg_at_risk');
      case 'regular':
        return t('seg_regular');
      default:
        return t('seg_new');
    }
  }

  function segmentClass(segment?: string): string {
    switch (segment) {
      case 'vip':
        return 'pill-gold';
      case 'at_risk':
        return 'pill-danger';
      case 'regular':
        return 'pill-success';
      default:
        return 'pill-muted';
    }
  }

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <Label className="mb-1 block">{tt('name', 'Name')} *</Label>
          <Input
            value={formData.name}
            onChange={(e) => handleFormChange('name', e.target.value)}
            placeholder={tt('customer_name', 'Customer name')}
          />
        </div>
        <div>
          <Label className="mb-1 block">{tt('phone', 'Phone')}</Label>
          <Input
            value={formData.phone}
            onChange={(e) => handleFormChange('phone', e.target.value)}
            placeholder="+966 5xx xxx xxxx"
          />
        </div>
        <div>
          <Label className="mb-1 block">{tt('email', 'Email')}</Label>
          <Input
            value={formData.email}
            onChange={(e) => handleFormChange('email', e.target.value)}
            placeholder="email@example.com"
          />
        </div>
        <div>
          <Label className="mb-1 block">{tt('vat_number_b2b', 'VAT Number (B2B)')}</Label>
          <Input
            value={formData.vat_number}
            onChange={(e) => handleFormChange('vat_number', e.target.value)}
            placeholder="3xxxxxxxxxxxxx3"
          />
        </div>
        <div>
          <Label className="mb-1 block">{tt('address', 'Address')}</Label>
          <Input
            value={formData.address}
            onChange={(e) => handleFormChange('address', e.target.value)}
            placeholder={tt('street_address', 'Street address')}
          />
        </div>
        <div>
          <Label className="mb-1 block">{tt('notes', 'Notes')}</Label>
          <Input
            value={formData.notes}
            onChange={(e) => handleFormChange('notes', e.target.value)}
            placeholder={tt('additional_notes', 'Additional notes')}
          />
        </div>
        {/* Segmentation tags (CRM-04 / F-039) — comma-separated */}
        <div>
          <Label className="mb-1 block">{t('tags')}</Label>
          <Input
            value={formData.tags}
            onChange={(e) => handleFormChange('tags', e.target.value)}
            placeholder={t('tags_placeholder')}
          />
        </div>
        {/* PDPL marketing consent (SEC-05 / CRM-05) */}
        <div className="flex items-start gap-3 rounded-md border border-input bg-muted/40 p-3">
          <Checkbox
            id="marketing-consent"
            checked={formData.marketing_consent}
            onCheckedChange={(v) =>
              setFormData((prev) => ({ ...prev, marketing_consent: v === true }))
            }
            className="mt-0.5"
          />
          <label htmlFor="marketing-consent" className="cursor-pointer">
            <span className="text-sm text-foreground block">{t('marketing_consent')}</span>
            <span className="text-xs text-muted-foreground block">{t('marketing_consent_hint')}</span>
          </label>
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.name}
            className="flex-1"
          >
            {submitting ? t('loading') : submitLabel}
          </Button>
        </div>
      </div>
    );
  }

  if (loading && customers.length === 0) {
    return <LoadingState message={t('loading')} />;
  }

  const customerColumns: DataTableColumn<Customer>[] = [
    {
      key: 'select',
      className: 'w-0',
      header: (
        <Checkbox
          checked={allPageSelected}
          onCheckedChange={toggleSelectAllOnPage}
          aria-label={tt('select_all', 'Select all')}
        />
      ),
      cell: (customer) => (
        <Checkbox
          checked={isSelected(customer.id)}
          onCheckedChange={() => toggleSelect(customer.id)}
          aria-label={`${tt('select_row', 'Select')} ${customer.name}`}
        />
      ),
    },
    {
      key: 'name',
      header: tt('name', 'Name'),
      className: 'font-medium text-foreground',
      cell: (customer) => (
        <>
          {customer.name}
          {customer.pii_erased_at && (
            <Badge variant="outline" className="ms-2 border-input text-muted-foreground text-xs">
              {t('pii_erased')}
            </Badge>
          )}
        </>
      ),
    },
    {
      key: 'phone',
      header: tt('phone', 'Phone'),
      cell: (customer) => customer.phone || '—',
    },
    {
      key: 'email',
      header: tt('email', 'Email'),
      cell: (customer) => customer.email || '—',
    },
    {
      key: 'vat',
      header: tt('vat_number', 'VAT Number'),
      cell: (customer) => customer.vat_number || '—',
    },
    {
      key: 'tags',
      header: t('tags'),
      cell: (customer) =>
        Array.isArray(customer.tags) && customer.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {customer.tags.map((tag) => (
              <Badge key={tag} variant="outline" className="border-brand/40 text-brand text-xs">
                {tag}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: 'consent',
      header: t('consent'),
      cell: (customer) =>
        customer.marketing_consent ? (
          <span className="pill-success">{t('consent_given')}</span>
        ) : (
          <span className="text-muted-foreground">{t('consent_none')}</span>
        ),
    },
    {
      key: 'actions',
      header: tt('actions', 'Actions'),
      cell: (customer) => {
        const erased = !!customer.pii_erased_at;
        return (
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => openEdit(customer)}
              disabled={erased}
              className="text-xs"
            >
              {tt('edit', 'Edit')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => openInsights(customer)}
              className="text-xs"
            >
              <BarChart3 className="h-3 w-3 me-1" />
              {t('view_insights')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => openConsent(customer)}
              className="text-xs"
            >
              <History className="h-3 w-3 me-1" />
              {t('consent_history')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleExportData(customer)}
              className="text-xs"
            >
              <Download className="h-3 w-3 me-1" />
              {t('export_data')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => openErase(customer)}
              disabled={erased}
              className="text-xs"
            >
              <ShieldOff className="h-3 w-3 me-1" />
              {t('erase_pii')}
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => openDelete(customer)}
              className="text-xs"
            >
              {tt('delete', 'Delete')}
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="animate-fade-up space-y-6">
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <PageHeading
          icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Users className="h-[18px] w-[18px]" /></span>}
          title={tt('customers', 'Customers')}
          subtitle={`${customers.length} ${tt('customers', 'Customers')}`}
        >
          <Button
            variant="outline"
            onClick={openRetention}
            className="h-11 rounded-[10px]"
          >
            <ShieldCheck className="h-4 w-4" />
            {t('retention_policy')}
          </Button>
          <DialogTrigger asChild>
            <Button
              onClick={() => setFormData(emptyForm)}
              className="h-11 rounded-[10px] shadow-brand"
            >
              <Plus className="h-4 w-4" />
              {tt('add_customer', 'Add Customer')}
            </Button>
          </DialogTrigger>
        </PageHeading>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{tt('add_new_customer', 'Add New Customer')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleAddCustomer, tt('add_customer', 'Add Customer'))}
        </DialogContent>
      </Dialog>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile icon={Users} label={tt('total_customers', 'Total Customers')} value={customers.length} tone="brand" />
        <StatTile
          icon={UserPlus}
          label={tt('new_this_month', 'New This Month')}
          value={customers.filter((c) => {
            if (!c.created_at) return false;
            const d = new Date(c.created_at);
            const now = new Date();
            return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
          }).length}
          tone="success"
        />
        <StatTile
          icon={Users}
          label={tt('with_email', 'With Email')}
          value={customers.filter((c) => c.email).length}
          tone="violet"
        />
      </div>

      {/* Search */}
      <SearchField
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={tt('search_customers', 'Search by name, phone, or email...')}
      />

      {/* #273 (Productivity — saved filters): pin the current search/segment
          combination under a name and re-apply it in one click. */}
      <SavedFilterBar<CustomerFilterPreset>
        saved={savedFilters.saved}
        onApply={(v) => {
          setSearch(v.search);
          setTagFilter(v.tagFilter);
        }}
        onSave={(name) => savedFilters.save(name, { search, tagFilter })}
        onRemove={savedFilters.remove}
        saveLabel={t('saved_views_save')}
        namePlaceholder={t('saved_views_name_placeholder')}
        applyTitle={(name) => t('saved_views_apply').replace('{name}', name)}
        removeLabel={(name) => t('saved_views_remove').replace('{name}', name)}
      />

      {/* Segment filter (CRM-04 / F-039) — filter the book by tag */}
      {allTags.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1 text-sm text-muted-foreground">
            <Tag className="h-4 w-4" />
            {t('filter_by_tag')}:
          </span>
          <button
            type="button"
            onClick={() => setTagFilter('')}
            className={`rounded-full px-3 py-1 text-xs ${
              tagFilter === '' ? 'bg-brand text-white' : 'bg-muted text-foreground/90'
            }`}
          >
            {t('all_tags')}
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => setTagFilter(tag)}
              className={`rounded-full px-3 py-1 text-xs ${
                tagFilter === tag ? 'bg-brand text-white' : 'bg-muted text-foreground/90'
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {/* Action error (PDPL export/erase) */}
      {actionError && (
        <div role="alert" className="rounded-md border border-danger/50 bg-danger/10 p-3 text-sm text-danger">
          {actionError}
        </div>
      )}

      {/* #231 bulk-action bar: surfaces once any row is selected. */}
      {selectedIds.size > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-2.5">
          <span className="text-sm font-medium text-brand-800" role="status" aria-live="polite">
            {selectedIds.size} {tt('selected', 'selected')}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={handleBulkDelete}
            className="border-danger/40 text-danger hover:bg-danger/10"
          >
            {tt('delete_selected', 'Delete selected')}
          </Button>
        </div>
      )}

      {/* Table — an error never masquerades as "no customers" */}
      {loadError ? (
        <ErrorState message={t('customers_load_error')} onRetry={loadCustomers} />
      ) : (
        <DataTable
          className="dxr-tile p-0"
          columns={customerColumns}
          rows={filteredCustomers}
          rowKey={(customer) => customer.id}
          empty={tt('no_customers_found', 'No customers found')}
        />
      )}

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{tt('edit_customer', 'Edit Customer')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditCustomer, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{tt('confirm_delete', 'Confirm Delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-foreground/90">
            {tt('delete_customer_confirm', 'Are you sure you want to delete')} <strong>{selectedCustomer?.name}</strong>? {tt('action_cannot_be_undone', 'This action cannot be undone.')}
          </p>
          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(false)}
              className="flex-1"
            >
              {t('cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteCustomer}
              disabled={submitting}
              className="flex-1"
            >
              {submitting ? t('loading') : tt('delete', 'Delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* PDPL Erase Dialog (SEC-05) */}
      <Dialog open={eraseOpen} onOpenChange={setEraseOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('erase_pii')}</DialogTitle>
          </DialogHeader>
          <p className="text-foreground/90">
            {t('erase_pii_confirm')} <strong>{selectedCustomer?.name}</strong>
          </p>
          <p className="text-xs text-muted-foreground">{t('erase_pii_retention')}</p>
          {actionError && (
            <div role="alert" className="rounded-md border border-danger/50 bg-danger/10 p-2 text-sm text-danger">
              {actionError}
            </div>
          )}
          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => setEraseOpen(false)}
              className="flex-1"
            >
              {t('cancel')}
            </Button>
            <Button
              onClick={handleEraseCustomer}
              variant="warning"
              disabled={submitting}
              className="flex-1"
            >
              {submitting ? t('loading') : t('erase_pii')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Customer insights — computed LTV / RFM-lite (CRM-04 / F-039) */}
      <Dialog open={insightsOpen} onOpenChange={setInsightsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-violet" />
              {t('customer_insights')}
              {selectedCustomer && (
                <span className="text-muted-foreground font-normal">— {selectedCustomer.name}</span>
              )}
            </DialogTitle>
          </DialogHeader>

          {insightsLoading ? (
            <LoadingState className="py-12" />
          ) : insightsError ? (
            <ErrorState
              message={t('insights_error')}
              onRetry={() => selectedCustomer && loadInsights(selectedCustomer.id)}
            />
          ) : insights && insights.visit_count === 0 ? (
            <div className="py-12 text-center text-muted-foreground">{t('no_purchases')}</div>
          ) : insights ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">{t('segment')}</span>
                <span className={segmentClass(insights.segment)}>
                  {segmentLabel(insights.segment)}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-md border border-border bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('lifetime_value')}</p>
                  <p className="text-xl font-bold text-foreground tabular-nums">
                    {formatMoney(insights.lifetime_value, language)}
                  </p>
                </div>
                <div className="rounded-md border border-border bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('visits')}</p>
                  <p className="text-xl font-bold text-foreground tabular-nums">{insights.visit_count}</p>
                </div>
                <div className="rounded-md border border-border bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('avg_basket')}</p>
                  <p className="text-lg font-semibold text-foreground tabular-nums">
                    {formatMoney(insights.average_basket, language)}
                  </p>
                </div>
                <div className="rounded-md border border-border bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('last_purchase_label')}</p>
                  <p className="text-lg font-semibold text-foreground">
                    {insights.recency_days != null
                      ? `${insights.recency_days} ${t('days_ago')}`
                      : '—'}
                  </p>
                </div>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* PDPL consent trail — append-only history behind the snapshot (#272) */}
      <Dialog open={consentOpen} onOpenChange={setConsentOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History className="h-5 w-5 text-brand" />
              {t('consent_history')}
              {selectedCustomer && (
                <span className="text-muted-foreground font-normal">— {selectedCustomer.name}</span>
              )}
            </DialogTitle>
          </DialogHeader>

          {consentLoading ? (
            <LoadingState className="py-12" />
          ) : consentError ? (
            <ErrorState
              message={t('consent_history_error')}
              onRetry={() => selectedCustomer && loadConsent(selectedCustomer.id)}
            />
          ) : consentEvents.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">{t('consent_history_empty')}</div>
          ) : (
            <ol className="space-y-2">
              {consentEvents.map((ev) => (
                <li
                  key={ev.id}
                  className="flex items-start justify-between gap-3 rounded-md border border-border bg-muted/40 p-3"
                >
                  <div>
                    <span className={ev.granted ? 'pill-success' : 'pill-muted'}>
                      {ev.granted ? t('consent_granted') : t('consent_withdrawn')}
                    </span>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t('consent_source')}: {ev.source}
                      {ev.actor ? ` · ${ev.actor}` : ''}
                    </p>
                  </div>
                  <span className="whitespace-nowrap text-xs text-muted-foreground" dir="ltr">
                    {ev.created_at ? formatDateTime(ev.created_at, language) : '—'}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </DialogContent>
      </Dialog>

      {/* Tenant dormant-PII retention policy (#272, SEC-05 / PDPL) */}
      <Dialog open={retentionOpen} onOpenChange={setRetentionOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-brand" />
              {t('retention_policy_title')}
            </DialogTitle>
          </DialogHeader>

          {retentionLoading ? (
            <LoadingState className="py-12" />
          ) : retentionError ? (
            <ErrorState message={t('retention_load_error')} onRetry={loadRetention} />
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">{t('retention_policy_hint')}</p>
              <div>
                <Label className="mb-1 block" htmlFor="retention-days">
                  {t('retention_days_label')}
                </Label>
                <Input
                  id="retention-days"
                  type="number"
                  min={1}
                  inputMode="numeric"
                  value={retentionDays}
                  onChange={(e) => setRetentionDays(e.target.value)}
                  placeholder={t('retention_disabled_placeholder')}
                  dir="ltr"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  {retentionDays.trim() === ''
                    ? t('retention_disabled')
                    : retentionUpdatedAt
                      ? `${t('retention_updated_at')}: ${formatDateTime(retentionUpdatedAt, language)}`
                      : ''}
                </p>
              </div>
              {retentionNotice && (
                <div className="rounded-md border border-brand/40 bg-brand/10 p-2 text-sm text-foreground">
                  {retentionNotice}
                </div>
              )}
              <div className="flex flex-wrap gap-3 pt-1">
                <Button onClick={handleSaveRetention} disabled={retentionSaving} className="flex-1">
                  {retentionSaving ? t('loading') : t('save')}
                </Button>
                <Button
                  variant="warning"
                  onClick={handleEnforceRetention}
                  disabled={retentionSaving}
                  className="flex-1"
                >
                  <ShieldOff className="h-4 w-4 me-1" />
                  {t('retention_enforce')}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}