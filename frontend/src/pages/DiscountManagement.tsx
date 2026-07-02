import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
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
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
import StatTile from '@/components/dashboard/StatTile';
import { useLanguage } from '@/lib/i18n';
import { undoableAction } from '@/lib/undo';
import { useBulkSelection } from '@/hooks/useBulkSelection';
import { SearchField } from '@/components/ui/search-field';
import SavedFilterBar from '@/components/dashboard/rx/SavedFilterBar';
import { useSavedFilters } from '@/hooks/useSavedFilters';
import LoadingState from '@/components/states/LoadingState';
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

// #273 — the status segment a Discounts saved view can capture.
type DiscountStatusFilter = 'all' | 'active' | 'inactive';

// #273 — the filter combination a saved view captures for the Discounts book.
interface DiscountFilterPreset {
  search: string;
  status: DiscountStatusFilter;
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
  // #273 (Productivity follow-up — saved filters): the search/status combination
  // a power user can pin under a name and re-apply in one click.
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<DiscountStatusFilter>('all');
  const savedFilters = useSavedFilters<DiscountFilterPreset>('dxr.savedfilters.discounts');

  const { t, tt, isRTL, language } = useLanguage();

  // #273 — narrow the book by code search + active/inactive segment before it
  // reaches the table and the selection helper, so both stay in sync with what
  // the operator sees.
  const filteredDiscounts = discounts.filter((d) => {
    const matchesSearch = !search.trim() || d.code.toLowerCase().includes(search.trim().toLowerCase());
    const active = d.is_active !== false;
    const matchesStatus =
      statusFilter === 'all' || (statusFilter === 'active' ? active : !active);
    return matchesSearch && matchesStatus;
  });

  // #231 (Productivity — bulk ops): multi-row selection for batch actions via the
  // shared useBulkSelection hook. The list is unpaginated, so the "page" is the
  // whole filtered set; the bulk bar surfaces once anything is selected.
  const {
    selectedIds,
    allPageSelected,
    isSelected,
    toggle: toggleSelect,
    toggleAllOnPage: toggleSelectAllOnPage,
    clear: clearSelection,
  } = useBulkSelection<string>(filteredDiscounts.map((d) => d.id));

  useEffect(() => {
    loadDiscounts();
  }, []);

