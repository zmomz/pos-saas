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
import { client, receivePurchaseOrder, getBranches } from '@/lib/api';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import { useLanguage } from '@/lib/i18n';
import { Truck, Plus, Search, Package, ClipboardList, CheckCircle } from 'lucide-react';

interface Supplier {
  id: string;
  name: string;
  contact_person?: string;
  email?: string;
  phone?: string;
  payment_terms?: string;
  vat_number?: string;
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
  items_json?: string;
  order_date?: string;
  received_date?: string;
  created_at?: string;
}

// A line being received now (a partial receipt against the PO).
interface ReceiveLine {
  product_id: string;
  product_name: string;
  ordered: number;
  received: number;
  qty: number;
}

interface SupplierFormData {
  name: string;
  contact_person: string;
  email: string;
  phone: string;
  payment_terms: string;
  vat_number: string;
  address: string;
}

interface POFormData {
  supplier_id: string;
  items: { product_id: string; product_name: string; quantity: number; unit_price: number }[];
}

const emptyPOItem = { product_id: '', product_name: '', quantity: 1, unit_price: 0 };

const emptySupplierForm: SupplierFormData = {
  name: '',
  contact_person: '',
  email: '',
  phone: '',
  payment_terms: 'Net 30',
  vat_number: '',
  address: '',
};

