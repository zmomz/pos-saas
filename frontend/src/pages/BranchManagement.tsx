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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { client, createStockAdjustment, getBranchTransfers, setMainBranch, getProductVariants, getBranchVariantStock, setBranchVariantStock, type BranchTransfer, type StockAdjustment, type StockAdjustmentReason, type ProductVariant } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatDate } from '@/lib/format';
import { toast } from 'sonner';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
import ErrorState from '@/components/states/ErrorState';
import LoadingState from '@/components/states/LoadingState';
import { Building2, Plus, MapPin, ArrowRightLeft, Package, ClipboardList, Star, History, Layers } from 'lucide-react';

const ADJUSTMENT_REASONS: StockAdjustmentReason[] = [
  'count',
  'wastage',
  'damage',
  'correction',
  'restock',
  'other',
];

interface Branch {
  id: string;
  name: string;
  address?: string;
  manager_name?: string;
  phone?: string;
  is_active: boolean;
  is_main?: boolean;
  created_at?: string;
}

interface BranchInventory {
  product_id: string;
  product_name: string;
  quantity: number;
  branch_id: string;
}

interface BranchFormData {
  name: string;
  address: string;
  manager_name: string;
  phone: string;
}

interface TransferData {
  from_branch_id: string;
  to_branch_id: string;
  product_id: string;
  quantity: number;
}

interface ProductOption {
  id: string;
  name: string;
}

const emptyForm: BranchFormData = {
  name: '',
  address: '',
  manager_name: '',
  phone: '',
};

