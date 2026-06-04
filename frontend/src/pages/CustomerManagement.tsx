import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
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
import { useLanguage } from '@/lib/i18n';
import { Users, UserPlus, Search, Download, ShieldOff, BarChart3, Tag } from 'lucide-react';

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

  const { t } = useLanguage();

  useEffect(() => {
    loadCustomers();
  }, []);

  async function loadCustomers() {
    setLoading(true);
    try {
      const data = await getCustomers();
      setCustomers(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load customers:', err);
      setCustomers([]);
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
        return 'bg-amber-600/20 text-amber-400';
      case 'at_risk':
        return 'bg-red-600/20 text-red-400';
      case 'regular':
        return 'bg-green-600/20 text-green-400';
      default:
        return 'bg-slate-600/30 text-slate-300';
    }
  }

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Name *</label>
          <Input
            value={formData.name}
            onChange={(e) => handleFormChange('name', e.target.value)}
            placeholder="Customer name"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Phone</label>
          <Input
            value={formData.phone}
            onChange={(e) => handleFormChange('phone', e.target.value)}
            placeholder="+966 5xx xxx xxxx"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Email</label>
          <Input
            value={formData.email}
            onChange={(e) => handleFormChange('email', e.target.value)}
            placeholder="email@example.com"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">VAT Number (B2B)</label>
          <Input
            value={formData.vat_number}
            onChange={(e) => handleFormChange('vat_number', e.target.value)}
            placeholder="3xxxxxxxxxxxxx3"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Address</label>
          <Input
            value={formData.address}
            onChange={(e) => handleFormChange('address', e.target.value)}
            placeholder="Street address"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Notes</label>
          <Input
            value={formData.notes}
            onChange={(e) => handleFormChange('notes', e.target.value)}
            placeholder="Additional notes"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        {/* Segmentation tags (CRM-04 / F-039) — comma-separated */}
        <div>
          <label className="text-sm text-slate-400 mb-1 block">{t('tags')}</label>
          <Input
            value={formData.tags}
            onChange={(e) => handleFormChange('tags', e.target.value)}
            placeholder={t('tags_placeholder')}
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        {/* PDPL marketing consent (SEC-05 / CRM-05) */}
        <div className="flex items-start gap-3 rounded-md border border-slate-600 bg-slate-700/40 p-3">
          <Checkbox
            id="marketing-consent"
            checked={formData.marketing_consent}
            onCheckedChange={(v) =>
              setFormData((prev) => ({ ...prev, marketing_consent: v === true }))
            }
            className="mt-0.5"
          />
          <label htmlFor="marketing-consent" className="cursor-pointer">
            <span className="text-sm text-white block">{t('marketing_consent')}</span>
            <span className="text-xs text-slate-400 block">{t('marketing_consent_hint')}</span>
          </label>
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.name}
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
          >
            {submitting ? t('loading') : submitLabel}
          </Button>
        </div>
      </div>
    );
  }

  if (loading && customers.length === 0) {
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
            <Users className="h-8 w-8 text-blue-400" />
            <div>
              <p className="text-slate-400 text-sm">Total Customers</p>
              <p className="text-2xl font-bold text-white">{customers.length}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <UserPlus className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-slate-400 text-sm">New This Month</p>
              <p className="text-2xl font-bold text-green-400">
                {customers.filter((c) => {
                  if (!c.created_at) return false;
                  const d = new Date(c.created_at);
                  const now = new Date();
                  return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
                }).length}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <Users className="h-8 w-8 text-purple-400" />
            <div>
              <p className="text-slate-400 text-sm">With Email</p>
              <p className="text-2xl font-bold text-purple-400">
                {customers.filter((c) => c.email).length}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search + Add */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, phone, or email..."
            className="pl-10 bg-slate-800 border-slate-600 text-white placeholder:text-slate-500"
          />
        </div>
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button
              onClick={() => setFormData(emptyForm)}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              + Add Customer
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-white">Add New Customer</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddCustomer, 'Add Customer')}
          </DialogContent>
        </Dialog>
      </div>

      {/* Segment filter (CRM-04 / F-039) — filter the book by tag */}
      {allTags.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1 text-sm text-slate-400">
            <Tag className="h-4 w-4" />
            {t('filter_by_tag')}:
          </span>
          <button
            type="button"
            onClick={() => setTagFilter('')}
            className={`rounded-full px-3 py-1 text-xs ${
              tagFilter === '' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'
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
                tagFilter === tag ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {/* Action error (PDPL export/erase) */}
      {actionError && (
        <div role="alert" className="rounded-md border border-red-600/50 bg-red-600/10 p-3 text-sm text-red-400">
          {actionError}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-800">
            <tr className="text-slate-400">
              <th className="p-3 text-start">Name</th>
              <th className="p-3 text-start">Phone</th>
              <th className="p-3 text-start">Email</th>
              <th className="p-3 text-start">VAT Number</th>
              <th className="p-3 text-start">{t('tags')}</th>
              <th className="p-3 text-start">{t('consent')}</th>
              <th className="p-3 text-start">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredCustomers.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-6 text-center text-slate-500">
                  No customers found
                </td>
              </tr>
            ) : (
              filteredCustomers.map((customer) => {
                const erased = !!customer.pii_erased_at;
                return (
                <tr key={customer.id} className="border-t border-slate-700 text-slate-300">
                  <td className="p-3 text-white font-medium">
                    {customer.name}
                    {erased && (
                      <Badge variant="outline" className="ms-2 border-slate-500 text-slate-400 text-xs">
                        {t('pii_erased')}
                      </Badge>
                    )}
                  </td>
                  <td className="p-3">{customer.phone || '—'}</td>
                  <td className="p-3">{customer.email || '—'}</td>
                  <td className="p-3">{customer.vat_number || '—'}</td>
                  <td className="p-3">
                    {Array.isArray(customer.tags) && customer.tags.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {customer.tags.map((tag) => (
                          <Badge
                            key={tag}
                            variant="outline"
                            className="border-blue-600/40 text-blue-300 text-xs"
                          >
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                  <td className="p-3">
                    {customer.marketing_consent ? (
                      <Badge className="bg-green-600/20 text-green-400 text-xs">{t('consent_given')}</Badge>
                    ) : (
                      <span className="text-slate-500">{t('consent_none')}</span>
                    )}
                  </td>
                  <td className="p-3">
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openEdit(customer)}
                        disabled={erased}
                        className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openInsights(customer)}
                        className="border-purple-600/50 text-purple-300 hover:bg-purple-600/20 text-xs"
                      >
                        <BarChart3 className="h-3 w-3 me-1" />
                        {t('view_insights')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleExportData(customer)}
                        className="border-blue-600/50 text-blue-400 hover:bg-blue-600/20 text-xs"
                      >
                        <Download className="h-3 w-3 me-1" />
                        {t('export_data')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openErase(customer)}
                        disabled={erased}
                        className="border-amber-600/50 text-amber-400 hover:bg-amber-600/20 text-xs"
                      >
                        <ShieldOff className="h-3 w-3 me-1" />
                        {t('erase_pii')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openDelete(customer)}
                        className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs"
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-white">Edit Customer</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditCustomer, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Confirm Delete</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">
            Are you sure you want to delete <strong>{selectedCustomer?.name}</strong>? This action
            cannot be undone.
          </p>
          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(false)}
              className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              {t('cancel')}
            </Button>
            <Button
              onClick={handleDeleteCustomer}
              disabled={submitting}
              className="flex-1 bg-red-600 hover:bg-red-700 text-white"
            >
              {submitting ? t('loading') : 'Delete'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* PDPL Erase Dialog (SEC-05) */}
      <Dialog open={eraseOpen} onOpenChange={setEraseOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">{t('erase_pii')}</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">
            {t('erase_pii_confirm')} <strong>{selectedCustomer?.name}</strong>
          </p>
          <p className="text-xs text-slate-500">{t('erase_pii_retention')}</p>
          {actionError && (
            <div role="alert" className="rounded-md border border-red-600/50 bg-red-600/10 p-2 text-sm text-red-400">
              {actionError}
            </div>
          )}
          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => setEraseOpen(false)}
              className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              {t('cancel')}
            </Button>
            <Button
              onClick={handleEraseCustomer}
              disabled={submitting}
              className="flex-1 bg-amber-600 hover:bg-amber-700 text-white"
            >
              {submitting ? t('loading') : t('erase_pii')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Customer insights — computed LTV / RFM-lite (CRM-04 / F-039) */}
      <Dialog open={insightsOpen} onOpenChange={setInsightsOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-purple-400" />
              {t('customer_insights')}
              {selectedCustomer && (
                <span className="text-slate-400 font-normal">— {selectedCustomer.name}</span>
              )}
            </DialogTitle>
          </DialogHeader>

          {insightsLoading ? (
            <div className="py-12 text-center text-slate-400 animate-pulse">{t('loading')}</div>
          ) : insightsError ? (
            <ErrorState
              message={t('insights_error')}
              onRetry={() => selectedCustomer && loadInsights(selectedCustomer.id)}
            />
          ) : insights && insights.visit_count === 0 ? (
            <div className="py-12 text-center text-slate-500">{t('no_purchases')}</div>
          ) : insights ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">{t('segment')}</span>
                <Badge className={`${segmentClass(insights.segment)} text-xs`}>
                  {segmentLabel(insights.segment)}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-md border border-slate-700 bg-slate-700/40 p-3">
                  <p className="text-xs text-slate-400">{t('lifetime_value')}</p>
                  <p className="text-xl font-bold text-white">
                    {insights.lifetime_value.toFixed(2)} <span className="text-sm">SAR</span>
                  </p>
                </div>
                <div className="rounded-md border border-slate-700 bg-slate-700/40 p-3">
                  <p className="text-xs text-slate-400">{t('visits')}</p>
                  <p className="text-xl font-bold text-white">{insights.visit_count}</p>
                </div>
                <div className="rounded-md border border-slate-700 bg-slate-700/40 p-3">
                  <p className="text-xs text-slate-400">{t('avg_basket')}</p>
                  <p className="text-lg font-semibold text-white">
                    {insights.average_basket.toFixed(2)} <span className="text-xs">SAR</span>
                  </p>
                </div>
                <div className="rounded-md border border-slate-700 bg-slate-700/40 p-3">
                  <p className="text-xs text-slate-400">{t('last_purchase_label')}</p>
                  <p className="text-lg font-semibold text-white">
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