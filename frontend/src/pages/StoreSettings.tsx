import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { useLanguage } from '@/lib/i18n';
import { useBusinessProfile } from '@/contexts/BusinessProfileContext';
import { notifyError } from '@/lib/notify';
import { Store, FileText, MapPin, Clock, Layers } from 'lucide-react';
import { toast } from 'sonner';
import {
  getStoreSettings,
  saveStoreSettings,
  setBusinessType,
  type BusinessHours,
  type BusinessType,
} from '@/lib/api';

// ISSUE-079 — one screen for the store-level identity and operating defaults that
// feed every receipt/invoice: VAT/CR numbers, the receipt footer, the branch
// profile and the business hours. Persisted server-side (seller name + VAT are
// written through to the authoritative client row).

const DAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const;

function defaultHours(): BusinessHours[] {
  return DAYS.map((day) => ({ day, open: '09:00', close: '23:00', closed: false }));
}

export default function StoreSettings() {
  const { t, isRTL } = useLanguage();
  const [storeName, setStoreName] = useState('');
  const [vatNumber, setVatNumber] = useState('');
  const [crNumber, setCrNumber] = useState('');
  const [receiptFooter, setReceiptFooter] = useState('');
  const [address, setAddress] = useState('');
  const [city, setCity] = useState('');
  const [phone, setPhone] = useState('');
  const [hours, setHours] = useState<BusinessHours[]>(defaultHours());
  const [saving, setSaving] = useState(false);

  // Change-business-type flow (issue #201). Switching the type recomputes the
  // navigation, dashboard, onboarding and restaurant permissions — no data is
  // deleted, so switching back restores everything.
  const { businessType, refresh } = useBusinessProfile();
  const currentType: BusinessType = businessType ?? 'retail';
  const [pendingType, setPendingType] = useState<BusinessType | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [changingType, setChangingType] = useState(false);

  function requestTypeChange(next: BusinessType) {
    if (next === currentType) return;
    setPendingType(next);
    setConfirmOpen(true);
  }

  async function confirmTypeChange() {
    if (!pendingType) return;
    setChangingType(true);
    try {
      await setBusinessType(pendingType);
      await refresh();
      toast.success(t('bt_changed'));
      setConfirmOpen(false);
      setPendingType(null);
    } catch (err) {
      notifyError(err, t('bt_change_failed') || 'Could not update business type. Please try again.');
    } finally {
      setChangingType(false);
    }
  }

  const typeLabel = (bt: BusinessType) =>
    bt === 'restaurant' ? t('business_type_restaurant') : bt === 'both' ? t('business_type_both') : t('business_type_retail');

  useEffect(() => {
    let cancelled = false;
    getStoreSettings()
      .then((s) => {
        if (cancelled) return;
        setStoreName(s.store_name || '');
        setVatNumber(s.vat_number || '');
        setCrNumber(s.cr_number || '');
        setReceiptFooter(s.receipt_footer || '');
        setAddress(s.address || '');
        setCity(s.city || '');
        setPhone(s.phone || '');
        if (s.business_hours && s.business_hours.length) setHours(s.business_hours);
      })
      .catch(() => {
        // First-time merchant with nothing saved — keep the empty/default form.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSave() {
    setSaving(true);
    try {
      await saveStoreSettings({
        store_name: storeName,
        vat_number: vatNumber,
        cr_number: crNumber,
        receipt_footer: receiptFooter,
        address,
        city,
        phone,
        business_hours: hours,
      });
      toast.success(t('settings_saved'));
    } catch (err) {
      console.error('Failed to save store settings:', err);
      toast.error(err instanceof Error ? err.message : t('settings_save_failed'));
    } finally {
      setSaving(false);
    }
  }

  function updateDay(index: number, patch: Partial<BusinessHours>) {
    setHours((prev) => prev.map((h, i) => (i === index ? { ...h, ...patch } : h)));
  }

  const labelCls = 'mb-1 block text-muted-foreground';

  return (
    <div className="animate-fade-up space-y-6 max-w-3xl" dir={isRTL ? 'rtl' : 'ltr'}>
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Store className="h-[18px] w-[18px]" /></span>}
        title={t('store_settings')}
        subtitle={t('store_settings_intro')}
      >
        <Button onClick={handleSave} disabled={saving} className="h-11 rounded-[10px] shadow-brand">
          {saving ? t('loading') : t('save_changes')}
        </Button>
      </PageHeading>

      {/* Identity: name, VAT, CR */}
      <div className="dxr-tile">
        <h2 className="mb-4 flex items-center gap-2 text-[16px] font-extrabold tracking-tight">
          <Store className="h-5 w-5 text-brand-600" />
          {t('store_settings')}
        </h2>
        <div className="space-y-4">
          <div>
            <Label htmlFor="store-name" className={labelCls}>{t('store_name')}</Label>
            <Input
              id="store-name"
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
              placeholder={t('store_name')}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="vat-number" className={labelCls}>{t('vat_number')}</Label>
              <Input
                id="vat-number"
                value={vatNumber}
                onChange={(e) => setVatNumber(e.target.value)}
                placeholder={t('vat_number')}
              />
            </div>
            <div>
              <Label htmlFor="cr-number" className={labelCls}>{t('cr_number')}</Label>
              <Input
                id="cr-number"
                value={crNumber}
                onChange={(e) => setCrNumber(e.target.value)}
                placeholder={t('cr_number')}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Business type (issue #201) — drives nav, dashboard, onboarding & POS mode */}
      <div className="dxr-tile">
        <h2 className="mb-1 flex items-center gap-2 text-[16px] font-extrabold tracking-tight">
          <Layers className="h-5 w-5 text-brand-600" />
          {t('business_type')}
        </h2>
        <p className="mb-4 text-sm text-muted-foreground">{t('bt_section_desc')}</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:items-end">
          <div>
            <Label htmlFor="business-type" className={labelCls}>{t('choose_business_type')}</Label>
            <Select value={currentType} onValueChange={(v) => requestTypeChange(v as BusinessType)}>
              <SelectTrigger id="business-type" aria-label={t('choose_business_type')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="retail">{t('business_type_retail')}</SelectItem>
                <SelectItem value="restaurant">{t('business_type_restaurant')}</SelectItem>
                <SelectItem value="both">{t('business_type_both')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs text-muted-foreground">{t('business_type_hint')}</p>
        </div>
      </div>

      {/* Receipt footer */}
      <div className="dxr-tile">
        <h2 className="mb-4 flex items-center gap-2 text-[16px] font-extrabold tracking-tight">
          <FileText className="h-5 w-5 text-success" />
          {t('receipt_footer')}
        </h2>
        <Input
          aria-label={t('receipt_footer')}
          value={receiptFooter}
          onChange={(e) => setReceiptFooter(e.target.value)}
          placeholder={t('receipt_footer')}
        />
      </div>

      {/* Branch profile */}
      <div className="dxr-tile">
        <h2 className="mb-4 flex items-center gap-2 text-[16px] font-extrabold tracking-tight">
          <MapPin className="h-5 w-5 text-violet" />
          {t('branch_profile')}
        </h2>
        <div className="space-y-4">
          <div>
            <Label htmlFor="branch-address" className={labelCls}>{t('address')}</Label>
            <Input
              id="branch-address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder={t('address')}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="branch-city" className={labelCls}>{t('city')}</Label>
              <Input
                id="branch-city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder={t('city')}
              />
            </div>
            <div>
              <Label htmlFor="branch-phone" className={labelCls}>{t('phone')}</Label>
              <Input
                id="branch-phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder={t('phone')}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Business hours */}
      <div className="dxr-tile">
        <h2 className="mb-4 flex items-center gap-2 text-[16px] font-extrabold tracking-tight">
          <Clock className="h-5 w-5 text-warning" />
          {t('business_hours')}
        </h2>
        <div className="space-y-2">
          {hours.map((h, i) => (
            <div key={h.day} className="flex items-center gap-3 py-1">
              <span className="w-12 text-sm text-muted-foreground uppercase">{h.day}</span>
              <Input
                type="time"
                aria-label={`${h.day}-${t('day_open')}`}
                value={h.open}
                disabled={h.closed}
                onChange={(e) => updateDay(i, { open: e.target.value })}
                className="w-32"
              />
              <Input
                type="time"
                aria-label={`${h.day}-${t('day_close')}`}
                value={h.close}
                disabled={h.closed}
                onChange={(e) => updateDay(i, { close: e.target.value })}
                className="w-32"
              />
              <Button
                size="sm"
                variant={h.closed ? 'destructive' : 'outline'}
                onClick={() => updateDay(i, { closed: !h.closed })}
              >
                {t('day_closed')}
              </Button>
            </div>
          ))}
        </div>
      </div>

      {/* Change-type warning — recompute, never delete */}
      <AlertDialog open={confirmOpen} onOpenChange={(open) => { if (!changingType) setConfirmOpen(open); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('bt_change_warning_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('bt_change_warning_desc')}
              {pendingType && (
                <span className="mt-2 block font-semibold text-foreground">
                  {typeLabel(currentType)}{' '}
                  <span className="inline-block rtl:-scale-x-100" aria-hidden="true">→</span>{' '}
                  {typeLabel(pendingType)}
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={changingType}>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => { e.preventDefault(); confirmTypeChange(); }}
              disabled={changingType}
            >
              {changingType ? t('loading') : t('bt_confirm_change')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
