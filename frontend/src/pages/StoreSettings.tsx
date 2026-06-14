import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useLanguage } from '@/lib/i18n';
import { Store, FileText, MapPin, Clock } from 'lucide-react';
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
  const [saved, setSaved] = useState(false);

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
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  }

  function updateDay(index: number, patch: Partial<BusinessHours>) {
    setHours((prev) => prev.map((h, i) => (i === index ? { ...h, ...patch } : h)));
  }

  return (
    <div className="space-y-6 max-w-3xl" dir={isRTL ? 'rtl' : 'ltr'}>
      <div>
        <h1 className="text-2xl font-bold text-white">{t('store_settings')}</h1>
        <p className="text-slate-400 text-sm mt-1">{t('store_settings_intro')}</p>
      </div>

      {/* Identity: name, VAT, CR */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Store className="h-5 w-5 text-brand-400" />
            {t('store_settings')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm text-slate-400 mb-1 block">{t('store_name')}</label>
            <Input
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
              placeholder={t('store_name')}
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('vat_number')}</label>
              <Input
                value={vatNumber}
                onChange={(e) => setVatNumber(e.target.value)}
                placeholder={t('vat_number')}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('cr_number')}</label>
              <Input
                value={crNumber}
                onChange={(e) => setCrNumber(e.target.value)}
                placeholder={t('cr_number')}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Receipt footer */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <FileText className="h-5 w-5 text-green-400" />
            {t('receipt_footer')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Input
            value={receiptFooter}
            onChange={(e) => setReceiptFooter(e.target.value)}
            placeholder={t('receipt_footer')}
            className="bg-slate-700 border-slate-600 text-white"
          />
        </CardContent>
      </Card>

      {/* Branch profile */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <MapPin className="h-5 w-5 text-purple-400" />
            {t('branch_profile')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm text-slate-400 mb-1 block">{t('address')}</label>
            <Input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder={t('address')}
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('city')}</label>
              <Input
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder={t('city')}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('phone')}</label>
              <Input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder={t('phone')}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Business hours */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Clock className="h-5 w-5 text-yellow-400" />
            {t('business_hours')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {hours.map((h, i) => (
            <div key={h.day} className="flex items-center gap-3 py-1">
              <span className="w-12 text-sm text-slate-300 uppercase">{h.day}</span>
              <Input
                type="time"
                aria-label={`${h.day}-${t('day_open')}`}
                value={h.open}
                disabled={h.closed}
                onChange={(e) => updateDay(i, { open: e.target.value })}
                className="bg-slate-700 border-slate-600 text-white w-32"
              />
              <Input
                type="time"
                aria-label={`${h.day}-${t('day_close')}`}
                value={h.close}
                disabled={h.closed}
                onChange={(e) => updateDay(i, { close: e.target.value })}
                className="bg-slate-700 border-slate-600 text-white w-32"
              />
              <Button
                size="sm"
                variant="outline"
                onClick={() => updateDay(i, { closed: !h.closed })}
                className={h.closed
                  ? 'bg-red-600/30 text-red-300 border-red-700'
                  : 'bg-slate-700 text-slate-300 border-slate-600'
                }
              >
                {t('day_closed')}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex gap-3">
        <Button onClick={handleSave} disabled={saving} className="bg-brand-600 hover:bg-brand-700 text-white">
          {saving ? t('loading') : saved ? '✓ ' + t('save_changes') : t('save_changes')}
        </Button>
      </div>
    </div>
  );
}