export default function BranchManagement() {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [inventoryOpen, setInventoryOpen] = useState(false);
  const [selectedBranch, setSelectedBranch] = useState<Branch | null>(null);
  const [branchInventory, setBranchInventory] = useState<BranchInventory[]>([]);
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [formData, setFormData] = useState<BranchFormData>(emptyForm);
  const [transferData, setTransferData] = useState<TransferData>({ from_branch_id: '', to_branch_id: '', product_id: '', quantity: 1 });
  const [transferError, setTransferError] = useState<string | null>(null);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [adjustData, setAdjustData] = useState<{ branch_id: string; product_id: string; reason: StockAdjustmentReason; counted_quantity: number; note: string }>({ branch_id: '', product_id: '', reason: 'count', counted_quantity: 0, note: '' });
  const [adjustError, setAdjustError] = useState<string | null>(null);
  const [adjustResult, setAdjustResult] = useState<StockAdjustment | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [transfers, setTransfers] = useState<BranchTransfer[]>([]);
  const [transfersLoading, setTransfersLoading] = useState(false);
  const [transfersError, setTransfersError] = useState<string | null>(null);
  const [historyFilter, setHistoryFilter] = useState('');
  // Per-branch variant stock (parity #5).
  const [variantStockOpen, setVariantStockOpen] = useState(false);
  const [variantProductId, setVariantProductId] = useState('');
  const [variants, setVariants] = useState<ProductVariant[]>([]);
  const [variantLedger, setVariantLedger] = useState<Record<number, number>>({});
  const [variantDraft, setVariantDraft] = useState<Record<number, string>>({});
  const [variantLoading, setVariantLoading] = useState(false);
  const [variantError, setVariantError] = useState(false);
  const [savingVariantId, setSavingVariantId] = useState<number | null>(null);

  const { t, tt, isRTL, language } = useLanguage();

  useEffect(() => {
    loadBranches();
    loadProducts();
  }, []);

  async function loadProducts() {
    try {
      const res = await client.entities.products.query({ query: {}, limit: 500 });
      const data = res.data;
      const list = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [];
      setProducts(list.map((p: { id: string | number; name: string }) => ({ id: String(p.id), name: p.name })));
    } catch (err) {
      console.error('Failed to load products:', err);
      setProducts([]);
    }
  }

  async function loadBranches() {
    setLoading(true);
    setLoadError(false);
    try {
      const res = await client.entities.branches.query({ query: {}, limit: 100 });
      const data = res.data;
      setBranches(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load branches:', err);
      setBranches([]);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  async function loadBranchInventory(branchId: string) {
    setInventoryLoading(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/production/branches/inventory',
        method: 'GET',
        data: { branch_id: branchId },
      });
      const data = res.data;
      setBranchInventory(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch {
      setBranchInventory([]);
    } finally {
      setInventoryLoading(false);
    }
  }

  function handleFormChange(field: keyof BranchFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddBranch() {
    setSubmitting(true);
    try {
      await client.entities.branches.create({
        data: {
          name: formData.name,
          address: formData.address || undefined,
          manager_name: formData.manager_name || undefined,
          phone: formData.phone || undefined,
          is_active: true,
        },
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadBranches();
    } catch (err) {
      console.error('Failed to create branch:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEditBranch() {
    if (!selectedBranch) return;
    setSubmitting(true);
    try {
      await client.entities.branches.update({
        id: selectedBranch.id,
        data: {
          name: formData.name,
          address: formData.address || undefined,
          manager_name: formData.manager_name || undefined,
          phone: formData.phone || undefined,
        },
      });
      setEditOpen(false);
      setSelectedBranch(null);
      setFormData(emptyForm);
      await loadBranches();
    } catch (err) {
      console.error('Failed to update branch:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSetMain(branch: Branch) {
    try {
      await setMainBranch(Number(branch.id));
      await loadBranches();
    } catch (err) {
      console.error('Failed to set main branch:', err);
    }
  }

  async function handleToggleBranch(branch: Branch) {
    try {
      await client.entities.branches.update({
        id: branch.id,
        data: { is_active: !branch.is_active },
      });
      await loadBranches();
    } catch (err) {
      console.error('Failed to toggle branch:', err);
    }
  }

  async function handleTransferStock() {
    setSubmitting(true);
    setTransferError(null);
    try {
      await client.apiCall.invoke({
        url: '/api/v1/production/branches/transfer',
        method: 'POST',
        data: {
          from_branch_id: Number(transferData.from_branch_id),
          to_branch_id: Number(transferData.to_branch_id),
          product_id: Number(transferData.product_id),
          quantity: transferData.quantity,
        },
      });
      setTransferOpen(false);
      setTransferData({ from_branch_id: '', to_branch_id: '', product_id: '', quantity: 1 });
      if (selectedBranch) {
        await loadBranchInventory(selectedBranch.id);
      }
    } catch (err) {
      console.error('Failed to transfer stock:', err);
      setTransferError(t('transfer_failed'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStockAdjust() {
    setSubmitting(true);
    setAdjustError(null);
    setAdjustResult(null);
    try {
      const result = await createStockAdjustment({
        product_id: Number(adjustData.product_id),
        branch_id: adjustData.branch_id ? Number(adjustData.branch_id) : undefined,
        reason: adjustData.reason,
        counted_quantity: adjustData.counted_quantity,
        note: adjustData.note || undefined,
      });
      setAdjustResult(result);
      // Refresh the open branch's inventory if it's the one we counted.
      if (selectedBranch && String(selectedBranch.id) === adjustData.branch_id) {
        await loadBranchInventory(selectedBranch.id);
      }
    } catch (err) {
      console.error('Failed to record stock adjustment:', err);
      setAdjustError(t('adjustment_failed'));
    } finally {
      setSubmitting(false);
    }
  }

  async function loadTransfers(branchId: string) {
    setTransfersLoading(true);
    setTransfersError(null);
    try {
      const res = await getBranchTransfers(branchId ? { branch_id: Number(branchId) } : undefined);
      setTransfers(res.items);
    } catch (err) {
      console.error('Failed to load transfer history:', err);
      setTransfersError(t('transfer_load_failed'));
      setTransfers([]);
    } finally {
      setTransfersLoading(false);
    }
  }

  function openHistory() {
    setHistoryFilter('');
    setHistoryOpen(true);
    loadTransfers('');
  }

  function handleHistoryFilter(branchId: string) {
    setHistoryFilter(branchId);
    loadTransfers(branchId);
  }

  function branchName(id: number) {
    return branches.find((b) => String(b.id) === String(id))?.name ?? `#${id}`;
  }

  function openEdit(branch: Branch) {
    setSelectedBranch(branch);
    setFormData({
      name: branch.name,
      address: branch.address || '',
      manager_name: branch.manager_name || '',
      phone: branch.phone || '',
    });
    setEditOpen(true);
  }

  function openInventory(branch: Branch) {
    setSelectedBranch(branch);
    loadBranchInventory(branch.id);
    setInventoryOpen(true);
  }

  function openVariantStock(branch: Branch) {
    setSelectedBranch(branch);
    setVariantProductId('');
    setVariants([]);
    setVariantLedger({});
    setVariantDraft({});
    setVariantError(false);
    setVariantStockOpen(true);
  }

  // Load the picked product's variants plus this branch's per-variant ledger,
  // then seed each row's editable quantity (variants with no row default to 0).
  async function loadVariantStock(branch: Branch, productId: string) {
    setVariantLoading(true);
    setVariantError(false);
    try {
      const [vs, ledger] = await Promise.all([
        getProductVariants(Number(productId)),
        getBranchVariantStock(Number(branch.id)),
      ]);
      const byId: Record<number, number> = {};
      for (const it of ledger.items || []) byId[it.variant_id] = it.quantity;
      setVariants(vs);
      setVariantLedger(byId);
      setVariantDraft(Object.fromEntries(vs.map((v) => [v.id, String(byId[v.id] ?? 0)])));
    } catch (err) {
      console.error('Failed to load variant stock:', err);
      setVariantError(true);
      setVariants([]);
    } finally {
      setVariantLoading(false);
    }
  }

  function handleVariantProductChange(productId: string) {
    setVariantProductId(productId);
    if (selectedBranch && productId) loadVariantStock(selectedBranch, productId);
  }

  async function handleSaveVariantStock(variant: ProductVariant) {
    if (!selectedBranch) return;
    const raw = variantDraft[variant.id];
    const quantity = parseInt(raw, 10);
    if (Number.isNaN(quantity) || quantity < 0) return;
    setSavingVariantId(variant.id);
    try {
      await setBranchVariantStock(Number(selectedBranch.id), variant.id, quantity);
      setVariantLedger((m) => ({ ...m, [variant.id]: quantity }));
      toast.success(t('stock_saved'));
    } catch (err) {
      console.error('Failed to save variant stock:', err);
      toast.error(t('action_failed'));
    } finally {
      setSavingVariantId(null);
    }
  }

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">{tt('branch_name', 'Branch Name')} *</label>
          <Input value={formData.name} onChange={(e) => handleFormChange('name', e.target.value)} placeholder={tt('branch_name_placeholder', 'Main Branch')} className="bg-muted border-input text-foreground" />
        </div>
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">{tt('address', 'Address')}</label>
          <Input value={formData.address} onChange={(e) => handleFormChange('address', e.target.value)} placeholder={tt('branch_address_placeholder', 'Branch address')} className="bg-muted border-input text-foreground" />
        </div>
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">{tt('manager_name', 'Manager Name')}</label>
          <Input value={formData.manager_name} onChange={(e) => handleFormChange('manager_name', e.target.value)} placeholder={tt('branch_manager_placeholder', 'Branch manager')} className="bg-muted border-input text-foreground" />
        </div>
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">{tt('phone', 'Phone')}</label>
          <Input value={formData.phone} onChange={(e) => handleFormChange('phone', e.target.value)} placeholder="+966 xxx xxxx" className="bg-muted border-input text-foreground" />
        </div>
        <Button onClick={onSubmit} disabled={submitting || !formData.name} className="w-full shadow-brand">
          {submitting ? t('loading') : submitLabel}
        </Button>
      </div>
    );
  }

  if (loading) return <LoadingState message={t('loading')} />;

  return (
    <div className="animate-fade-up space-y-6" dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Header */}
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Building2 className="h-[18px] w-[18px]" /></span>}
        title={tt('branch_management', 'Branch Management')}
        subtitle={tt('branch_management_desc', 'Manage your business locations and inventory')}
      >
        <Button onClick={() => { setAdjustError(null); setAdjustResult(null); setAdjustData({ branch_id: '', product_id: '', reason: 'count', counted_quantity: 0, note: '' }); setAdjustOpen(true); }} variant="outline" className="h-11 rounded-[10px] border-input text-foreground/90 hover:bg-muted">
          <ClipboardList className="h-4 w-4 me-2" /> {t('stock_count')}
        </Button>
        <Button onClick={() => { setTransferError(null); setTransferOpen(true); }} variant="outline" className="h-11 rounded-[10px] border-input text-foreground/90 hover:bg-muted">
          <ArrowRightLeft className="h-4 w-4 me-2" /> {t('transfer_stock')}
        </Button>
        <Button onClick={openHistory} variant="outline" className="h-11 rounded-[10px] border-input text-foreground/90 hover:bg-muted">
          <History className="h-4 w-4 me-2" /> {t('transfer_history')}
        </Button>
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button onClick={() => setFormData(emptyForm)} className="h-11 rounded-[10px] shadow-brand">
              <Plus className="h-4 w-4 me-2" /> {tt('add_branch', 'Add Branch')}
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-card border-border text-foreground max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-foreground">{tt('add_new_branch', 'Add New Branch')}</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddBranch, tt('create_branch', 'Create Branch'))}
          </DialogContent>
        </Dialog>
      </PageHeading>

      {/* Branch Cards — a failed load shows an error+retry, never "no branches" */}
      {loadError ? (
        <ErrorState message={t('branches_load_error')} onRetry={loadBranches} />
      ) : (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {branches.length === 0 ? (
          <Card className="bg-card border-border col-span-full">
            <CardContent className="p-8 text-center">
              <Building2 className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
              <p className="text-muted-foreground">{tt('no_branches_configured', 'No branches configured. Add your first branch.')}</p>
            </CardContent>
          </Card>
        ) : (
          branches.map((branch) => (
            <Card key={branch.id} className="bg-card border-border">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-foreground text-lg">{branch.name}</CardTitle>
                  <div className="flex items-center gap-2">
                    {branch.is_main && (
                      <Badge className="pill-sky flex items-center gap-1">
                        <Star className="h-3 w-3 fill-current" /> {t('main_branch')}
                      </Badge>
                    )}
                    <Badge className={branch.is_active ? 'pill-success' : 'pill-danger'}>
                      {branch.is_active ? tt('active', 'Active') : tt('inactive', 'Inactive')}
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {branch.address && (
                  <div className="flex items-center gap-2 text-muted-foreground text-sm">
                    <MapPin className="h-4 w-4" />
                    <span>{branch.address}</span>
                  </div>
                )}
                {branch.manager_name && (
                  <p className="text-muted-foreground text-sm">{tt('manager', 'Manager')}: <span className="text-foreground">{branch.manager_name}</span></p>
                )}
                {branch.phone && (
                  <p className="text-muted-foreground text-sm">{tt('phone', 'Phone')}: <span className="text-foreground">{branch.phone}</span></p>
                )}
                <div className="flex gap-2 pt-2">
                  <Button size="sm" variant="outline" onClick={() => openInventory(branch)} className="border-input text-foreground/90 hover:bg-muted text-xs flex-1">
                    <Package className="h-3 w-3 me-1" /> {tt('inventory', 'Inventory')}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => openVariantStock(branch)} className="border-input text-foreground/90 hover:bg-muted text-xs flex-1">
                    <Layers className="h-3 w-3 me-1" /> {t('variant_stock')}
                  </Button>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => openEdit(branch)} className="border-input text-foreground/90 hover:bg-muted text-xs flex-1">
                    {tt('edit', 'Edit')}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleToggleBranch(branch)} className={branch.is_active ? 'border-danger/50 text-danger hover:bg-danger/10 text-xs flex-1' : 'border-success/50 text-success hover:bg-success/10 text-xs flex-1'}>
                    {branch.is_active ? tt('disable', 'Disable') : tt('enable', 'Enable')}
                  </Button>
                </div>
                {!branch.is_main && (
                  <Button size="sm" variant="outline" onClick={() => handleSetMain(branch)} className="w-full border-brand/50 text-brand hover:bg-brand/10 text-xs">
                    <Star className="h-3 w-3 me-1" /> {t('set_as_main')}
                  </Button>
                )}
              </CardContent>
            </Card>
          ))
        )}
      </div>
      )}

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-card border-border text-foreground max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground">{tt('edit_branch', 'Edit Branch')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditBranch, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Inventory Dialog */}
      <Dialog open={inventoryOpen} onOpenChange={setInventoryOpen}>
        <DialogContent className="bg-card border-border text-foreground max-h-[90vh] overflow-y-auto max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-foreground">{tt('inventory', 'Inventory')} - {selectedBranch?.name}</DialogTitle>
          </DialogHeader>
          {inventoryLoading ? (
            <div className="text-center py-8 text-muted-foreground">{t('loading')}</div>
          ) : branchInventory.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">{tt('no_inventory_data', 'No inventory data for this branch')}</div>
          ) : (
            <div className="rounded-lg border border-border">
              <DataTable
                className="text-sm"
                columns={[
                  {
                    key: 'product',
                    header: tt('product', 'Product'),
                    cell: (item) => <span className="text-foreground">{item.product_name}</span>,
                  },
                  {
                    key: 'quantity',
                    header: tt('quantity', 'Quantity'),
                    cell: (item) => (
                      <Badge className={item.quantity > 10 ? 'pill-success' : item.quantity > 0 ? 'pill-warning' : 'pill-danger'}>
                        {item.quantity}
                      </Badge>
                    ),
                  },
                ] satisfies DataTableColumn<BranchInventory>[]}
                rows={branchInventory}
                rowKey={(_item, idx) => idx}
              />
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Variant Stock Dialog (parity #5) */}
      <Dialog open={variantStockOpen} onOpenChange={setVariantStockOpen}>
        <DialogContent className="bg-card border-border text-foreground max-h-[90vh] overflow-y-auto max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('variant_stock')} - {selectedBranch?.name}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t('variant_stock_desc')}</p>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('product')}</label>
              <Select value={variantProductId} onValueChange={handleVariantProductChange}>
                <SelectTrigger className="bg-muted border-input text-foreground">
                  <SelectValue placeholder={t('select_product')} />
                </SelectTrigger>
                <SelectContent className="bg-card border-input">
                  {products.map((p) => (
                    <SelectItem key={p.id} value={p.id} className="text-foreground hover:bg-muted">{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {!variantProductId ? (
              <div className="text-center py-8 text-muted-foreground text-sm">{t('select_product_first')}</div>
            ) : variantLoading ? (
              <LoadingState className="py-8" />
            ) : variantError ? (
              <div className="text-center py-8">
                <p className="text-foreground/90 mb-3">{t('variant_stock_load_error')}</p>
                <Button variant="outline" onClick={() => selectedBranch && loadVariantStock(selectedBranch, variantProductId)} className="border-input text-foreground/90 hover:bg-muted">
                  {t('retry')}
                </Button>
              </div>
            ) : variants.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">{t('no_variants_for_product')}</div>
            ) : (
              <div className="rounded-lg border border-border">
                <DataTable
                  className="text-sm"
                  columns={[
                    {
                      key: 'variant',
                      header: t('variant'),
                      cell: (v) => (
                        <div>
                          <span className="text-foreground">{v.name}</span>
                          {v.sku && <span className="block text-xs text-muted-foreground">{v.sku}</span>}
                        </div>
                      ),
                    },
                    {
                      key: 'stock',
                      header: t('branch_quantity'),
                      align: 'end',
                      cell: (v) => {
                        const draft = variantDraft[v.id] ?? '';
                        const dirty = draft.trim() !== '' && parseInt(draft, 10) !== (variantLedger[v.id] ?? 0);
                        return (
                          <div className="flex items-center justify-end gap-2">
                            <Input
                              type="number"
                              min={0}
                              value={draft}
                              onChange={(e) => setVariantDraft((m) => ({ ...m, [v.id]: e.target.value }))}
                              className="bg-muted border-input text-foreground w-24 text-end"
                            />
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleSaveVariantStock(v)}
                              disabled={!dirty || savingVariantId === v.id}
                              className="border-input text-foreground/90 hover:bg-muted shrink-0"
                            >
                              {savingVariantId === v.id ? t('loading') : t('save')}
                            </Button>
                          </div>
                        );
                      },
                    },
                  ] satisfies DataTableColumn<ProductVariant>[]}
                  rows={variants}
                  rowKey={(v) => v.id}
                />
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Transfer Dialog */}
      <Dialog open={transferOpen} onOpenChange={setTransferOpen}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('transfer_stock')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('from_branch')}</label>
              <Select
                value={transferData.from_branch_id}
                onValueChange={(v) => setTransferData((d) => ({ ...d, from_branch_id: v }))}
              >
                <SelectTrigger className="bg-muted border-input text-foreground">
                  <SelectValue placeholder={t('select_branch')} />
                </SelectTrigger>
                <SelectContent className="bg-card border-input">
                  {branches.filter((b) => b.is_active).map((b) => (
                    <SelectItem key={b.id} value={b.id} className="text-foreground hover:bg-muted">{b.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('to_branch')}</label>
              <Select
                value={transferData.to_branch_id}
                onValueChange={(v) => setTransferData((d) => ({ ...d, to_branch_id: v }))}
              >
                <SelectTrigger className="bg-muted border-input text-foreground">
                  <SelectValue placeholder={t('select_branch')} />
                </SelectTrigger>
                <SelectContent className="bg-card border-input">
                  {branches.filter((b) => b.is_active && b.id !== transferData.from_branch_id).map((b) => (
                    <SelectItem key={b.id} value={b.id} className="text-foreground hover:bg-muted">{b.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('product')}</label>
              <Select
                value={transferData.product_id}
                onValueChange={(v) => setTransferData((d) => ({ ...d, product_id: v }))}
              >
                <SelectTrigger className="bg-muted border-input text-foreground">
                  <SelectValue placeholder={t('select_product')} />
                </SelectTrigger>
                <SelectContent className="bg-card border-input">
                  {products.map((p) => (
                    <SelectItem key={p.id} value={p.id} className="text-foreground hover:bg-muted">{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('quantity')}</label>
              <Input type="number" value={transferData.quantity} onChange={(e) => setTransferData((d) => ({ ...d, quantity: parseInt(e.target.value) || 0 }))} className="bg-muted border-input text-foreground" />
            </div>
            {transferError && (
              <p role="alert" className="text-sm text-danger">{transferError}</p>
            )}
            <Button
              onClick={handleTransferStock}
              disabled={submitting || !transferData.from_branch_id || !transferData.to_branch_id || !transferData.product_id || transferData.quantity <= 0}
              className="w-full shadow-brand"
            >
              {submitting ? t('loading') : t('transfer_stock')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Transfer History Dialog (ISSUE-060) */}
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="bg-card border-border text-foreground max-h-[90vh] overflow-y-auto max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('transfer_history')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('branch')}</label>
              <Select
                value={historyFilter === '' ? '__all__' : historyFilter}
                onValueChange={(v) => handleHistoryFilter(v === '__all__' ? '' : v)}
              >
                <SelectTrigger className="bg-muted border-input text-foreground">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-input">
                  <SelectItem value="__all__" className="text-foreground hover:bg-muted">{t('all_branches')}</SelectItem>
                  {branches.map((b) => (
                    <SelectItem key={b.id} value={b.id} className="text-foreground hover:bg-muted">{b.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {transfersError ? (
              <p role="alert" className="text-sm text-danger">{transfersError}</p>
            ) : transfersLoading ? (
              <div className="text-center py-8 text-muted-foreground">{t('loading')}</div>
            ) : transfers.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">{t('transfer_history_empty')}</div>
            ) : (
              <div className="rounded-lg border border-border">
                <DataTable
                  className="text-sm"
                  columns={[
                    {
                      key: 'date',
                      header: t('date'),
                      cell: (tr) => <span className="whitespace-nowrap tabular-nums">{tr.created_at ? formatDate(tr.created_at, language) : '—'}</span>,
                    },
                    { key: 'from', header: t('from_branch'), cell: (tr) => branchName(tr.from_branch_id) },
                    { key: 'to', header: t('to_branch'), cell: (tr) => branchName(tr.to_branch_id) },
                    {
                      key: 'product',
                      header: t('product'),
                      cell: (tr) => <span className="text-foreground">{tr.product_name ?? `#${tr.product_id}`}</span>,
                    },
                    { key: 'quantity', header: t('quantity'), cell: (tr) => tr.quantity },
                    { key: 'status', header: t('status'), cell: (tr) => <Badge className="pill-sky">{tr.status}</Badge> },
                  ] satisfies DataTableColumn<BranchTransfer>[]}
                  rows={transfers}
                  rowKey={(tr) => tr.id}
                />
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Stock Count / Adjustment Dialog (INV-06) */}
      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{t('stock_count')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-xs text-muted-foreground">{t('stock_count_hint')}</p>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('product')}</label>
              <Select
                value={adjustData.product_id}
                onValueChange={(v) => setAdjustData((d) => ({ ...d, product_id: v }))}
              >
                <SelectTrigger className="bg-muted border-input text-foreground">
                  <SelectValue placeholder={t('select_product')} />
                </SelectTrigger>
                <SelectContent className="bg-card border-input">
                  {products.map((p) => (
                    <SelectItem key={p.id} value={p.id} className="text-foreground hover:bg-muted">{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('branch')}</label>
              <Select
                value={adjustData.branch_id === '' ? '__client__' : adjustData.branch_id}
                onValueChange={(v) => setAdjustData((d) => ({ ...d, branch_id: v === '__client__' ? '' : v }))}
              >
                <SelectTrigger className="bg-muted border-input text-foreground">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-input">
                  <SelectItem value="__client__" className="text-foreground hover:bg-muted">{t('client_level_stock')}</SelectItem>
                  {branches.filter((b) => b.is_active).map((b) => (
                    <SelectItem key={b.id} value={b.id} className="text-foreground hover:bg-muted">{b.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('reason')}</label>
              <Select
                value={adjustData.reason}
                onValueChange={(v) => setAdjustData((d) => ({ ...d, reason: v as StockAdjustmentReason }))}
              >
                <SelectTrigger className="bg-muted border-input text-foreground">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-input">
                  {ADJUSTMENT_REASONS.map((r) => (
                    <SelectItem key={r} value={r} className="text-foreground hover:bg-muted">{t(`reason_${r}`)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('counted_quantity')}</label>
              <Input type="number" min={0} value={adjustData.counted_quantity} onChange={(e) => setAdjustData((d) => ({ ...d, counted_quantity: parseInt(e.target.value) || 0 }))} className="bg-muted border-input text-foreground" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-1 block">{t('adjustment_note')}</label>
              <Input value={adjustData.note} onChange={(e) => setAdjustData((d) => ({ ...d, note: e.target.value }))} className="bg-muted border-input text-foreground" />
            </div>
            {adjustResult && (
              <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm">
                <div className="flex justify-between text-muted-foreground"><span>{t('system_quantity')}</span><span className="text-foreground">{adjustResult.system_quantity}</span></div>
                <div className="flex justify-between text-muted-foreground"><span>{t('counted_quantity')}</span><span className="text-foreground">{adjustResult.counted_quantity}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">{t('variance')}</span>
                  <Badge className={adjustResult.variance === 0 ? 'pill-muted' : adjustResult.variance > 0 ? 'pill-success' : 'pill-danger'}>
                    {adjustResult.variance > 0 ? `+${adjustResult.variance}` : adjustResult.variance}
                  </Badge>
                </div>
              </div>
            )}
            {adjustError && (
              <p role="alert" className="text-sm text-danger">{adjustError}</p>
            )}
            <Button
              onClick={handleStockAdjust}
              disabled={submitting || !adjustData.product_id}
              className="w-full shadow-brand"
            >
              {submitting ? t('loading') : t('adjust_stock')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}