import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { useLanguage } from '@/lib/i18n';
import { Store, FileText, MapPin, Clock } from 'lucide-react';
import { toast } from 'sonner';
import {
  getStoreSettings,
  saveStoreSettings,
  type BusinessHours,
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
      toast.success(t('save_changes'));
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
      <div className="dxr-tile" style={{ padding: 22 }}>
        <h2 className="mb-4 flex items-center gap-2 text-[16px] font-extrabold tracking-tight">
          <Store className="h-5 w-5 text-brand-600" />
          {t('store_settings')}
        </h2>
        <div className="space-y-4">
          <div>
            <Label className={labelCls}>{t('store_name')}</Label>
            <Input
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
              placeholder={t('store_name')}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label className={labelCls}>{t('vat_number')}</Label>
              <Input
                value={vatNumber}
                onChange={(e) => setVatNumber(e.target.value)}
                placeholder={t('vat_number')}
              />
            </div>
            <div>
              <Label className={labelCls}>{t('cr_number')}</Label>
              <Input
                value={crNumber}
                onChange={(e) => setCrNumber(e.target.value)}
                placeholder={t('cr_number')}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Receipt footer */}
      <div className="dxr-tile" style={{ padding: 22 }}>
        <h2 className="mb-4 flex items-center gap-2 text-[16px] font-extrabold tracking-tight">
          <FileText className="h-5 w-5 text-success" />
          {t('receipt_footer')}
        </h2>
        <Input
          value={receiptFooter}
          onChange={(e) => setReceiptFooter(e.target.value)}
          placeholder={t('receipt_footer')}
        />
      </div>

      {/* Branch profile */}
      <div className="dxr-tile" style={{ padding: 22 }}>
        <h2 className="mb-4 flex items-center gap-2 text-[16px] font-extrabold tracking-tight">
          <MapPin className="h-5 w-5 text-violet" />
          {t('branch_profile')}
        </h2>
        <div className="space-y-4">
          <div>
            <Label className={labelCls}>{t('address')}</Label>
            <Input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder={t('address')}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label className={labelCls}>{t('city')}</Label>
              <Input
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder={t('city')}
              />
            </div>
            <div>
              <Label className={labelCls}>{t('phone')}</Label>
              <Input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder={t('phone')}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Business hours */}
      <div className="dxr-tile" style={{ padding: 22 }}>
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
    </div>
  );
}
