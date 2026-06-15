import { useEffect, useState } from 'react';
import { ShoppingCart, CheckCircle } from 'lucide-react';
import { CUSTOMER_DISPLAY_KEY, type CustomerDisplayPayload } from '@/lib/customerDisplay';
import { useLanguage } from '@/lib/i18n';

// The display always renders with a resolved business name; the writer omits it
// when unknown (HW-05), so the reader keeps this platform fallback.
type DisplayState = CustomerDisplayPayload & { businessName: string };

export default function CustomerDisplay() {
  const { t, isRTL } = useLanguage();
  const [display, setDisplay] = useState<DisplayState>({
    items: [],
    subtotal: 0,
    vat: 0,
    total: 0,
    businessName: 'POS System',
    status: 'idle',
  });

  useEffect(() => {
    // Listen for POS updates via localStorage events
    function handleStorageChange(e: StorageEvent) {
      if (e.key === CUSTOMER_DISPLAY_KEY) {
        try {
          const data = JSON.parse(e.newValue || '{}');
          setDisplay((prev) => ({ ...prev, ...data }));
        } catch {
          // ignore parse errors
        }
      }
    }

    // Also poll localStorage for initial state and same-tab updates
    function pollDisplay() {
      try {
        const raw = localStorage.getItem(CUSTOMER_DISPLAY_KEY);
        if (raw) {
          const data = JSON.parse(raw);
          setDisplay((prev) => ({ ...prev, ...data }));
        }
      } catch {
        // ignore
      }
    }

    window.addEventListener('storage', handleStorageChange);
    const interval = setInterval(pollDisplay, 1000);
    pollDisplay();

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      clearInterval(interval);
    };
  }, []);

  if (display.status === 'paid') {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'} className="min-h-screen bg-gradient-to-b from-green-900 to-green-950 flex items-center justify-center p-8">
        <div className="text-center">
          <CheckCircle className="h-24 w-24 text-green-400 mx-auto mb-6 animate-pulse" />
          <h1 className="text-5xl font-bold text-white mb-4">{t('cd_thank_you')}</h1>
          <p className="text-2xl text-green-300 mt-6">{t('cd_thank_you_sub')}</p>
        </div>
      </div>
    );
  }

  return (
    <div dir={isRTL ? 'rtl' : 'ltr'} className="min-h-screen bg-gradient-to-b from-slate-900 to-slate-950 flex flex-col">
      {/* Header */}
      <div className="bg-slate-800/80 border-b border-slate-700 p-6 text-center">
        <h1 className="text-3xl font-bold text-white">{display.businessName}</h1>
        <p className="text-slate-400 text-lg mt-1">{t('cd_welcome')}</p>
      </div>

      {/* Cart Items */}
      <div className="flex-1 p-6 overflow-y-auto">
        {display.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <ShoppingCart className="h-20 w-20 text-slate-700 mb-4" />
            <p className="text-2xl text-slate-500">{t('cd_waiting')}</p>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto space-y-3">
            {display.items.map((item, idx) => (
              <div key={idx} className="flex items-center justify-between bg-slate-800/60 rounded-xl p-4 border border-slate-700/50">
                <div className="flex items-center gap-4">
                  <span className="text-2xl font-bold text-brand-400 w-10 text-center">{item.quantity}×</span>
                  <div>
                    {/* HW-05 data contract: bilingual product line (Arabic primary, English secondary). */}
                    <p className="text-xl text-white font-medium">{item.name_ar || item.name}</p>
                    {item.name_ar && <p className="text-sm text-slate-400">{item.name}</p>}
                  </div>
                </div>
                <p className="text-xl text-white font-bold" dir="ltr">
                  {(item.price * item.quantity).toFixed(2)} <span className="text-sm text-slate-400">{t('cd_currency')}</span>
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Totals Footer */}
      {display.items.length > 0 && (
        <div className="bg-slate-800 border-t border-slate-700 p-6">
          <div className="max-w-2xl mx-auto space-y-3">
            <div className="flex justify-between text-lg text-slate-300">
              <span>{t('subtotal')}</span>
              <span dir="ltr">{display.subtotal.toFixed(2)} {t('cd_currency')}</span>
            </div>
            <div className="flex justify-between text-lg text-slate-300">
              <span>{t('vat')}</span>
              <span dir="ltr">{display.vat.toFixed(2)} {t('cd_currency')}</span>
            </div>
            <div className="border-t border-slate-600 pt-3 flex justify-between">
              <span className="text-3xl font-bold text-white">{t('total')}</span>
              <span className="text-4xl font-bold text-green-400" dir="ltr">{display.total.toFixed(2)} <span className="text-xl">{t('cd_currency')}</span></span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}