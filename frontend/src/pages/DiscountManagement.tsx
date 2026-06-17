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
import { getDiscounts, createDiscount, updateDiscount, deleteDiscount } from '@/lib/api';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile from '@/components/dashboard/StatTile';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { Tag, Percent, DollarSign, Plus } from 'lucide-react';

interface Discount {
  id: string;
  code: string;
  type: string;
  value: number;
  min_purchase?: number;
  max_uses?: number;
  usage_count?: number;
  is_active?: boolean;
  starts_at?: string | null;
  ends_at?: string | null;
  created_at?: string;
}

interface DiscountFormData {
  code: string;
  type: string;
  value: string;
  min_purchase: string;
  max_uses: string;
  starts_at: string;
  ends_at: string;
}

const emptyForm: DiscountFormData = {
  code: '',
  type: 'percentage',
  value: '',
  min_purchase: '',
  max_uses: '',
  starts_at: '',
  ends_at: '',
};

// A native datetime-local control emits/consumes "YYYY-MM-DDTHH:mm"; the API
// stores/returns full ISO datetimes, so trim to the minute for the input.
function toLocalInput(iso?: string | null): string {
  return iso ? iso.slice(0, 16) : '';
}

// PRC-02: where "now" sits relative to a discount's scheduled window.
type WindowState = 'scheduled' | 'expired' | 'live';

