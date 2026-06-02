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
import { client, receivePurchaseOrder } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Truck, Plus, Search, Package, ClipboardList, CheckCircle } from 'lucide-react';

interface Supplier {
  id: string;
  name: string;
  contact_person?: string;
  email?: string;
  phone?: string;
  payment_terms?: string;
  status?: string;
  address?: string;
  created_at?: string;
}

interface PurchaseOrder {
  id: string;
  supplier_id: string;
  supplier_name?: string;
  status: string;
  total_amount: number;
  items_count: number;
  order_date?: string;
  received_date?: string;
  created_at?: string;
}

interface SupplierFormData {
  name: string;
  contact_person: string;
  email: string;
  phone: string;
  payment_terms: string;
  address: string;
}

interface POFormData {
  supplier_id: string;
  items: { product_name: string; quantity: number; unit_price: number }[];
}

const emptySupplierForm: SupplierFormData = {
  name: '',
  contact_person: '',
  email: '',
  phone: '',
  payment_terms: 'Net 30',
  address: '',
};

export default function SupplierManagement() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [poOpen, setPoOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null);
  const [formData, setFormData] = useState<SupplierFormData>(emptySupplierForm);
  const [poForm, setPoForm] = useState<POFormData>({ supplier_id: '', items: [{ product_name: '', quantity: 1, unit_price: 0 }] });
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<'suppliers' | 'orders'>('suppliers');

  const { t } = useLanguage();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [suppRes, poRes] = await Promise.all([
        client.entities.suppliers.query({ query: {}, limit: 200 }),
        client.entities.purchase_orders.query({ query: {}, limit: 200 }),
      ]);
      const suppData = suppRes.data;
      const poData = poRes.data;
      setSuppliers(Array.isArray(suppData?.items) ? suppData.items : Array.isArray(suppData) ? suppData : []);
      setPurchaseOrders(Array.isArray(poData?.items) ? poData.items : Array.isArray(poData) ? poData : []);
    } catch (err) {
      console.error('Failed to load supplier data:', err);
      setSuppliers([]);
      setPurchaseOrders([]);
    } finally {
      setLoading(false);
    }
  }

  const filteredSuppliers = suppliers.filter((s) => {
    const term = search.toLowerCase();
    return (
      s.name?.toLowerCase().includes(term) ||
      s.contact_person?.toLowerCase().includes(term) ||
      s.email?.toLowerCase().includes(term)
    );
  });

  function handleFormChange(field: keyof SupplierFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddSupplier() {
    setSubmitting(true);
    try {
      await client.entities.suppliers.create({
        data: {
          name: formData.name,
          contact_person: formData.contact_person || undefined,
          email: formData.email || undefined,
          phone: formData.phone || undefined,
          payment_terms: formData.payment_terms || 'Net 30',
          address: formData.address || undefined,
          status: 'active',
        },
      });
      setAddOpen(false);
      setFormData(emptySupplierForm);
      await loadData();
    } catch (err) {
      console.error('Failed to create supplier:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEditSupplier() {
    if (!selectedSupplier) return;
    setSubmitting(true);
    try {
      await client.entities.suppliers.update({
        id: selectedSupplier.id,
        data: {
          name: formData.name,
          contact_person: formData.contact_person || undefined,
          email: formData.email || undefined,
          phone: formData.phone || undefined,
          payment_terms: formData.payment_terms || undefined,
          address: formData.address || undefined,
        },
      });
      setEditOpen(false);
      setSelectedSupplier(null);
      setFormData(emptySupplierForm);
      await loadData();
    } catch (err) {
      console.error('Failed to update supplier:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeleteSupplier() {
    if (!selectedSupplier) return;
    setSubmitting(true);
    try {
      await client.entities.suppliers.delete({ id: selectedSupplier.id });
      setDeleteOpen(false);
      setSelectedSupplier(null);
      await loadData();
    } catch (err) {
      console.error('Failed to delete supplier:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openEdit(supplier: Supplier) {
    setSelectedSupplier(supplier);
    setFormData({
      name: supplier.name,
      contact_person: supplier.contact_person || '',
      email: supplier.email || '',
      phone: supplier.phone || '',
      payment_terms: supplier.payment_terms || 'Net 30',
      address: supplier.address || '',
    });
    setEditOpen(true);
  }

  function openCreatePO(supplier: Supplier) {
    setSelectedSupplier(supplier);
    setPoForm({ supplier_id: supplier.id, items: [{ product_name: '', quantity: 1, unit_price: 0 }] });
    setPoOpen(true);
  }

  async function handleCreatePO() {
    setSubmitting(true);
    try {
      const totalAmount = poForm.items.reduce((sum, item) => sum + item.quantity * item.unit_price, 0);
      await client.entities.purchase_orders.create({
        data: {
          supplier_id: poForm.supplier_id,
          supplier_name: selectedSupplier?.name,
          status: 'draft',
          total_amount: totalAmount,
          items_count: poForm.items.length,
          items: JSON.stringify(poForm.items),
          order_date: new Date().toISOString(),
        },
      });
      setPoOpen(false);
      await loadData();
    } catch (err) {
      console.error('Failed to create PO:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReceiveStock(po: PurchaseOrder) {
    try {
      // Phase 6: the real receive endpoint increments product stock + records
      // cost server-side (idempotent), rather than just flipping the status.
      await receivePurchaseOrder(po.id);
      await loadData();
    } catch (err) {
      console.error('Failed to receive stock:', err);
    }
  }

  function addPOItem() {
    setPoForm((prev) => ({
      ...prev,
      items: [...prev.items, { product_name: '', quantity: 1, unit_price: 0 }],
    }));
  }

  function updatePOItem(index: number, field: string, value: string | number) {
    setPoForm((prev) => {
      const items = [...prev.items];
      items[index] = { ...items[index], [field]: value };
      return { ...prev, items };
    });
  }

  function removePOItem(index: number) {
    setPoForm((prev) => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== index),
    }));
  }

  function getStatusBadge(status: string) {
    const colors: Record<string, string> = {
      draft: 'bg-gray-500/20 text-gray-400',
      sent: 'bg-blue-500/20 text-blue-400',
      received: 'bg-green-500/20 text-green-400',
      cancelled: 'bg-red-500/20 text-red-400',
      active: 'bg-green-500/20 text-green-400',
      inactive: 'bg-red-500/20 text-red-400',
    };
    return <Badge className={colors[status] || 'bg-gray-500/20 text-gray-400'}>{status}</Badge>;
  }

  function renderSupplierForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Supplier Name *</label>
          <Input value={formData.name} onChange={(e) => handleFormChange('name', e.target.value)} placeholder="Company name" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Contact Person</label>
          <Input value={formData.contact_person} onChange={(e) => handleFormChange('contact_person', e.target.value)} placeholder="Contact name" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Email</label>
          <Input value={formData.email} onChange={(e) => handleFormChange('email', e.target.value)} placeholder="supplier@example.com" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Phone</label>
          <Input value={formData.phone} onChange={(e) => handleFormChange('phone', e.target.value)} placeholder="+966 5xx xxx xxxx" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Payment Terms</label>
          <Input value={formData.payment_terms} onChange={(e) => handleFormChange('payment_terms', e.target.value)} placeholder="Net 30" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Address</label>
          <Input value={formData.address} onChange={(e) => handleFormChange('address', e.target.value)} placeholder="Full address" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <Button onClick={onSubmit} disabled={submitting || !formData.name} className="w-full bg-blue-600 hover:bg-blue-700 text-white">
          {submitting ? t('loading') : submitLabel}
        </Button>
      </div>
    );
  }

  if (loading && suppliers.length === 0) {
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
            <Truck className="h-8 w-8 text-blue-400" />
            <div>
              <p className="text-slate-400 text-sm">Total Suppliers</p>
              <p className="text-2xl font-bold text-white">{suppliers.length}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <ClipboardList className="h-8 w-8 text-yellow-400" />
            <div>
              <p className="text-slate-400 text-sm">Pending Orders</p>
              <p className="text-2xl font-bold text-yellow-400">
                {purchaseOrders.filter((po) => po.status === 'draft' || po.status === 'sent').length}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <CheckCircle className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-slate-400 text-sm">Received This Month</p>
              <p className="text-2xl font-bold text-green-400">
                {purchaseOrders.filter((po) => {
                  if (po.status !== 'received' || !po.received_date) return false;
                  const d = new Date(po.received_date);
                  const now = new Date();
                  return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
                }).length}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        <Button variant={activeTab === 'suppliers' ? 'default' : 'outline'} onClick={() => setActiveTab('suppliers')} className={activeTab === 'suppliers' ? 'bg-blue-600 text-white' : 'border-slate-600 text-slate-300'}>
          Suppliers
        </Button>
        <Button variant={activeTab === 'orders' ? 'default' : 'outline'} onClick={() => setActiveTab('orders')} className={activeTab === 'orders' ? 'bg-blue-600 text-white' : 'border-slate-600 text-slate-300'}>
          Purchase Orders
        </Button>
      </div>

      {activeTab === 'suppliers' && (
        <>
          {/* Search + Add */}
          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search suppliers..." className="pl-10 bg-slate-800 border-slate-600 text-white placeholder:text-slate-500" />
            </div>
            <Dialog open={addOpen} onOpenChange={setAddOpen}>
              <DialogTrigger asChild>
                <Button onClick={() => setFormData(emptySupplierForm)} className="bg-blue-600 hover:bg-blue-700 text-white">
                  <Plus className="h-4 w-4 mr-2" /> Add Supplier
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="text-white">Add New Supplier</DialogTitle>
                </DialogHeader>
                {renderSupplierForm(handleAddSupplier, 'Add Supplier')}
              </DialogContent>
            </Dialog>
          </div>

          {/* Suppliers Table */}
          <div className="overflow-x-auto rounded-lg border border-slate-700">
            <table className="w-full text-sm">
              <thead className="bg-slate-800">
                <tr className="text-slate-400">
                  <th className="p-3 text-start">Name</th>
                  <th className="p-3 text-start">Contact</th>
                  <th className="p-3 text-start">Email</th>
                  <th className="p-3 text-start">Phone</th>
                  <th className="p-3 text-start">Terms</th>
                  <th className="p-3 text-start">Status</th>
                  <th className="p-3 text-start">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredSuppliers.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-6 text-center text-slate-500">No suppliers found</td>
                  </tr>
                ) : (
                  filteredSuppliers.map((supplier) => (
                    <tr key={supplier.id} className="border-t border-slate-700 text-slate-300">
                      <td className="p-3 text-white font-medium">{supplier.name}</td>
                      <td className="p-3">{supplier.contact_person || '—'}</td>
                      <td className="p-3">{supplier.email || '—'}</td>
                      <td className="p-3">{supplier.phone || '—'}</td>
                      <td className="p-3">{supplier.payment_terms || '—'}</td>
                      <td className="p-3">{getStatusBadge(supplier.status || 'active')}</td>
                      <td className="p-3">
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => openEdit(supplier)} className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs">Edit</Button>
                          <Button size="sm" variant="outline" onClick={() => openCreatePO(supplier)} className="border-blue-600/50 text-blue-400 hover:bg-blue-600/20 text-xs">
                            <Package className="h-3 w-3 mr-1" /> PO
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => { setSelectedSupplier(supplier); setDeleteOpen(true); }} className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs">Delete</Button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {activeTab === 'orders' && (
        <div className="overflow-x-auto rounded-lg border border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-800">
              <tr className="text-slate-400">
                <th className="p-3 text-start">Order ID</th>
                <th className="p-3 text-start">Supplier</th>
                <th className="p-3 text-start">Items</th>
                <th className="p-3 text-start">Total</th>
                <th className="p-3 text-start">Status</th>
                <th className="p-3 text-start">Date</th>
                <th className="p-3 text-start">Actions</th>
              </tr>
            </thead>
            <tbody>
              {purchaseOrders.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-slate-500">No purchase orders</td>
                </tr>
              ) : (
                purchaseOrders.map((po) => (
                  <tr key={po.id} className="border-t border-slate-700 text-slate-300">
                    <td className="p-3 text-white font-mono text-xs">#{po.id.slice(0, 8)}</td>
                    <td className="p-3">{po.supplier_name || '—'}</td>
                    <td className="p-3">{po.items_count}</td>
                    <td className="p-3 text-white font-medium">SAR {po.total_amount?.toFixed(2)}</td>
                    <td className="p-3">{getStatusBadge(po.status)}</td>
                    <td className="p-3">{po.order_date ? new Date(po.order_date).toLocaleDateString() : '—'}</td>
                    <td className="p-3">
                      {(po.status === 'draft' || po.status === 'sent') && (
                        <Button size="sm" onClick={() => handleReceiveStock(po)} className="bg-green-600 hover:bg-green-700 text-white text-xs">
                          <CheckCircle className="h-3 w-3 mr-1" /> Receive
                        </Button>
                      )}
                    </td>
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
            <DialogTitle className="text-white">Edit Supplier</DialogTitle>
          </DialogHeader>
          {renderSupplierForm(handleEditSupplier, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Create PO Dialog */}
      <Dialog open={poOpen} onOpenChange={setPoOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white">Create Purchase Order - {selectedSupplier?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {poForm.items.map((item, idx) => (
              <div key={idx} className="flex gap-2 items-end">
                <div className="flex-1">
                  <label className="text-xs text-slate-400">Product</label>
                  <Input value={item.product_name} onChange={(e) => updatePOItem(idx, 'product_name', e.target.value)} placeholder="Product name" className="bg-slate-700 border-slate-600 text-white text-sm" />
                </div>
                <div className="w-20">
                  <label className="text-xs text-slate-400">Qty</label>
                  <Input type="number" value={item.quantity} onChange={(e) => updatePOItem(idx, 'quantity', parseInt(e.target.value) || 0)} className="bg-slate-700 border-slate-600 text-white text-sm" />
                </div>
                <div className="w-24">
                  <label className="text-xs text-slate-400">Price</label>
                  <Input type="number" value={item.unit_price} onChange={(e) => updatePOItem(idx, 'unit_price', parseFloat(e.target.value) || 0)} className="bg-slate-700 border-slate-600 text-white text-sm" />
                </div>
                {poForm.items.length > 1 && (
                  <Button size="sm" variant="outline" onClick={() => removePOItem(idx)} className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs mb-0.5">×</Button>
                )}
              </div>
            ))}
            <Button variant="outline" onClick={addPOItem} className="border-slate-600 text-slate-300 hover:bg-slate-700 text-sm w-full">
              + Add Item
            </Button>
            <div className="border-t border-slate-700 pt-3">
              <p className="text-slate-400 text-sm">Total: <span className="text-white font-bold">SAR {poForm.items.reduce((s, i) => s + i.quantity * i.unit_price, 0).toFixed(2)}</span></p>
            </div>
            <Button onClick={handleCreatePO} disabled={submitting || poForm.items.some((i) => !i.product_name)} className="w-full bg-blue-600 hover:bg-blue-700 text-white">
              {submitting ? t('loading') : 'Create Purchase Order'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Confirm Delete</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">
            Are you sure you want to delete <strong>{selectedSupplier?.name}</strong>?
          </p>
          <div className="flex gap-3 pt-4">
            <Button variant="outline" onClick={() => setDeleteOpen(false)} className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700">{t('cancel')}</Button>
            <Button onClick={handleDeleteSupplier} disabled={submitting} className="flex-1 bg-red-600 hover:bg-red-700 text-white">
              {submitting ? t('loading') : 'Delete'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}