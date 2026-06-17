import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  getQuotations,
  createQuotation,
  deleteQuotation,
  convertQuotation,
  quotationDocumentPath,
} from '@/lib/api';
import { getAPIBaseURL } from '@/lib/config';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import ErrorState from '@/components/states/ErrorState';
import EmptyState from '@/components/states/EmptyState';
import { toast } from 'sonner';
import { FileText, Plus, Trash2, Eye, ShoppingCart } from 'lucide-react';

// ISSUE-056: a converted/expired quote is terminal — it can't be converted again.
const TERMINAL_STATUSES = ['converted', 'expired'];

// Map each quote status to a distinct pill so draft/sent/converted/expired read
// differently (they were all flattened to pill-muted).
const STATUS_PILL: Record<string, string> = {
  draft: 'pill-muted',
  sent: 'pill-sky',
  accepted: 'pill-success',
  converted: 'pill-success',
  rejected: 'pill-danger',
  expired: 'pill-danger',
};

interface LineItem {
  name: string;
  quantity: number;
  price: number;
}

interface Quotation {
  id: number;
  quote_number?: string;
  customer_name?: string;
  total_amount?: number;
  status?: string;
  valid_until?: string;
  created_at?: string;
}

const VAT_RATE = 0.15;

export default function QuotationManagement() {
  const { t, language } = useLanguage();
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [customerName, setCustomerName] = useState('');
  const [validUntil, setValidUntil] = useState('');
  const [notes, setNotes] = useState('');
  const [items, setItems] = useState<LineItem[]>([{ name: '', quantity: 1, price: 0 }]);

  async function load() {
    setLoading(true);
    setError(false);
    try {
      const data = await getQuotations();
      setQuotations((data?.items as Quotation[]) || []);
    } catch (err) {
      console.error('Failed to load quotations:', err);
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const subtotal = items.reduce((sum, it) => sum + it.quantity * it.price, 0);
  const vatAmount = subtotal * VAT_RATE;
  const total = subtotal + vatAmount;

  function setItem(idx: number, patch: Partial<LineItem>) {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  async function handleSave() {
    const validItems = items.filter((it) => it.name.trim() && it.quantity > 0);
    if (validItems.length === 0) return;
    setSaving(true);
    try {
      await createQuotation({
        customer_name: customerName || undefined,
        items_json: JSON.stringify(validItems),
        subtotal,
        vat_amount: vatAmount,
        total_amount: total,
        valid_until: validUntil || undefined,
        notes: notes || undefined,
        status: 'draft',
      });
      setOpen(false);
      setCustomerName('');
      setValidUntil('');
      setNotes('');
      setItems([{ name: '', quantity: 1, price: 0 }]);
      await load();
    } catch (err) {
      console.error('Failed to create quotation:', err);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteQuotation(String(id));
      await load();
    } catch (err) {
      console.error('Failed to delete quotation:', err);
    }
  }

  // ISSUE-056: turn the quote into a real ZATCA sale via the canonical path.
  async function handleConvert(id: number) {
    try {
      const result = await convertQuotation(id, { payment_method: 'cash' });
      toast.success(`${t('converted_to_sale')}: ${result.invoice_number}`);
      await load();
    } catch (err) {
      console.error('Failed to convert quotation:', err);
      toast.error(t('convert_failed'));
    }
  }

  // The quotation document is always-Arabic and requires auth, so fetch it with
  // the bearer token and open the HTML in a new tab (rather than a bare link).
  async function openDocument(id: number) {
    try {
      const token = localStorage.getItem('pos_auth_token');
      const resp = await fetch(`${getAPIBaseURL()}${quotationDocumentPath(id)}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const html = await resp.text();
      const win = window.open('', '_blank');
      if (win) {
        win.document.open();
        win.document.write(html);
        win.document.close();
      }
    } catch (err) {
      console.error('Failed to open quotation document:', err);
    }
  }

  return (
    <div className="animate-fade-up space-y-6">
      <Dialog open={open} onOpenChange={setOpen}>
        <PageHeading
          icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><FileText className="h-[18px] w-[18px]" /></span>}
          title={t('quotations')}
          subtitle={`${quotations.length} ${t('quotations')}`}
        >
          <DialogTrigger asChild>
            <Button className="h-11 rounded-[10px] shadow-brand">
              <Plus className="h-4 w-4" />
              {t('new_quotation')}
            </Button>
          </DialogTrigger>
        </PageHeading>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('new_quotation')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder={t('customer_name')}
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
            />
            {items.map((it, idx) => (
              <div key={idx} className="flex gap-2">
                <Input
                  placeholder={t('item_name')}
                  value={it.name}
                  onChange={(e) => setItem(idx, { name: e.target.value })}
                  className="flex-1"
                />
                <Input
                  type="number"
                  min={1}
                  value={it.quantity}
                  onChange={(e) => setItem(idx, { quantity: Number(e.target.value) })}
                  className="w-20"
                />
                <Input
                  type="number"
                  min={0}
                  step="0.01"
                  value={it.price}
                  onChange={(e) => setItem(idx, { price: Number(e.target.value) })}
                  className="w-28"
                />
              </div>
            ))}
            <Button
              variant="outline"
              onClick={() => setItems((p) => [...p, { name: '', quantity: 1, price: 0 }])}
              className="w-full"
            >
              <Plus className="h-4 w-4 me-2" />
              {t('add_item')}
            </Button>
            <Input
              type="date"
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
            />
            <Input
              placeholder={t('notes')}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
            <div className="text-foreground/90 text-sm space-y-1 border-t border-border pt-2">
              <div className="flex justify-between"><span>{t('subtotal')}</span><span className="tabular-nums">{formatMoney(subtotal, language)}</span></div>
              <div className="flex justify-between"><span>{t('vat')}</span><span className="tabular-nums">{formatMoney(vatAmount, language)}</span></div>
              <div className="flex justify-between font-bold text-foreground"><span>{t('total')}</span><span className="tabular-nums">{formatMoney(total, language)}</span></div>
            </div>
            <Button
              onClick={handleSave}
              disabled={saving}
              className="w-full"
            >
              {t('save')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {loading ? (
        <p className="text-muted-foreground">{t('loading')}</p>
      ) : error ? (
        <ErrorState onRetry={load} />
      ) : quotations.length === 0 ? (
        <EmptyState icon={FileText} message={t('no_quotations')} />
      ) : (
        <div className="space-y-3">
          {quotations.map((q) => (
            <Card key={q.id} className="bg-card border-border">
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-foreground font-semibold">{q.quote_number}</p>
                  <p className="text-muted-foreground text-sm">{q.customer_name || '—'}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`${STATUS_PILL[q.status || 'draft'] || 'pill-muted'} capitalize`}>{q.status || 'draft'}</span>
                  <span className="text-brand font-bold tabular-nums">{formatMoney(q.total_amount || 0, language)}</span>
                  {!TERMINAL_STATUSES.includes(q.status || 'draft') && (
                    <Button size="sm" variant="outline" onClick={() => handleConvert(q.id)}>
                      <ShoppingCart className="w-4 h-4 me-1" />
                      {t('convert_to_sale')}
                    </Button>
                  )}
                  <Button size="sm" variant="outline" onClick={() => openDocument(q.id)}>
                    <Eye className="w-4 h-4" />
                  </Button>
                  <Button size="sm" variant="destructive" onClick={() => handleDelete(q.id)}>
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
