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
import { Building2, Plus, MapPin, ArrowRightLeft, Package } from 'lucide-react';

interface Branch {
  id: string;
  name: string;
  address?: string;
  manager_name?: string;
  phone?: string;
  is_active: boolean;
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
  const [submitting, setSubmitting] = useState(false);
  const [inventoryLoading, setInventoryLoading] = useState(false);

  const { t } = useLanguage();

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
    try {
      const res = await client.entities.branches.query({ query: {}, limit: 100 });
      const data = res.data;
      setBranches(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load branches:', err);
      setBranches([]);
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

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Branch Name *</label>
          <Input value={formData.name} onChange={(e) => handleFormChange('name', e.target.value)} placeholder="Main Branch" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Address</label>
          <Input value={formData.address} onChange={(e) => handleFormChange('address', e.target.value)} placeholder="Branch address" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Manager Name</label>
          <Input value={formData.manager_name} onChange={(e) => handleFormChange('manager_name', e.target.value)} placeholder="Branch manager" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Phone</label>
          <Input value={formData.phone} onChange={(e) => handleFormChange('phone', e.target.value)} placeholder="+966 xxx xxxx" className="bg-slate-700 border-slate-600 text-white" />
        </div>
        <Button onClick={onSubmit} disabled={submitting || !formData.name} className="w-full bg-blue-600 hover:bg-blue-700 text-white">
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
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Building2 className="h-6 w-6 text-blue-400" />
            Branch Management
          </h2>
          <p className="text-slate-400 text-sm mt-1">Manage your business locations and inventory</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => { setTransferError(null); setTransferOpen(true); }} variant="outline" className="border-slate-600 text-slate-300 hover:bg-slate-700">
            <ArrowRightLeft className="h-4 w-4 mr-2" /> {t('transfer_stock')}
          </Button>
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button onClick={() => setFormData(emptyForm)} className="bg-blue-600 hover:bg-blue-700 text-white">
                <Plus className="h-4 w-4 mr-2" /> Add Branch
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle className="text-white">Add New Branch</DialogTitle>
              </DialogHeader>
              {renderForm(handleAddBranch, 'Create Branch')}
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Branch Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {branches.length === 0 ? (
          <Card className="bg-slate-800 border-slate-700 col-span-full">
            <CardContent className="p-8 text-center">
              <Building2 className="h-12 w-12 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-400">No branches configured. Add your first branch.</p>
            </CardContent>
          </Card>
        ) : (
          branches.map((branch) => (
            <Card key={branch.id} className="bg-slate-800 border-slate-700">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-white text-lg">{branch.name}</CardTitle>
                  <Badge className={branch.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}>
                    {branch.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {branch.address && (
                  <div className="flex items-center gap-2 text-slate-400 text-sm">
                    <MapPin className="h-4 w-4" />
                    <span>{branch.address}</span>
                  </div>
                )}
                {branch.manager_name && (
                  <p className="text-slate-400 text-sm">Manager: <span className="text-white">{branch.manager_name}</span></p>
                )}
                {branch.phone && (
                  <p className="text-slate-400 text-sm">Phone: <span className="text-white">{branch.phone}</span></p>
                )}
                <div className="flex gap-2 pt-2">
                  <Button size="sm" variant="outline" onClick={() => openInventory(branch)} className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs flex-1">
                    <Package className="h-3 w-3 mr-1" /> Inventory
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => openEdit(branch)} className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs">
                    Edit
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleToggleBranch(branch)} className={branch.is_active ? 'border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs' : 'border-green-600/50 text-green-400 hover:bg-green-600/20 text-xs'}>
                    {branch.is_active ? 'Disable' : 'Enable'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-white">Edit Branch</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditBranch, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Inventory Dialog */}
      <Dialog open={inventoryOpen} onOpenChange={setInventoryOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white">Inventory - {selectedBranch?.name}</DialogTitle>
          </DialogHeader>
          {inventoryLoading ? (
            <div className="text-center py-8 text-slate-400">{t('loading')}</div>
          ) : branchInventory.length === 0 ? (
            <div className="text-center py-8 text-slate-500">No inventory data for this branch</div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-700">
              <table className="w-full text-sm">
                <thead className="bg-slate-700/50">
                  <tr className="text-slate-400">
                    <th className="p-2 text-start">Product</th>
                    <th className="p-2 text-start">Quantity</th>
                  </tr>
                </thead>
                <tbody>
                  {branchInventory.map((item, idx) => (
                    <tr key={idx} className="border-t border-slate-700 text-slate-300">
                      <td className="p-2 text-white">{item.product_name}</td>
                      <td className="p-2">
                        <Badge className={item.quantity > 10 ? 'bg-green-500/20 text-green-400' : item.quantity > 0 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400'}>
                          {item.quantity}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Transfer Dialog */}
      <Dialog open={transferOpen} onOpenChange={setTransferOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">{t('transfer_stock')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('from_branch')}</label>
              <select
                value={transferData.from_branch_id}
                onChange={(e) => setTransferData((d) => ({ ...d, from_branch_id: e.target.value }))}
                className="w-full bg-slate-700 border border-slate-600 text-white rounded-md p-2"
              >
                <option value="">{t('select_branch')}</option>
                {branches.filter((b) => b.is_active).map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('to_branch')}</label>
              <select
                value={transferData.to_branch_id}
                onChange={(e) => setTransferData((d) => ({ ...d, to_branch_id: e.target.value }))}
                className="w-full bg-slate-700 border border-slate-600 text-white rounded-md p-2"
              >
                <option value="">{t('select_branch')}</option>
                {branches.filter((b) => b.is_active && b.id !== transferData.from_branch_id).map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('product')}</label>
              <select
                value={transferData.product_id}
                onChange={(e) => setTransferData((d) => ({ ...d, product_id: e.target.value }))}
                className="w-full bg-slate-700 border border-slate-600 text-white rounded-md p-2"
              >
                <option value="">{t('select_product')}</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('quantity')}</label>
              <Input type="number" value={transferData.quantity} onChange={(e) => setTransferData((d) => ({ ...d, quantity: parseInt(e.target.value) || 0 }))} className="bg-slate-700 border-slate-600 text-white" />
            </div>
            {transferError && (
              <p role="alert" className="text-sm text-red-400">{transferError}</p>
            )}
            <Button
              onClick={handleTransferStock}
              disabled={submitting || !transferData.from_branch_id || !transferData.to_branch_id || !transferData.product_id || transferData.quantity <= 0}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white"
            >
              {submitting ? t('loading') : t('transfer_stock')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}