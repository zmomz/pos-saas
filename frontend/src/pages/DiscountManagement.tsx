import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
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
import { getDiscounts, createDiscount, updateDiscount, deleteDiscount } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Tag, Percent, DollarSign } from 'lucide-react';

interface Discount {
  id: string;
  code: string;
  type: string;
  value: number;
  min_purchase?: number;
  max_uses?: number;
  used_count?: number;
  is_active?: boolean;
  created_at?: string;
}

interface DiscountFormData {
  code: string;
  type: string;
  value: string;
  min_purchase: string;
  max_uses: string;
}

const emptyForm: DiscountFormData = {
  code: '',
  type: 'percentage',
  value: '',
  min_purchase: '',
  max_uses: '',
};

function generateCode(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let code = '';
  for (let i = 0; i < 8; i++) {
    code += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return code;
}

export default function DiscountManagement() {
  const [discounts, setDiscounts] = useState<Discount[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedDiscount, setSelectedDiscount] = useState<Discount | null>(null);
  const [formData, setFormData] = useState<DiscountFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const { t } = useLanguage();

  useEffect(() => {
    loadDiscounts();
  }, []);

  async function loadDiscounts() {
    setLoading(true);
    try {
      const data = await getDiscounts();
      setDiscounts(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load discounts:', err);
      setDiscounts([]);
    } finally {
      setLoading(false);
    }
  }

  const activeCount = discounts.filter((d) => d.is_active !== false).length;

  function handleFormChange(field: keyof DiscountFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddDiscount() {
    setSubmitting(true);
    try {
      await createDiscount({
        code: formData.code,
        type: formData.type,
        value: parseFloat(formData.value),
        min_purchase: formData.min_purchase ? parseFloat(formData.min_purchase) : undefined,
        max_uses: formData.max_uses ? parseInt(formData.max_uses, 10) : undefined,
        is_active: true,
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadDiscounts();
    } catch (err) {
      console.error('Failed to create discount:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openEdit(discount: Discount) {
    setSelectedDiscount(discount);
    setFormData({
      code: discount.code,
      type: discount.type || 'percentage',
      value: String(discount.value),
      min_purchase: discount.min_purchase ? String(discount.min_purchase) : '',
      max_uses: discount.max_uses ? String(discount.max_uses) : '',
    });
    setEditOpen(true);
  }

  async function handleEditDiscount() {
    if (!selectedDiscount) return;
    setSubmitting(true);
    try {
      await updateDiscount(selectedDiscount.id, {
        code: formData.code,
        type: formData.type,
        value: parseFloat(formData.value),
        min_purchase: formData.min_purchase ? parseFloat(formData.min_purchase) : null,
        max_uses: formData.max_uses ? parseInt(formData.max_uses, 10) : null,
      });
      setEditOpen(false);
      setSelectedDiscount(null);
      setFormData(emptyForm);
      await loadDiscounts();
    } catch (err) {
      console.error('Failed to update discount:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleStatus(discount: Discount) {
    try {
      await updateDiscount(discount.id, { is_active: discount.is_active === false });
      await loadDiscounts();
    } catch (err) {
      console.error('Failed to toggle discount status:', err);
    }
  }

  function openDelete(discount: Discount) {
    setSelectedDiscount(discount);
    setDeleteOpen(true);
  }

  async function handleDeleteDiscount() {
    if (!selectedDiscount) return;
    setSubmitting(true);
    try {
      await deleteDiscount(selectedDiscount.id);
      setDeleteOpen(false);
      setSelectedDiscount(null);
      await loadDiscounts();
    } catch (err) {
      console.error('Failed to delete discount:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Discount Code *</label>
          <div className="flex gap-2">
            <Input
              value={formData.code}
              onChange={(e) => handleFormChange('code', e.target.value.toUpperCase())}
              placeholder="e.g. SAVE20"
              className="bg-slate-700 border-slate-600 text-white flex-1"
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => handleFormChange('code', generateCode())}
              className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs whitespace-nowrap"
            >
              Auto Generate
            </Button>
          </div>
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Type *</label>
          <Select value={formData.type} onValueChange={(v) => handleFormChange('type', v)}>
            <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-600">
              <SelectItem value="percentage" className="text-white hover:bg-slate-700">
                Percentage (%)
              </SelectItem>
              <SelectItem value="fixed" className="text-white hover:bg-slate-700">
                Fixed Amount (SAR)
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">
            Value * {formData.type === 'percentage' ? '(%)' : '(SAR)'}
          </label>
          <Input
            type="number"
            value={formData.value}
            onChange={(e) => handleFormChange('value', e.target.value)}
            placeholder={formData.type === 'percentage' ? '10' : '50.00'}
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Min Purchase (SAR)</label>
          <Input
            type="number"
            value={formData.min_purchase}
            onChange={(e) => handleFormChange('min_purchase', e.target.value)}
            placeholder="0.00 (no minimum)"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Max Uses</label>
          <Input
            type="number"
            value={formData.max_uses}
            onChange={(e) => handleFormChange('max_uses', e.target.value)}
            placeholder="Unlimited"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.code || !formData.value}
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
          >
            {submitting ? t('loading') : submitLabel}
          </Button>
        </div>
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
      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <Tag className="h-8 w-8 text-blue-400" />
            <div>
              <p className="text-slate-400 text-sm">Total Discounts</p>
              <p className="text-2xl font-bold text-white">{discounts.length}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <Percent className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-slate-400 text-sm">{t('active')}</p>
              <p className="text-2xl font-bold text-green-400">{activeCount}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <DollarSign className="h-8 w-8 text-purple-400" />
            <div>
              <p className="text-slate-400 text-sm">Total Uses</p>
              <p className="text-2xl font-bold text-purple-400">
                {discounts.reduce((sum, d) => sum + (d.used_count || 0), 0)}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Add Button */}
      <div className="flex justify-end">
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button
              onClick={() => setFormData(emptyForm)}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              + Create Discount
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-white">Create New Discount</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddDiscount, 'Create Discount')}
          </DialogContent>
        </Dialog>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-800">
            <tr className="text-slate-400">
              <th className="p-3 text-start">Code</th>
              <th className="p-3 text-start">Type</th>
              <th className="p-3 text-start">Value</th>
              <th className="p-3 text-start">Min Purchase</th>
              <th className="p-3 text-start">Usage</th>
              <th className="p-3 text-start">{t('status')}</th>
              <th className="p-3 text-start">Actions</th>
            </tr>
          </thead>
          <tbody>
            {discounts.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-6 text-center text-slate-500">
                  No discounts created yet
                </td>
              </tr>
            ) : (
              discounts.map((discount) => (
                <tr key={discount.id} className="border-t border-slate-700 text-slate-300">
                  <td className="p-3">
                    <code className="bg-slate-700 px-2 py-0.5 rounded text-blue-300 font-mono text-xs">
                      {discount.code}
                    </code>
                  </td>
                  <td className="p-3 capitalize">{discount.type}</td>
                  <td className="p-3 font-medium text-white">
                    {discount.type === 'percentage'
                      ? `${discount.value}%`
                      : `SAR ${discount.value}`}
                  </td>
                  <td className="p-3">
                    {discount.min_purchase ? `SAR ${discount.min_purchase}` : '—'}
                  </td>
                  <td className="p-3">
                    {discount.used_count || 0}
                    {discount.max_uses ? ` / ${discount.max_uses}` : ' / ∞'}
                  </td>
                  <td className="p-3">
                    {discount.is_active !== false ? (
                      <Badge className="bg-green-600/20 text-green-400 border border-green-600/40">
                        {t('active')}
                      </Badge>
                    ) : (
                      <Badge className="bg-slate-600/20 text-slate-400 border border-slate-600/40">
                        {t('inactive')}
                      </Badge>
                    )}
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => toggleStatus(discount)}
                        className={`text-xs ${
                          discount.is_active !== false
                            ? 'border-orange-600/50 text-orange-400 hover:bg-orange-600/20'
                            : 'border-green-600/50 text-green-400 hover:bg-green-600/20'
                        }`}
                      >
                        {discount.is_active !== false ? 'Disable' : 'Enable'}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openEdit(discount)}
                        className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openDelete(discount)}
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
            <DialogTitle className="text-white">Edit Discount</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditDiscount, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Confirm Delete</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">
            Are you sure you want to delete discount <strong>{selectedDiscount?.code}</strong>? This
            action cannot be undone.
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
              onClick={handleDeleteDiscount}
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