function windowState(discount: Discount, now: Date = new Date()): WindowState {
  if (discount.starts_at && now < new Date(discount.starts_at)) return 'scheduled';
  if (discount.ends_at && now > new Date(discount.ends_at)) return 'expired';
  return 'live';
}

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
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedDiscount, setSelectedDiscount] = useState<Discount | null>(null);
  const [formData, setFormData] = useState<DiscountFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const { t, isRTL, language } = useLanguage();
  const tt = (key: string, fallback: string) => { const v = t(key); return v === key ? fallback : v; };

  useEffect(() => {
    loadDiscounts();
  }, []);

  async function loadDiscounts() {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const data = await getDiscounts();
      setDiscounts(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      console.error('Failed to load discounts:', err);
      setDiscounts([]);
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 403 means the account lacks access to discount management; show the
      // in-page permission state rather than a misleading empty table (UX-02).
      if (status === 403) {
        setDenied(true);
      } else {
        // A real fetch failure must not masquerade as "no discounts" (UX-02).
        setError(true);
      }
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
        starts_at: formData.starts_at || undefined,
        ends_at: formData.ends_at || undefined,
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
      starts_at: toLocalInput(discount.starts_at),
      ends_at: toLocalInput(discount.ends_at),
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
        starts_at: formData.starts_at || null,
        ends_at: formData.ends_at || null,
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
          <Label className="mb-1 block">{t('discount_code')} *</Label>
          <div className="flex gap-2">
            <Input
              value={formData.code}
              onChange={(e) => handleFormChange('code', e.target.value.toUpperCase())}
              placeholder={t('discount_code_placeholder')}
              dir="ltr"
              className="flex-1"
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => handleFormChange('code', generateCode())}
              className="text-xs whitespace-nowrap"
            >
              {t('auto_generate')}
            </Button>
          </div>
        </div>
        <div>
          <Label className="mb-1 block">{t('discount_type')} *</Label>
          <Select value={formData.type} onValueChange={(v) => handleFormChange('type', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="percentage">
                {t('discount_percentage')} (%)
              </SelectItem>
              <SelectItem value="fixed">
                {t('discount_fixed')} (SAR)
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1 block">
            {t('discount_value')} * {formData.type === 'percentage' ? '(%)' : '(SAR)'}
          </Label>
          <Input
            type="number"
            value={formData.value}
            onChange={(e) => handleFormChange('value', e.target.value)}
            placeholder={formData.type === 'percentage' ? '10' : '50.00'}
          />
        </div>
        <div>
          <Label className="mb-1 block">{t('min_purchase')} (SAR)</Label>
          <Input
            type="number"
            value={formData.min_purchase}
            onChange={(e) => handleFormChange('min_purchase', e.target.value)}
            placeholder={t('min_purchase_placeholder')}
          />
        </div>
        <div>
          <Label className="mb-1 block">{t('max_uses')}</Label>
          <Input
            type="number"
            value={formData.max_uses}
            onChange={(e) => handleFormChange('max_uses', e.target.value)}
            placeholder={t('max_uses_placeholder')}
          />
        </div>
        {/* PRC-02 scheduled validity window — a coupon is only honoured between
            these bounds; leave either empty for an open-ended (always-on) code. */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label className="mb-1 block">{t('valid_from')}</Label>
            <Input
              type="datetime-local"
              dir="ltr"
              value={formData.starts_at}
              onChange={(e) => handleFormChange('starts_at', e.target.value)}
            />
          </div>
          <div>
            <Label className="mb-1 block">{t('valid_until')}</Label>
            <Input
              type="datetime-local"
              dir="ltr"
              value={formData.ends_at}
              onChange={(e) => handleFormChange('ends_at', e.target.value)}
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">{t('validity_window_hint')}</p>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.code || !formData.value}
            className="flex-1"
          >
            {submitting ? t('loading') : submitLabel}
          </Button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'} className="flex items-center justify-center h-64">
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  if (denied) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'}>
        <PermissionDenied />
      </div>
    );
  }

  if (error) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'}>
        <ErrorState onRetry={loadDiscounts} />
      </div>
    );
  }

  return (
    <div dir={isRTL ? 'rtl' : 'ltr'} className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Tag className="h-[18px] w-[18px]" /></span>}
        title={tt('discounts', 'Discounts')}
        subtitle={`${discounts.length} ${t('total_discounts')}`}
      >
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button
              onClick={() => setFormData(emptyForm)}
              className="h-11 rounded-[10px] shadow-brand"
            >
              <Plus className="h-4 w-4" />
              {t('create_discount')}
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('create_new_discount')}</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddDiscount, t('create_discount'))}
          </DialogContent>
        </Dialog>
      </PageHeading>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile icon={Tag} label={t('total_discounts')} value={discounts.length} tone="brand" />
        <StatTile icon={Percent} label={t('active')} value={activeCount} tone="success" />
        <StatTile
          icon={DollarSign}
          label={t('total_uses')}
          value={discounts.reduce((sum, d) => sum + (d.usage_count || 0), 0)}
          tone="violet"
        />
      </div>

      {/* Table */}
      <div className="dxr-tile overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-muted/40">
            <tr className="text-muted-foreground">
              <th className="p-3 text-start">{t('code')}</th>
              <th className="p-3 text-start">{t('discount_type')}</th>
              <th className="p-3 text-start">{t('discount_value')}</th>
              <th className="p-3 text-start">{t('min_purchase')}</th>
              <th className="p-3 text-start">{t('usage')}</th>
              <th className="p-3 text-start">{t('validity_window')}</th>
              <th className="p-3 text-start">{t('status')}</th>
              <th className="p-3 text-start">{t('actions')}</th>
            </tr>
          </thead>
          <tbody>
            {discounts.length === 0 ? (
              <tr>
                <td colSpan={8} className="p-6 text-center text-muted-foreground">
                  {t('no_discounts')}
                </td>
              </tr>
            ) : (
              discounts.map((discount) => (
                <tr key={discount.id} className="border-t border-border text-foreground/90">
                  <td className="p-3">
                    <code className="bg-muted px-2 py-0.5 rounded text-brand-700 font-mono text-xs" dir="ltr">
                      {discount.code}
                    </code>
                  </td>
                  <td className="p-3">
                    {discount.type === 'percentage' ? t('discount_percentage') : t('discount_fixed')}
                  </td>
                  <td className="p-3 font-medium text-foreground tabular-nums">
                    {discount.type === 'percentage'
                      ? `${discount.value}%`
                      : formatMoney(discount.value, language)}
                  </td>
                  <td className="p-3 tabular-nums">
                    {discount.min_purchase ? formatMoney(discount.min_purchase, language) : '—'}
                  </td>
                  <td className="p-3 tabular-nums">
                    {discount.usage_count ?? 0}
                    {discount.max_uses ? ` / ${discount.max_uses}` : ' / ∞'}
                  </td>
                  <td className="p-3">
                    {!discount.starts_at && !discount.ends_at ? (
                      <span className="text-muted-foreground">{t('validity_always')}</span>
                    ) : (
                      <div className="flex flex-col gap-1">
                        <span className="text-xs text-muted-foreground" dir="ltr">
                          {discount.starts_at ? toLocalInput(discount.starts_at) : '…'}
                          {' → '}
                          {discount.ends_at ? toLocalInput(discount.ends_at) : '…'}
                        </span>
                        {windowState(discount) === 'scheduled' && (
                          <span className="pill-warning w-fit">
                            {t('discount_scheduled')}
                          </span>
                        )}
                        {windowState(discount) === 'expired' && (
                          <span className="pill-danger w-fit">
                            {t('discount_expired')}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="p-3">
                    {discount.is_active !== false ? (
                      <span className="pill-success">
                        {t('active')}
                      </span>
                    ) : (
                      <span className="pill-muted">
                        {t('inactive')}
                      </span>
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
                            ? 'border-warning/40 text-warning hover:bg-warning/10'
                            : 'border-success/40 text-success hover:bg-success/10'
                        }`}
                      >
                        {discount.is_active !== false ? t('disable') : t('enable')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openEdit(discount)}
                        className="text-xs"
                      >
                        {t('edit')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openDelete(discount)}
                        className="border-danger/40 text-danger hover:bg-danger/10 text-xs"
                      >
                        {t('delete')}
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
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('edit_discount')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditDiscount, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('confirm_delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-foreground/90">{t('delete_discount_confirm')}</p>
          <p className="text-center font-mono text-brand-700" dir="ltr">{selectedDiscount?.code}</p>
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
              onClick={handleDeleteDiscount}
              disabled={submitting}
              className="flex-1"
            >
              {submitting ? t('loading') : t('delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}