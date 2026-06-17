import { useState, useEffect } from 'react';
import { Plus, Edit2, Trash2, Package } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { getPackagesList, createPackage, updatePackage, deletePackage } from '@/lib/api';

const FEATURE_KEYS = [
  'email_receipts', 'sms_receipts', 'loyalty', 'restaurant', 'inventory', 'discounts', 'zatca', 'omnichannel',
] as const;

interface PackageItem {
  id: number;
  name: string;
  client_slots: number;
  wholesale_price: number;
  suggested_retail_price: number;
  is_active: boolean;
  features?: string[] | null;
}

interface PackageFormData {
  name: string;
  client_slots: number;
  wholesale_price: number;
  suggested_retail_price: number;
  features: string[];
}

const emptyForm: PackageFormData = {
  name: '', client_slots: 0, wholesale_price: 0, suggested_retail_price: 0, features: [],
};

export default function PackageManagement() {
  const { language, t, isRTL } = useLanguage();
  const [packages, setPackages] = useState<PackageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingPackage, setEditingPackage] = useState<PackageItem | null>(null);
  const [form, setForm] = useState<PackageFormData>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  useEffect(() => {
    fetchPackages();
  }, []);

  async function fetchPackages() {
    try {
      setLoading(true);
      setLoadError(false);
      setDenied(false);
      const data = await getPackagesList();
      setPackages(data?.items || data?.packages || []);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setDenied(true);
      else setLoadError(true);
      setPackages([]);
    } finally {
      setLoading(false);
    }
  }

  function openAddDialog() {
    setEditingPackage(null);
    setForm(emptyForm);
    setDialogOpen(true);
  }

  function openEditDialog(pkg: PackageItem) {
    setEditingPackage(pkg);
    setForm({
      name: pkg.name,
      client_slots: pkg.client_slots,
      wholesale_price: pkg.wholesale_price,
      suggested_retail_price: pkg.suggested_retail_price,
      features: pkg.features || [],
    });
    setDialogOpen(true);
  }

  function toggleFeature(key: string) {
    setForm((prev) => ({
      ...prev,
      features: prev.features.includes(key) ? prev.features.filter((f) => f !== key) : [...prev.features, key],
    }));
  }

  async function handleSubmit() {
    if (!form.name.trim()) return;
    try {
      setSaving(true);
      const tier = form.features.length > 0 ? form.features : null;
      if (editingPackage) {
        await updatePackage(editingPackage.id, { ...form, features: tier });
      } else {
        await createPackage({ ...form, features: tier ?? undefined });
      }
      setDialogOpen(false);
      setForm(emptyForm);
      setEditingPackage(null);
      await fetchPackages();
    } catch (err) {
      console.error('Failed to save package:', err);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deletePackage(id);
      setConfirmDeleteId(null);
      await fetchPackages();
    } catch (err) {
      console.error('Failed to delete package:', err);
    }
  }

  return (
    <div className="animate-fade-up space-y-5" dir={isRTL ? 'rtl' : 'ltr'}>
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-9 w-9"><Package className="h-[18px] w-[18px]" /></span>}
        title={t('package_management')}
        subtitle={`${packages.length} ${t('packages')}`}
      >
        <Button onClick={openAddDialog} className="shadow-brand">
          <Plus className="h-4 w-4" />
          {t('add_package')}
        </Button>
      </PageHeading>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand border-t-transparent" />
          <span className="ms-3 text-muted-foreground">{t('loading')}</span>
        </div>
      )}

      {!loading && denied && <PermissionDenied />}
      {!loading && !denied && loadError && <ErrorState onRetry={fetchPackages} />}

      {!loading && !denied && !loadError && packages.length === 0 && (
        <div className="dxr-tile flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Package className="mb-4 h-16 w-16 opacity-25" />
          <p className="text-lg">{t('no_packages')}</p>
        </div>
      )}

      {!loading && !denied && packages.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {packages.map((pkg) => (
            <div key={pkg.id} className="dxr-tile dxr-hover flex flex-col">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-extrabold tracking-tight">{pkg.name}</h3>
                <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold', pkg.is_active ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground')}>
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {pkg.is_active ? t('active') : t('inactive')}
                </span>
              </div>

              <div className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">{t('client_slots')}</span><span className="font-semibold tabular-nums">{pkg.client_slots}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">{t('wholesale_price')}</span><span className="font-semibold tabular-nums">{formatMoney(pkg.wholesale_price || 0, language)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">{t('retail_price')}</span><span className="font-semibold tabular-nums">{formatMoney(pkg.suggested_retail_price || 0, language)}</span></div>
              </div>

              <div className="mt-3">
                <span className="mb-1.5 block text-xs font-semibold text-muted-foreground">{t('feature_tier')}</span>
                {pkg.features && pkg.features.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {pkg.features.map((f) => (
                      <span key={f} className="rounded-full bg-brand-500/10 px-2.5 py-0.5 text-xs font-semibold text-brand-700 dark:text-brand-300">{t(`feat_${f}`)}</span>
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground">{t('feature_tier_none')}</span>
                )}
              </div>

              <div className="mt-auto flex gap-2 pt-4">
                <Button variant="outline" size="sm" onClick={() => openEditDialog(pkg)} className="flex-1">
                  <Edit2 className="h-3.5 w-3.5" />
                  {t('edit')}
                </Button>
                {confirmDeleteId === pkg.id ? (
                  <div className="flex flex-1 gap-1">
                    <Button size="sm" variant="danger" onClick={() => handleDelete(pkg.id)} className="flex-1">{t('yes')}</Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmDeleteId(null)} className="flex-1">{t('no')}</Button>
                  </div>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => setConfirmDeleteId(pkg.id)} className="flex-1 border-danger/40 text-danger hover:bg-danger/10">
                    <Trash2 className="h-3.5 w-3.5" />
                    {t('deactivate')}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add / Edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingPackage ? t('edit_package') : t('add_package')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">{t('name')}</label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t('package_name_placeholder')} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-sm text-muted-foreground">{t('client_slots')}</label>
                <Input type="number" value={form.client_slots} onChange={(e) => setForm({ ...form, client_slots: Number(e.target.value) })} min={0} />
              </div>
              <div>
                <label className="mb-1 block text-sm text-muted-foreground">{t('wholesale_price')}</label>
                <Input type="number" value={form.wholesale_price} onChange={(e) => setForm({ ...form, wholesale_price: Number(e.target.value) })} min={0} step={0.01} />
              </div>
              <div>
                <label className="mb-1 block text-sm text-muted-foreground">{t('retail_price')}</label>
                <Input type="number" value={form.suggested_retail_price} onChange={(e) => setForm({ ...form, suggested_retail_price: Number(e.target.value) })} min={0} step={0.01} />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">{t('feature_tier')}</label>
              <p className="mb-2 text-xs text-muted-foreground">{t('feature_tier_hint')}</p>
              <div className="grid grid-cols-2 gap-2">
                {FEATURE_KEYS.map((key) => (
                  <label key={key} className="flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-muted/40 px-2.5 py-2 text-sm">
                    <Checkbox checked={form.features.includes(key)} onCheckedChange={() => toggleFeature(key)} />
                    <span>{t(`feat_${key}`)}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setDialogOpen(false)}>{t('cancel')}</Button>
              <Button onClick={handleSubmit} disabled={saving || !form.name.trim()}>{saving ? t('loading') : t('save')}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