  async function loadDiscounts() {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const data = await getDiscounts();
      const list = Array.isArray(data?.items) ? data.items : [];
      setDiscounts(list as unknown as Discount[]);
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

  // #231 (Productivity — undo): deleting a discount is deferred behind an undo
  // window. We drop the row optimistically and only hit the server once the
  // window elapses; an undo cancels the commit outright so a mis-click never
  // reaches the backend and no restore round-trip is needed.
  function handleDeleteDiscount() {
    if (!selectedDiscount) return;
    const discount = selectedDiscount;
    setDeleteOpen(false);
    setSelectedDiscount(null);
    // Optimistic removal; the server still holds the row until (and unless) the
    // deferred commit fires, so a refetch reliably restores it on undo.
    setDiscounts((prev) => prev.filter((d) => d.id !== discount.id));
    undoableAction({
      message: tt('discount_deleted', 'Discount deleted'),
      undoLabel: tt('action_undo', 'Undo'),
      onUndo: () => {
        loadDiscounts();
      },
      onCommit: async () => {
        try {
          await deleteDiscount(discount.id);
          await loadDiscounts();
        } catch (err) {
          console.error('Failed to delete discount:', err);
          // Commit failed — restore the row so the operator isn't misled.
          loadDiscounts();
        }
      },
    });
  }

  // #231 (Productivity — bulk ops + undo): delete every selected discount in one
  // action. Mirrors the single-row delete: rows drop optimistically and the
  // deletes are deferred behind the undo window, so an undo cancels the whole
  // batch before it reaches the server and no restore round-trip is needed.
  function handleBulkDelete() {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    clearSelection();
    setDiscounts((prev) => prev.filter((d) => !ids.includes(d.id)));
    undoableAction({
      message: `${ids.length} ${tt('discounts_deleted', 'discounts deleted')}`,
      undoLabel: tt('action_undo', 'Undo'),
      onUndo: () => {
        loadDiscounts();
      },
      onCommit: async () => {
        try {
          await Promise.all(ids.map((id) => deleteDiscount(id)));
          await loadDiscounts();
        } catch (err) {
          console.error('Failed to bulk-delete discounts:', err);
          // Commit failed — restore the rows so the operator isn't misled.
          loadDiscounts();
        }
      },
    });
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
                {t('discount_fixed')} (⃁)
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1 block">
            {t('discount_value')} * {formData.type === 'percentage' ? '(%)' : '(⃁)'}
          </Label>
          <Input
            type="number"
            value={formData.value}
            onChange={(e) => handleFormChange('value', e.target.value)}
            placeholder={formData.type === 'percentage' ? '10' : '50.00'}
          />
        </div>
        <div>
          <Label className="mb-1 block">{t('min_purchase')} (⃁)</Label>
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

  if (loading) return <LoadingState message={t('loading')} />;

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

  const discountColumns: DataTableColumn<Discount>[] = [
    {
      key: 'select',
      className: 'w-0',
      header: (
        <Checkbox
          checked={allPageSelected}
          onCheckedChange={toggleSelectAllOnPage}
          aria-label={tt('select_all', 'Select all')}
        />
      ),
      cell: (discount) => (
        <Checkbox
          checked={isSelected(discount.id)}
          onCheckedChange={() => toggleSelect(discount.id)}
          aria-label={`${tt('select_row', 'Select')} ${discount.code}`}
        />
      ),
    },
    {
      key: 'code',
      header: t('code'),
      cell: (discount) => (
        <code className="bg-muted px-2 py-0.5 rounded text-brand-700 font-mono text-xs" dir="ltr">
          {discount.code}
        </code>
      ),
    },
    {
      key: 'type',
      header: t('discount_type'),
      cell: (discount) =>
        discount.type === 'percentage' ? t('discount_percentage') : t('discount_fixed'),
    },
    {
      key: 'value',
      header: t('discount_value'),
      className: 'font-medium text-foreground tabular-nums',
      cell: (discount) =>
        discount.type === 'percentage'
          ? `${discount.value}%`
          : formatMoney(discount.value, language),
    },
    {
      key: 'min_purchase',
      header: t('min_purchase'),
      className: 'tabular-nums',
      cell: (discount) =>
        discount.min_purchase ? formatMoney(discount.min_purchase, language) : '—',
    },
    {
      key: 'usage',
      header: t('usage'),
      className: 'tabular-nums',
      cell: (discount) =>
        `${discount.usage_count ?? 0}${discount.max_uses ? ` / ${discount.max_uses}` : ' / ∞'}`,
    },
    {
      key: 'validity',
      header: t('validity_window'),
      cell: (discount) =>
        !discount.starts_at && !discount.ends_at ? (
          <span className="text-muted-foreground">{t('validity_always')}</span>
        ) : (
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground" dir="ltr">
              {discount.starts_at ? toLocalInput(discount.starts_at) : '…'}
              {' → '}
              {discount.ends_at ? toLocalInput(discount.ends_at) : '…'}
            </span>
            {windowState(discount) === 'scheduled' && (
              <span className="pill-warning w-fit">{t('discount_scheduled')}</span>
            )}
            {windowState(discount) === 'expired' && (
              <span className="pill-danger w-fit">{t('discount_expired')}</span>
            )}
          </div>
        ),
    },
    {
      key: 'status',
      header: t('status'),
      cell: (discount) =>
        discount.is_active !== false ? (
          <span className="pill-success">{t('active')}</span>
        ) : (
          <span className="pill-muted">{t('inactive')}</span>
        ),
    },
    {
      key: 'actions',
      header: t('actions'),
      cell: (discount) => (
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
          <Button size="sm" variant="outline" onClick={() => openEdit(discount)} className="text-xs">
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
      ),
    },
  ];

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

      {/* #273 (Productivity — saved filters): search by code, segment by status,
          and pin the combination under a name to re-apply it in one click. */}
      <SearchField
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={t('search_discounts')}
      />

      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1 text-sm text-muted-foreground">
          {t('filter_by_status')}:
        </span>
        {(['all', 'active', 'inactive'] as DiscountStatusFilter[]).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            className={`rounded-full px-3 py-1 text-xs ${
              statusFilter === s ? 'bg-brand text-white' : 'bg-muted text-foreground/90'
            }`}
          >
            {t(s)}
          </button>
        ))}
      </div>

      <SavedFilterBar<DiscountFilterPreset>
        saved={savedFilters.saved}
        onApply={(v) => {
          setSearch(v.search);
          setStatusFilter(v.status);
        }}
        onSave={(name) => savedFilters.save(name, { search, status: statusFilter })}
        onRemove={savedFilters.remove}
        saveLabel={t('saved_views_save')}
        namePlaceholder={t('saved_views_name_placeholder')}
        applyTitle={(name) => t('saved_views_apply').replace('{name}', name)}
        removeLabel={(name) => t('saved_views_remove').replace('{name}', name)}
      />

      {/* #231 bulk-action bar: surfaces once any row is selected. */}
      {selectedIds.size > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-2.5">
          <span className="text-sm font-medium text-brand-800" role="status" aria-live="polite">
            {selectedIds.size} {tt('selected', 'selected')}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={handleBulkDelete}
            className="border-danger/40 text-danger hover:bg-danger/10"
          >
            {tt('delete_selected', 'Delete selected')}
          </Button>
        </div>
      )}

      {/* Table */}
      <DataTable
        className="dxr-tile p-0"
        columns={discountColumns}
        rows={filteredDiscounts}
        rowKey={(discount) => discount.id}
        empty={t('no_discounts')}
      />

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