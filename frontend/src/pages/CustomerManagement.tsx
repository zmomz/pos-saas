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
import { getCustomers, createCustomer, updateCustomer, deleteCustomer } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Users, UserPlus, Search } from 'lucide-react';

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
  created_at?: string;
}

interface CustomerFormData {
  name: string;
  phone: string;
  email: string;
  vat_number: string;
  address: string;
  notes: string;
}

const emptyForm: CustomerFormData = {
  name: '',
  phone: '',
  email: '',
  vat_number: '',
  address: '',
  notes: '',
};

export default function CustomerManagement() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [formData, setFormData] = useState<CustomerFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

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

  const filteredCustomers = customers.filter((c) => {
    const term = search.toLowerCase();
    return (
      c.name?.toLowerCase().includes(term) ||
      c.phone?.toLowerCase().includes(term) ||
      c.email?.toLowerCase().includes(term)
    );
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

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-800">
            <tr className="text-slate-400">
              <th className="p-3 text-start">Name</th>
              <th className="p-3 text-start">Phone</th>
              <th className="p-3 text-start">Email</th>
              <th className="p-3 text-start">VAT Number</th>
              <th className="p-3 text-start">Address</th>
              <th className="p-3 text-start">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredCustomers.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-6 text-center text-slate-500">
                  No customers found
                </td>
              </tr>
            ) : (
              filteredCustomers.map((customer) => (
                <tr key={customer.id} className="border-t border-slate-700 text-slate-300">
                  <td className="p-3 text-white font-medium">{customer.name}</td>
                  <td className="p-3">{customer.phone || '—'}</td>
                  <td className="p-3">{customer.email || '—'}</td>
                  <td className="p-3">{customer.vat_number || '—'}</td>
                  <td className="p-3 max-w-[200px] truncate">{customer.address || '—'}</td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openEdit(customer)}
                        className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                      >
                        Edit
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
              ))
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
    </div>
  );
}