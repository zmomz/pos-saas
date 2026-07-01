import { useEffect, useState } from 'react';
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
  type CustomerInsights,
} from '@/lib/api';
import ErrorState from '@/components/states/ErrorState';
import LoadingState from '@/components/states/LoadingState';
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile from '@/components/dashboard/StatTile';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { Plus, Users, UserPlus, Download, ShieldOff, BarChart3, Tag } from 'lucide-react';

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
  const [search, setSearch] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [eraseOpen, setEraseOpen] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [formData, setFormData] = useState<CustomerFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState('');
  const [tagFilter, setTagFilter] = useState<string>('');

  // CRM-04 (F-039): per-customer computed insights dialog.
  const [insightsOpen, setInsightsOpen] = useState(false);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsError, setInsightsError] = useState(false);
  const [insights, setInsights] = useState<CustomerInsights | null>(null);

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

  async function handleDeleteCustomer() {
    if (!selectedCustomer) return;
    setSubmitting(true);
    try {
      await deleteCustomer(selectedCustomer.id);
      setDeleteOpen(false);
      setSelectedCustomer(null);
      await loadCustomers();
    } catch (err) {
      console.error('Failed to delete customer:', err);
    } finally {
      setSubmitting(false);
    }
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
    </div>
  );
}