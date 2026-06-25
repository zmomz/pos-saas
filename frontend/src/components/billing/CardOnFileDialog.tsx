import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useLanguage } from '@/lib/i18n';
import { tokenizeCard, moyasarConfigured } from '@/lib/moyasar';
import { ShieldCheck } from 'lucide-react';

export interface CardOnFileToken {
  token: string;
  last4: string;
  brand: string;
}

interface CardOnFileDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  publishableKey?: string | null;
  onSave: (token: CardOnFileToken) => Promise<void>;
  titleKey?: string;
  saving?: boolean;
}

// Reusable card-on-file form (Moyasar tokenization, PAY-09). The PAN is tokenized
// client-side and never reaches our server; when no publishable key is configured
// a clearly-marked sandbox token is produced so the flow stays demonstrable.
export default function CardOnFileDialog({
  open,
  onOpenChange,
  publishableKey,
  onSave,
  titleKey,
  saving,
}: CardOnFileDialogProps) {
  const { t } = useLanguage();
  const [name, setName] = useState('');
  const [number, setNumber] = useState('');
  const [month, setMonth] = useState('');
  const [year, setYear] = useState('');
  const [cvc, setCvc] = useState('');
  const [busy, setBusy] = useState(false);

  const configured = moyasarConfigured(publishableKey);
  const working = busy || !!saving;

  function reset() {
    setName('');
    setNumber('');
    setMonth('');
    setYear('');
    setCvc('');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (working) return;
    setBusy(true);
    try {
      const token = await tokenizeCard({ number, name, month, year, cvc }, publishableKey);
      await onSave({ token: token.token, last4: token.last4 || '', brand: token.brand || '' });
      toast.success(t('card_saved') || 'Card saved');
      reset();
      onOpenChange(false);
    } catch (err) {
      console.error('Save card failed:', err);
      toast.error(err instanceof Error ? err.message : (t('card_save_failed') || 'Could not save card'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!working) onOpenChange(o); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(titleKey || 'add_card') || 'Add card'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="cof-name">{t('cardholder_name') || 'Cardholder name'}</Label>
            <Input id="cof-name" autoComplete="cc-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cof-number">{t('card_number') || 'Card number'}</Label>
            <Input id="cof-number" inputMode="numeric" autoComplete="cc-number" placeholder="4111 1111 1111 1111" value={number} onChange={(e) => setNumber(e.target.value)} required />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="cof-month">{t('card_month') || 'MM'}</Label>
              <Input id="cof-month" inputMode="numeric" autoComplete="cc-exp-month" placeholder="MM" maxLength={2} value={month} onChange={(e) => setMonth(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cof-year">{t('card_year') || 'YY'}</Label>
              <Input id="cof-year" inputMode="numeric" autoComplete="cc-exp-year" placeholder="YY" maxLength={4} value={year} onChange={(e) => setYear(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cof-cvc">{t('card_cvc') || 'CVC'}</Label>
              <Input id="cof-cvc" inputMode="numeric" autoComplete="cc-csc" placeholder="123" maxLength={4} value={cvc} onChange={(e) => setCvc(e.target.value)} required />
            </div>
          </div>
          <div className="flex items-start gap-2 rounded-xl bg-muted/60 px-3 py-2 text-[12px] text-muted-foreground">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            <span>
              {t('card_tokenized_note') || 'Your card is tokenized by Moyasar — the card number never reaches our servers.'}
              {!configured && (
                <span className="mt-0.5 block font-semibold text-warning">{t('sandbox_mode') || 'Sandbox mode — no live charge.'}</span>
              )}
            </span>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" disabled={working} onClick={() => onOpenChange(false)}>{t('cancel') || 'Cancel'}</Button>
            <Button type="submit" disabled={working} className="shadow-brand">{working ? (t('loading') || 'Saving…') : (t('save_card') || 'Save card')}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