export default function SupplierManagement() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<{ id: string; name: string }[]>([]);
  const [branches, setBranches] = useState<{ id: string; name: string }[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [search, setSearch] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [poOpen, setPoOpen] = useState(false);
  const [receiveOpen, setReceiveOpen] = useState(false);
  const [receivePO, setReceivePO] = useState<PurchaseOrder | null>(null);
  const [receiveBranchId, setReceiveBranchId] = useState('');
  const [receiveLines, setReceiveLines] = useState<ReceiveLine[]>([]);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null);
  const [formData, setFormData] = useState<SupplierFormData>(emptySupplierForm);
  const [poForm, setPoForm] = useState<POFormData>({ supplier_id: '', items: [{ ...emptyPOItem }] });
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<'suppliers' | 'orders'>('suppliers');

  const { t, isRTL } = useLanguage();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const [suppRes, poRes, prodRes, branchData] = await Promise.all([
        client.entities.suppliers.query({ query: {}, limit: 200 }),
        client.entities.purchase_orders.query({ query: {}, limit: 200 }),
        client.entities.products.query({ query: {}, limit: 500 }),
        getBranches(),
      ]);
      const suppData = suppRes.data;
      const poData = poRes.data;
      const prodData = prodRes.data;
      setSuppliers(Array.isArray(suppData?.items) ? suppData.items : Array.isArray(suppData) ? suppData : []);
      setPurchaseOrders(Array.isArray(poData?.items) ? poData.items : Array.isArray(poData) ? poData : []);
      const prodList = Array.isArray(prodData?.items) ? prodData.items : Array.isArray(prodData) ? prodData : [];
      setProducts(prodList.map((p: { id: string | number; name: string }) => ({ id: String(p.id), name: p.name })));
      const branchList = Array.isArray(branchData?.items) ? branchData.items : Array.isArray(branchData) ? branchData : [];
      setBranches(branchList.map((b: { id: string | number; name: string }) => ({ id: String(b.id), name: b.name })));
    } catch (err: unknown) {
      console.error('Failed to load supplier data:', err);
      setSuppliers([]);
      setPurchaseOrders([]);
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 403 means the account lacks access to supplier management; show the
      // in-page permission state rather than a misleading empty table (UX-02).
      if (status === 403) {
        setDenied(true);
      } else {
        // A real fetch failure must not masquerade as "no suppliers" (UX-02).
        setError(true);
      }
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
          vat_number: formData.vat_number || undefined,
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
          vat_number: formData.vat_number || undefined,
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
      vat_number: supplier.vat_number || '',
      address: supplier.address || '',
    });
    setEditOpen(true);
  }

  function openCreatePO(supplier: Supplier) {
    setSelectedSupplier(supplier);
    setPoForm({ supplier_id: supplier.id, items: [{ ...emptyPOItem }] });
    setPoOpen(true);
  }

  async function handleCreatePO() {
    setSubmitting(true);
    try {
      const totalAmount = poForm.items.reduce((sum, item) => sum + item.quantity * item.unit_price, 0);
      // Map to the real `Purchase_orders` schema: `order_number` is NOT NULL with
      // no default (so generate one), lines live in `items_json` carrying the
      // `product_id` the receive flow keys off of. The old payload's
      // supplier_name/items_count/items/order_date fields don't exist on the model.
      const itemsJson = JSON.stringify(
        poForm.items.map((item) => ({
          product_id: Number(item.product_id),
          product_name: item.product_name,
          quantity: item.quantity,
          unit_price: item.unit_price,
        })),
      );
      await client.entities.purchase_orders.create({
        data: {
          supplier_id: Number(poForm.supplier_id),
          order_number: `PO-${Date.now()}`,
          status: 'draft',
          total_amount: totalAmount,
          items_json: itemsJson,
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

  // Open the receive dialog for a PO: parse its items_json lines (only those that
  // carry a product_id are receivable into stock) and default each line's
  // receive-now quantity to its outstanding balance (ordered − already received).
  function openReceive(po: PurchaseOrder) {
    let parsed: unknown = [];
    try {
      parsed = po.items_json ? JSON.parse(po.items_json) : [];
    } catch {
      parsed = [];
    }
    const lines: ReceiveLine[] = (Array.isArray(parsed) ? parsed : [])
      .filter((l) => l && l.product_id !== undefined && l.product_id !== null)
      .map((l) => {
        const ordered = Number(l.quantity) || 0;
        const received = Number(l.received) || 0;
        return {
          product_id: String(l.product_id),
          product_name:
            l.product_name || products.find((p) => p.id === String(l.product_id))?.name || `#${l.product_id}`,
          ordered,
          received,
          qty: Math.max(0, ordered - received),
        };
      });
    setReceivePO(po);
    setReceiveLines(lines);
    setReceiveBranchId('');
    setReceiveOpen(true);
  }

  function updateReceiveQty(index: number, value: number) {
    setReceiveLines((prev) => {
      const lines = [...prev];
      lines[index] = { ...lines[index], qty: Math.max(0, value) };
      return lines;
    });
  }

  async function handleReceiveSubmit() {
    if (!receivePO) return;
    setSubmitting(true);
    try {
      // The real receive endpoint lands stock per line (keyed off product_id),
      // optionally into a branch ledger, and leaves the PO partially_received
      // when only part of a line's outstanding balance is received.
      const lines = receiveLines
        .filter((l) => l.qty > 0)
        .map((l) => ({ product_id: Number(l.product_id), quantity: l.qty }));
      const branch_id = receiveBranchId ? Number(receiveBranchId) : undefined;
      await receivePurchaseOrder(Number(receivePO.id), { branch_id, lines });
      setReceiveOpen(false);
      setReceivePO(null);
      await loadData();
    } catch (err) {
      console.error('Failed to receive stock:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function addPOItem() {
    setPoForm((prev) => ({
      ...prev,
      items: [...prev.items, { ...emptyPOItem }],
    }));
  }

  function selectPOProduct(index: number, productId: string) {
    setPoForm((prev) => {
      const items = [...prev.items];
      const name = products.find((p) => p.id === productId)?.name ?? '';
      items[index] = { ...items[index], product_id: productId, product_name: name };
      return { ...prev, items };
    });
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
      sent: 'bg-brand-500/20 text-brand-400',
      ordered: 'bg-brand-500/20 text-brand-400',
      partially_received: 'bg-amber-500/20 text-amber-400',
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
          <label className="text-sm text-slate-400 mb-1 block">{t('supplier_name')} *</label>
          <Input value={formData.name} onChange={(e) => handleFormChange('name', e.target.value)} placeholder={t('company_name')} className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">{t('contact_person')}</label>
          <Input value={formData.contact_person} onChange={(e) => handleFormChange('contact_person', e.target.value)} placeholder={t('contact_name_placeholder')} className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">{t('email')}</label>
          <Input value={formData.email} onChange={(e) => handleFormChange('email', e.target.value)} placeholder="supplier@example.com" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">{t('phone')}</label>
          <Input value={formData.phone} onChange={(e) => handleFormChange('phone', e.target.value)} placeholder="+966 5xx xxx xxxx" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">{t('payment_terms')}</label>
          <Input value={formData.payment_terms} onChange={(e) => handleFormChange('payment_terms', e.target.value)} placeholder={t('net30')} className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">{t('vat_number')}</label>
          <Input value={formData.vat_number} onChange={(e) => handleFormChange('vat_number', e.target.value)} placeholder="300000000000003" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">{t('address')}</label>
          <Input value={formData.address} onChange={(e) => handleFormChange('address', e.target.value)} placeholder={t('full_address_placeholder')} className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <Button onClick={onSubmit} disabled={submitting || !formData.name} className="w-full bg-brand-600 hover:bg-brand-700 text-white">
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

  if (denied) {
    return <PermissionDenied />;
  }

  if (error) {
    return <ErrorState message={t('suppliers_load_error')} onRetry={loadData} />;
  }

  return (
    <div className="space-y-6" dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <Truck className="h-8 w-8 text-brand-400" />
            <div>
              <p className="text-slate-400 text-sm">{t('total_suppliers')}</p>
              <p className="text-2xl font-bold text-white">{suppliers.length}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <ClipboardList className="h-8 w-8 text-amber-400" />
            <div>
              <p className="text-slate-400 text-sm">{t('pending_orders')}</p>
              <p className="text-2xl font-bold text-amber-400">
                {purchaseOrders.filter((po) => po.status === 'draft' || po.status === 'sent').length}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <CheckCircle className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-slate-400 text-sm">{t('received_this_month')}</p>
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
        <Button variant={activeTab === 'suppliers' ? 'default' : 'outline'} onClick={() => setActiveTab('suppliers')} className={activeTab === 'suppliers' ? 'bg-brand-600 text-white' : 'border-slate-600 text-slate-300'}>
          {t('suppliers')}
        </Button>
        <Button variant={activeTab === 'orders' ? 'default' : 'outline'} onClick={() => setActiveTab('orders')} className={activeTab === 'orders' ? 'bg-brand-600 text-white' : 'border-slate-600 text-slate-300'}>
          {t('purchase_orders')}
        </Button>
      </div>

      {activeTab === 'suppliers' && (
        <>
          {/* Search + Add */}
          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
            <div className="relative flex-1">
              <Search className="absolute start-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('search_suppliers')} className="ps-10 bg-slate-800 border-slate-600 text-white placeholder:text-slate-500" />
            </div>
            <Dialog open={addOpen} onOpenChange={setAddOpen}>
              <DialogTrigger asChild>
                <Button onClick={() => setFormData(emptySupplierForm)} className="bg-brand-600 hover:bg-brand-700 text-white">
                  <Plus className="h-4 w-4 me-2" /> {t('add_supplier')}
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="text-white">{t('add_new_supplier')}</DialogTitle>
                </DialogHeader>
                {renderSupplierForm(handleAddSupplier, t('add_supplier'))}
              </DialogContent>
            </Dialog>
          </div>

          {/* Suppliers Table */}
          <div className="overflow-x-auto rounded-lg border border-slate-700">
            <table className="w-full text-sm">
              <thead className="bg-slate-800">
                <tr className="text-slate-400">
                  <th className="p-3 text-start">{t('name')}</th>
                  <th className="p-3 text-start">{t('contact')}</th>
                  <th className="p-3 text-start">{t('email')}</th>
                  <th className="p-3 text-start">{t('phone')}</th>
                  <th className="p-3 text-start">{t('vat_number')}</th>
                  <th className="p-3 text-start">{t('terms')}</th>
                  <th className="p-3 text-start">{t('status')}</th>
                  <th className="p-3 text-start">{t('actions')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredSuppliers.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-slate-500">{t('no_suppliers_found')}</td>
                  </tr>
                ) : (
                  filteredSuppliers.map((supplier) => (
                    <tr key={supplier.id} className="border-t border-slate-700 text-slate-300">
                      <td className="p-3 text-white font-medium">{supplier.name}</td>
                      <td className="p-3">{supplier.contact_person || '—'}</td>
                      <td className="p-3">{supplier.email || '—'}</td>
                      <td className="p-3">{supplier.phone || '—'}</td>
                      <td className="p-3 font-mono text-xs">{supplier.vat_number || '—'}</td>
                      <td className="p-3">{supplier.payment_terms || '—'}</td>
                      <td className="p-3">{getStatusBadge(supplier.status || 'active')}</td>
                      <td className="p-3">
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => openEdit(supplier)} className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs">{t('edit')}</Button>
                          <Button size="sm" variant="outline" onClick={() => openCreatePO(supplier)} className="border-brand-600/50 text-brand-400 hover:bg-brand-600/20 text-xs">
                            <Package className="h-3 w-3 me-1" /> {t('po_short')}
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => { setSelectedSupplier(supplier); setDeleteOpen(true); }} className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs">{t('delete')}</Button>
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
                <th className="p-3 text-start">{t('order_id')}</th>
                <th className="p-3 text-start">{t('supplier')}</th>
                <th className="p-3 text-start">{t('items_label')}</th>
                <th className="p-3 text-start">{t('total')}</th>
                <th className="p-3 text-start">{t('status')}</th>
                <th className="p-3 text-start">{t('date')}</th>
                <th className="p-3 text-start">{t('actions')}</th>
              </tr>
            </thead>
            <tbody>
              {purchaseOrders.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-slate-500">{t('no_purchase_orders')}</td>
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
                      {po.status !== 'received' && po.status !== 'cancelled' && (
                        <Button size="sm" onClick={() => openReceive(po)} className="bg-green-600 hover:bg-green-700 text-white text-xs">
                          <CheckCircle className="h-3 w-3 mr-1" />
                          {po.status === 'partially_received' ? t('receive_remaining') : t('receive_po')}
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
            <DialogTitle className="text-white">{t('edit_supplier')}</DialogTitle>
          </DialogHeader>
          {renderSupplierForm(handleEditSupplier, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Create PO Dialog */}
      <Dialog open={poOpen} onOpenChange={setPoOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white">{t('create_purchase_order')} - {selectedSupplier?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {poForm.items.map((item, idx) => (
              <div key={idx} className="flex gap-2 items-end">
                <div className="flex-1">
                  <label className="text-xs text-slate-400">{t('product')}</label>
                  <select
                    value={item.product_id}
                    onChange={(e) => selectPOProduct(idx, e.target.value)}
                    className="w-full bg-slate-700 border border-slate-600 text-white rounded-md p-2 text-sm"
                  >
                    <option value="">{t('select_product')}</option>
                    {products.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div className="w-20">
                  <label className="text-xs text-slate-400">{t('qty')}</label>
                  <Input type="number" value={item.quantity} onChange={(e) => updatePOItem(idx, 'quantity', parseInt(e.target.value) || 0)} className="bg-slate-700 border-slate-600 text-white text-sm" />
                </div>
                <div className="w-24">
                  <label className="text-xs text-slate-400">{t('price')}</label>
                  <Input type="number" value={item.unit_price} onChange={(e) => updatePOItem(idx, 'unit_price', parseFloat(e.target.value) || 0)} className="bg-slate-700 border-slate-600 text-white text-sm" />
                </div>
                {poForm.items.length > 1 && (
                  <Button size="sm" variant="outline" onClick={() => removePOItem(idx)} className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs mb-0.5">×</Button>
                )}
              </div>
            ))}
            <Button variant="outline" onClick={addPOItem} className="border-slate-600 text-slate-300 hover:bg-slate-700 text-sm w-full">
              + {t('add_item')}
            </Button>
            <div className="border-t border-slate-700 pt-3">
              <p className="text-slate-400 text-sm">{t('total')}: <span className="text-white font-bold">SAR {poForm.items.reduce((s, i) => s + i.quantity * i.unit_price, 0).toFixed(2)}</span></p>
            </div>
            <Button onClick={handleCreatePO} disabled={submitting || poForm.items.some((i) => !i.product_id)} className="w-full bg-brand-600 hover:bg-brand-700 text-white">
              {submitting ? t('loading') : t('create_purchase_order')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Receive PO Dialog */}
      <Dialog open={receiveOpen} onOpenChange={setReceiveOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white">{t('receive_stock')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">{t('branch')}</label>
              <select
                value={receiveBranchId}
                onChange={(e) => setReceiveBranchId(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 text-white rounded-md p-2 text-sm"
              >
                <option value="">{t('client_level_stock')}</option>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            </div>
            {receiveLines.length === 0 ? (
              <p className="text-slate-500 text-sm">{t('no_receivable_lines')}</p>
            ) : (
              receiveLines.map((line, idx) => {
                const remaining = Math.max(0, line.ordered - line.received);
                return (
                  <div key={idx} className="flex gap-2 items-end">
                    <div className="flex-1">
                      <p className="text-white text-sm">{line.product_name}</p>
                      <p className="text-xs text-slate-400">
                        {t('ordered')}: {line.ordered} · {t('remaining')}: {remaining}
                      </p>
                    </div>
                    <div className="w-24">
                      <label className="text-xs text-slate-400">{t('receive_now')}</label>
                      <Input
                        type="number"
                        min={0}
                        max={remaining}
                        value={line.qty}
                        onChange={(e) => updateReceiveQty(idx, parseInt(e.target.value) || 0)}
                        className="bg-slate-700 border-slate-600 text-white text-sm"
                      />
                    </div>
                  </div>
                );
              })
            )}
            <Button
              onClick={handleReceiveSubmit}
              disabled={submitting || receiveLines.every((l) => l.qty <= 0)}
              className="w-full bg-green-600 hover:bg-green-700 text-white"
            >
              {submitting ? t('loading') : t('receive_stock')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">{t('confirm_delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">
            {t('delete_supplier_confirm')} <strong>{selectedSupplier?.name}</strong>?
          </p>
          <div className="flex gap-3 pt-4">
            <Button variant="outline" onClick={() => setDeleteOpen(false)} className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700">{t('cancel')}</Button>
            <Button onClick={handleDeleteSupplier} disabled={submitting} className="flex-1 bg-red-600 hover:bg-red-700 text-white">
              {submitting ? t('loading') : t('delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}