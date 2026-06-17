import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import PageHeading from '@/components/dashboard/rx/PageHeading';
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
import StatTile from '@/components/dashboard/StatTile';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
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

  const { t, isRTL, language } = useLanguage();

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
    const classes: Record<string, string> = {
      draft: 'pill-muted',
      sent: 'pill-sky',
      ordered: 'pill-sky',
      partially_received: 'pill-warning',
      received: 'pill-success',
      cancelled: 'pill-danger',
      active: 'pill-success',
      inactive: 'pill-danger',
    };
    return <span className={classes[status] || 'pill-muted'}>{status}</span>;
  }

  function renderSupplierForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <Label className="mb-1 block">{t('supplier_name')} *</Label>
          <Input value={formData.name} onChange={(e) => handleFormChange('name', e.target.value)} placeholder={t('company_name')} />
        </div>
        <div>
          <Label className="mb-1 block">{t('contact_person')}</Label>
          <Input value={formData.contact_person} onChange={(e) => handleFormChange('contact_person', e.target.value)} placeholder={t('contact_name_placeholder')} />
        </div>
        <div>
          <Label className="mb-1 block">{t('email')}</Label>
          <Input value={formData.email} onChange={(e) => handleFormChange('email', e.target.value)} placeholder="supplier@example.com" />
        </div>
        <div>
          <Label className="mb-1 block">{t('phone')}</Label>
          <Input value={formData.phone} onChange={(e) => handleFormChange('phone', e.target.value)} placeholder="+966 5xx xxx xxxx" />
        </div>
        <div>
          <Label className="mb-1 block">{t('payment_terms')}</Label>
          <Input value={formData.payment_terms} onChange={(e) => handleFormChange('payment_terms', e.target.value)} placeholder={t('net30')} />
        </div>
        <div>
          <Label className="mb-1 block">{t('vat_number')}</Label>
          <Input value={formData.vat_number} onChange={(e) => handleFormChange('vat_number', e.target.value)} placeholder="300000000000003" />
        </div>
        <div>
          <Label className="mb-1 block">{t('address')}</Label>
          <Input value={formData.address} onChange={(e) => handleFormChange('address', e.target.value)} placeholder={t('full_address_placeholder')} />
        </div>
        <Button onClick={onSubmit} disabled={submitting || !formData.name} className="w-full">
          {submitting ? t('loading') : submitLabel}
        </Button>
      </div>
    );
  }

  const supplierColumns: DataTableColumn<Supplier>[] = [
    {
      key: 'name',
      header: t('name'),
      cell: (supplier) => <span className="text-foreground font-medium">{supplier.name}</span>,
    },
    { key: 'contact', header: t('contact'), cell: (supplier) => supplier.contact_person || '—' },
    { key: 'email', header: t('email'), cell: (supplier) => supplier.email || '—' },
    { key: 'phone', header: t('phone'), cell: (supplier) => supplier.phone || '—' },
    {
      key: 'vat',
      header: t('vat_number'),
      cell: (supplier) => <span className="font-mono text-xs">{supplier.vat_number || '—'}</span>,
    },
    { key: 'terms', header: t('terms'), cell: (supplier) => supplier.payment_terms || '—' },
    { key: 'status', header: t('status'), cell: (supplier) => getStatusBadge(supplier.status || 'active') },
    {
      key: 'actions',
      header: t('actions'),
      cell: (supplier) => (
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => openEdit(supplier)} className="text-xs">{t('edit')}</Button>
          <Button size="sm" variant="outline" onClick={() => openCreatePO(supplier)} className="text-xs">
            <Package className="h-3 w-3 me-1" /> {t('po_short')}
          </Button>
          <Button size="sm" variant="destructive" onClick={() => { setSelectedSupplier(supplier); setDeleteOpen(true); }} className="text-xs">{t('delete')}</Button>
        </div>
      ),
    },
  ];

  const orderColumns: DataTableColumn<PurchaseOrder>[] = [
    {
      key: 'order_id',
      header: t('order_id'),
      cell: (po) => <span className="text-foreground font-mono text-xs">#{po.id.slice(0, 8)}</span>,
    },
    { key: 'supplier', header: t('supplier'), cell: (po) => po.supplier_name || '—' },
    { key: 'items', header: t('items_label'), cell: (po) => po.items_count },
    {
      key: 'total',
      header: t('total'),
      cell: (po) => <span className="text-foreground font-medium tabular-nums">{formatMoney(po.total_amount || 0, language)}</span>,
    },
    { key: 'status', header: t('status'), cell: (po) => getStatusBadge(po.status) },
    {
      key: 'date',
      header: t('date'),
      cell: (po) => (po.order_date ? new Date(po.order_date).toLocaleDateString() : '—'),
    },
    {
      key: 'actions',
      header: t('actions'),
      cell: (po) =>
        po.status !== 'received' && po.status !== 'cancelled' ? (
          <Button size="sm" variant="success" onClick={() => openReceive(po)} className="text-xs">
            <CheckCircle className="h-3 w-3 me-1" />
            {po.status === 'partially_received' ? t('receive_remaining') : t('receive_po')}
          </Button>
        ) : null,
    },
  ];

  if (loading && suppliers.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-foreground animate-pulse">{t('loading')}</div>
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
    <div className="animate-fade-up space-y-6" dir={isRTL ? 'rtl' : 'ltr'}>
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <PageHeading
          icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Truck className="h-[18px] w-[18px]" /></span>}
          title={t('suppliers')}
          subtitle={`${suppliers.length} ${t('total_suppliers')}`}
        >
          <DialogTrigger asChild>
            <Button onClick={() => setFormData(emptySupplierForm)} className="h-11 rounded-[10px] shadow-brand">
              <Plus className="h-4 w-4" /> {t('add_supplier')}
            </Button>
          </DialogTrigger>
        </PageHeading>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('add_new_supplier')}</DialogTitle>
          </DialogHeader>
          {renderSupplierForm(handleAddSupplier, t('add_supplier'))}
        </DialogContent>
      </Dialog>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile icon={Truck} label={t('total_suppliers')} value={suppliers.length} tone="brand" />
        <StatTile
          icon={ClipboardList}
          label={t('pending_orders')}
          value={purchaseOrders.filter((po) => po.status === 'draft' || po.status === 'sent').length}
          tone="warning"
        />
        <StatTile
          icon={CheckCircle}
          label={t('received_this_month')}
          value={purchaseOrders.filter((po) => {
            if (po.status !== 'received' || !po.received_date) return false;
            const d = new Date(po.received_date);
            const now = new Date();
            return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
          }).length}
          tone="success"
        />
      </div>

      {/* Tabs */}
      <div className="dxr-seg">
        <button data-active={activeTab === 'suppliers'} onClick={() => setActiveTab('suppliers')}>
          {t('suppliers')}
        </button>
        <button data-active={activeTab === 'orders'} onClick={() => setActiveTab('orders')}>
          {t('purchase_orders')}
        </button>
      </div>

      {activeTab === 'suppliers' && (
        <>
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute start-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('search_suppliers')} className="ps-10" />
          </div>

          {/* Suppliers Table */}
          <DataTable
            className="rounded-lg border border-border"
            columns={supplierColumns}
            rows={filteredSuppliers}
            rowKey={(supplier) => supplier.id}
            empty={t('no_suppliers_found')}
          />
        </>
      )}

      {activeTab === 'orders' && (
        <DataTable
          className="rounded-lg border border-border"
          columns={orderColumns}
          rows={purchaseOrders}
          rowKey={(po) => po.id}
          empty={t('no_purchase_orders')}
        />
      )}

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('edit_supplier')}</DialogTitle>
          </DialogHeader>
          {renderSupplierForm(handleEditSupplier, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Create PO Dialog */}
      <Dialog open={poOpen} onOpenChange={setPoOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('create_purchase_order')} - {selectedSupplier?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {poForm.items.map((item, idx) => (
              <div key={idx} className="flex gap-2 items-end">
                <div className="flex-1">
                  <Label className="text-xs">{t('product')}</Label>
                  <Select value={item.product_id || undefined} onValueChange={(v) => selectPOProduct(idx, v)}>
                    <SelectTrigger className="text-sm">
                      <SelectValue placeholder={t('select_product')} />
                    </SelectTrigger>
                    <SelectContent>
                      {products.map((p) => (
                        <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="w-20">
                  <Label className="text-xs">{t('qty')}</Label>
                  <Input type="number" value={item.quantity} onChange={(e) => updatePOItem(idx, 'quantity', parseInt(e.target.value) || 0)} className="text-sm" />
                </div>
                <div className="w-24">
                  <Label className="text-xs">{t('price')}</Label>
                  <Input type="number" value={item.unit_price} onChange={(e) => updatePOItem(idx, 'unit_price', parseFloat(e.target.value) || 0)} className="text-sm" />
                </div>
                {poForm.items.length > 1 && (
                  <Button size="sm" variant="destructive" onClick={() => removePOItem(idx)} className="text-xs mb-0.5">×</Button>
                )}
              </div>
            ))}
            <Button variant="outline" onClick={addPOItem} className="text-sm w-full">
              <Plus className="h-4 w-4 me-1" /> {t('add_item')}
            </Button>
            <div className="border-t border-border pt-3">
              <p className="text-muted-foreground text-sm">{t('total')}: <span className="text-foreground font-bold tabular-nums">{formatMoney(poForm.items.reduce((s, i) => s + i.quantity * i.unit_price, 0), language)}</span></p>
            </div>
            <Button onClick={handleCreatePO} disabled={submitting || poForm.items.some((i) => !i.product_id)} className="w-full">
              {submitting ? t('loading') : t('create_purchase_order')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Receive PO Dialog */}
      <Dialog open={receiveOpen} onOpenChange={setReceiveOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('receive_stock')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-xs mb-1 block">{t('branch')}</Label>
              <Select value={receiveBranchId || undefined} onValueChange={(v) => setReceiveBranchId(v)}>
                <SelectTrigger className="text-sm">
                  <SelectValue placeholder={t('client_level_stock')} />
                </SelectTrigger>
                <SelectContent>
                  {branches.map((b) => (
                    <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {receiveLines.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('no_receivable_lines')}</p>
            ) : (
              receiveLines.map((line, idx) => {
                const remaining = Math.max(0, line.ordered - line.received);
                return (
                  <div key={idx} className="flex gap-2 items-end">
                    <div className="flex-1">
                      <p className="text-foreground text-sm">{line.product_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {t('ordered')}: {line.ordered} · {t('remaining')}: {remaining}
                      </p>
                    </div>
                    <div className="w-24">
                      <Label className="text-xs">{t('receive_now')}</Label>
                      <Input
                        type="number"
                        min={0}
                        max={remaining}
                        value={line.qty}
                        onChange={(e) => updateReceiveQty(idx, parseInt(e.target.value) || 0)}
                        className="text-sm"
                      />
                    </div>
                  </div>
                );
              })
            )}
            <Button
              onClick={handleReceiveSubmit}
              variant="success"
              disabled={submitting || receiveLines.every((l) => l.qty <= 0)}
              className="w-full"
            >
              {submitting ? t('loading') : t('receive_stock')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('confirm_delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-foreground/90">
            {t('delete_supplier_confirm')} <strong>{selectedSupplier?.name}</strong>?
          </p>
          <div className="flex gap-3 pt-4">
            <Button variant="outline" onClick={() => setDeleteOpen(false)} className="flex-1">{t('cancel')}</Button>
            <Button variant="destructive" onClick={handleDeleteSupplier} disabled={submitting} className="flex-1">
              {submitting ? t('loading') : t('delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}