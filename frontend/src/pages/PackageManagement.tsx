import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus, Edit2, Trash2, Package } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import ErrorState from '@/components/states/ErrorState';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { getPackagesList, createPackage, updatePackage, deletePackage } from '@/lib/api';

// MA-07: the canonical feature keys an agent may gate per client (mirrors the
// backend FEATURE_KEYS). A package's tier is the subset it unlocks.
const FEATURE_KEYS = [
  'email_receipts',
  'sms_receipts',
  'loyalty',
  'restaurant',
  'inventory',
  'discounts',
  'zatca',
  'omnichannel',
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
  name: '',
  client_slots: 0,
  wholesale_price: 0,
  suggested_retail_price: 0,
  features: [],
};

export default function PackageManagement() {
  const navigate = useNavigate();
  const { language, setLanguage, t, isRTL } = useLanguage();
  const [packages, setPackages] = useState<PackageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
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
      const data = await getPackagesList();
      // The endpoint returns { items, total }; keep a legacy `packages` fallback.
      setPackages(data?.items || data?.packages || []);
    } catch {
      // A failed fetch is an error, not an empty catalog — surface it distinctly.
      setLoadError(true);
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
      features: prev.features.includes(key)
        ? prev.features.filter((f) => f !== key)
        : [...prev.features, key],
    }));
  }

  async function handleSubmit() {
    if (!form.name.trim()) return;
    try {
      setSaving(true);
      // Empty selection ⇒ no tier (null), not "a tier that unlocks nothing".
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
    } catch {
      // silent fail
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deletePackage(id);
      setConfirmDeleteId(null);
      await fetchPackages();
    } catch {
      // silent fail
    }
  }

  const labels = {
    title: language === 'ar' ? 'إدارة الباقات' : language === 'hi' ? 'पैकेज प्रबंधन' : language === 'ur' ? 'پیکج مینجمنٹ' : 'Package Management',
    addPackage: language === 'ar' ? 'إضافة باقة' : language === 'hi' ? 'पैकेज जोड़ें' : language === 'ur' ? 'پیکج شامل کریں' : 'Add Package',
    editPackage: language === 'ar' ? 'تعديل الباقة' : language === 'hi' ? 'पैकेज संपादित करें' : language === 'ur' ? 'پیکج ترمیم کریں' : 'Edit Package',
    name: language === 'ar' ? 'الاسم' : language === 'hi' ? 'नाम' : language === 'ur' ? 'نام' : 'Name',
    clientSlots: t('client_slots'),
    wholesalePrice: t('wholesale_price'),
    retailPrice: t('retail_price'),
    confirmDelete: language === 'ar' ? 'تأكيد الحذف؟' : language === 'hi' ? 'हटाने की पुष्टि करें?' : language === 'ur' ? 'حذف کی تصدیق؟' : 'Confirm deactivate?',
    deactivate: language === 'ar' ? 'تعطيل' : language === 'hi' ? 'निष्क्रिय करें' : language === 'ur' ? 'غیر فعال کریں' : 'Deactivate',
    noPackages: language === 'ar' ? 'لا توجد باقات' : language === 'hi' ? 'कोई पैकेज नहीं' : language === 'ur' ? 'کوئی پیکج نہیں' : 'No packages found',
  };

  return (
    <div className={`min-h-screen bg-slate-900 text-white ${isRTL ? 'rtl' : 'ltr'}`} dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Header */}
      <header className="border-b border-slate-700 bg-slate-800 px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate('/master')}
              className="text-slate-300 hover:text-white"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <h1 className="text-xl font-bold">{labels.title}</h1>
          </div>
          <div className="flex items-center gap-3">
            <Select value={language} onValueChange={(val) => setLanguage(val as Language)}>
              <SelectTrigger className="w-32 border-slate-700 bg-slate-700 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="border-slate-700 bg-slate-800 text-white">
                {languageOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button onClick={openAddDialog} className="bg-blue-600 text-white hover:bg-blue-700">
                  <Plus className="mr-2 h-4 w-4" />
                  {labels.addPackage}
                </Button>
              </DialogTrigger>
              <DialogContent className="border-slate-700 bg-slate-800 text-white">
                <DialogHeader>
                  <DialogTitle>
                    {editingPackage ? labels.editPackage : labels.addPackage}
                  </DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-4">
                  <div>
                    <label className="mb-1 block text-sm text-slate-300">{labels.name}</label>
                    <Input
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      className="border-slate-600 bg-slate-700 text-white"
                      placeholder="e.g. Business Pro"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm text-slate-300">{labels.clientSlots}</label>
                    <Input
                      type="number"
                      value={form.client_slots}
                      onChange={(e) => setForm({ ...form, client_slots: Number(e.target.value) })}
                      className="border-slate-600 bg-slate-700 text-white"
                      min={0}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm text-slate-300">{labels.wholesalePrice}</label>
                    <Input
                      type="number"
                      value={form.wholesale_price}
                      onChange={(e) => setForm({ ...form, wholesale_price: Number(e.target.value) })}
                      className="border-slate-600 bg-slate-700 text-white"
                      min={0}
                      step={0.01}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm text-slate-300">{labels.retailPrice}</label>
                    <Input
                      type="number"
                      value={form.suggested_retail_price}
                      onChange={(e) => setForm({ ...form, suggested_retail_price: Number(e.target.value) })}
                      className="border-slate-600 bg-slate-700 text-white"
                      min={0}
                      step={0.01}
                    />
                  </div>
                  {/* MA-07: feature-entitlement tier */}
                  <div>
                    <label className="mb-1 block text-sm text-slate-300">{t('feature_tier')}</label>
                    <p className="mb-2 text-xs text-slate-400">{t('feature_tier_hint')}</p>
                    <div className="grid grid-cols-2 gap-2">
                      {FEATURE_KEYS.map((key) => (
                        <label
                          key={key}
                          className="flex cursor-pointer items-center gap-2 rounded-md border border-slate-600 bg-slate-700/50 px-2 py-1.5 text-sm text-slate-200"
                        >
                          <Checkbox
                            checked={form.features.includes(key)}
                            onCheckedChange={() => toggleFeature(key)}
                          />
                          <span>{t(`feat_${key}`)}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="flex justify-end gap-3 pt-2">
                    <Button
                      variant="outline"
                      onClick={() => setDialogOpen(false)}
                      className="border-slate-600 text-slate-300 hover:bg-slate-700 hover:text-white"
                    >
                      {t('cancel')}
                    </Button>
                    <Button
                      onClick={handleSubmit}
                      disabled={saving || !form.name.trim()}
                      className="bg-blue-600 text-white hover:bg-blue-700"
                    >
                      {saving ? t('loading') : t('save')}
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-6xl p-6">
        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
            <span className="ml-3 text-slate-400">{t('loading')}</span>
          </div>
        )}

        {/* Error state — distinct from empty (UX-02) */}
        {!loading && loadError && (
          <ErrorState onRetry={fetchPackages} />
        )}

        {/* Empty state */}
        {!loading && !loadError && packages.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <Package className="mb-4 h-16 w-16 opacity-30" />
            <p className="text-lg">{labels.noPackages}</p>
          </div>
        )}

        {/* Package grid */}
        {!loading && packages.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {packages.map((pkg) => (
              <Card key={pkg.id} className="border-slate-700 bg-slate-800">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-lg text-white">{pkg.name}</CardTitle>
                  <Badge className={pkg.is_active ? 'bg-green-600 text-white' : 'bg-slate-600 text-slate-300'}>
                    {pkg.is_active ? t('active') : t('inactive')}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">{labels.clientSlots}</span>
                    <span className="font-medium text-white">{pkg.client_slots}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">{labels.wholesalePrice}</span>
                    <span className="font-medium text-white">SAR {pkg.wholesale_price}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">{labels.retailPrice}</span>
                    <span className="font-medium text-white">SAR {pkg.suggested_retail_price}</span>
                  </div>
                  {/* MA-07: the package's feature tier */}
                  <div>
                    <span className="mb-1 block text-xs text-slate-400">{t('feature_tier')}</span>
                    {pkg.features && pkg.features.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {pkg.features.map((f) => (
                          <Badge key={f} className="bg-blue-900/40 text-blue-200">
                            {t(`feat_${f}`)}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-slate-500">{t('feature_tier_none')}</span>
                    )}
                  </div>
                  <div className="flex gap-2 pt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openEditDialog(pkg)}
                      className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700 hover:text-white"
                    >
                      <Edit2 className="mr-1 h-3.5 w-3.5" />
                      {language === 'ar' ? 'تعديل' : language === 'hi' ? 'संपादित' : language === 'ur' ? 'ترمیم' : 'Edit'}
                    </Button>
                    {confirmDeleteId === pkg.id ? (
                      <div className="flex flex-1 gap-1">
                        <Button
                          size="sm"
                          onClick={() => handleDelete(pkg.id)}
                          className="flex-1 bg-red-600 text-white hover:bg-red-700"
                        >
                          {language === 'ar' ? 'نعم' : language === 'hi' ? 'हाँ' : language === 'ur' ? 'ہاں' : 'Yes'}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setConfirmDeleteId(null)}
                          className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700 hover:text-white"
                        >
                          {language === 'ar' ? 'لا' : language === 'hi' ? 'नहीं' : language === 'ur' ? 'نہیں' : 'No'}
                        </Button>
                      </div>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setConfirmDeleteId(pkg.id)}
                        className="flex-1 border-red-800 text-red-400 hover:bg-red-900/30 hover:text-red-300"
                      >
                        <Trash2 className="mr-1 h-3.5 w-3.5" />
                        {labels.deactivate}
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}