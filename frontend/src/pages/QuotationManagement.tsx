import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
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
  quotationDocumentPath,
} from '@/lib/api';
import { getAPIBaseURL } from '@/lib/config';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { FileText, Plus, Trash2, Eye } from 'lucide-react';

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
  const navigate = useNavigate();
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [customerName, setCustomerName] = useState('');
  const [validUntil, setValidUntil] = useState('');
  const [notes, setNotes] = useState('');
  const [items, setItems] = useState<LineItem[]>([{ name: '', quantity: 1, price: 0 }]);

  async function load() {
    setLoading(true);
    try {
      const data = await getQuotations();
      setQuotations((data?.items as Quotation[]) || []);
    } catch (err) {
      console.error('Failed to load quotations:', err);
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
    <div className="min-h-screen bg-slate-900 p-4">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <FileText className="w-6 h-6 text-brand-400" />
            <h1 className="text-2xl font-bold text-white">{t('quotations')}</h1>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => navigate(-1)}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              {t('back')}
            </Button>
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button className="bg-brand-600 hover:bg-brand-700 text-white">
                  <Plus className="w-4 h-4 me-2" />
                  {t('new_quotation')}
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-slate-800 border-slate-700 text-white max-w-lg">
                <DialogHeader>
                  <DialogTitle>{t('new_quotation')}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                  <Input
                    placeholder={t('customer_name')}
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    className="bg-slate-900 border-slate-600 text-white"
                  />
                  {items.map((it, idx) => (
                    <div key={idx} className="flex gap-2">
                      <Input
                        placeholder={t('item_name')}
                        value={it.name}
                        onChange={(e) => setItem(idx, { name: e.target.value })}
                        className="bg-slate-900 border-slate-600 text-white flex-1"
                      />
                      <Input
                        type="number"
                        min={1}
                        value={it.quantity}
                        onChange={(e) => setItem(idx, { quantity: Number(e.target.value) })}
                        className="bg-slate-900 border-slate-600 text-white w-20"
                      />
                      <Input
                        type="number"
                        min={0}
                        step="0.01"
                        value={it.price}
                        onChange={(e) => setItem(idx, { price: Number(e.target.value) })}
                        className="bg-slate-900 border-slate-600 text-white w-28"
                      />
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    onClick={() => setItems((p) => [...p, { name: '', quantity: 1, price: 0 }])}
                    className="border-slate-600 text-slate-300 hover:bg-slate-700 w-full"
                  >
                    <Plus className="w-4 h-4 me-2" />
                    {t('add_item')}
                  </Button>
                  <Input
                    type="date"
                    value={validUntil}
                    onChange={(e) => setValidUntil(e.target.value)}
                    className="bg-slate-900 border-slate-600 text-white"
                  />
                  <Input
                    placeholder={t('notes')}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="bg-slate-900 border-slate-600 text-white"
                  />
                  <div className="text-slate-300 text-sm space-y-1 border-t border-slate-700 pt-2">
                    <div className="flex justify-between"><span>{t('subtotal')}</span><span>{formatMoney(subtotal, language)}</span></div>
                    <div className="flex justify-between"><span>{t('vat')}</span><span>{formatMoney(vatAmount, language)}</span></div>
                    <div className="flex justify-between font-bold text-white"><span>{t('total')}</span><span>{formatMoney(total, language)}</span></div>
                  </div>
                  <Button
                    onClick={handleSave}
                    disabled={saving}
                    className="bg-green-600 hover:bg-green-700 text-white w-full"
                  >
                    {t('save')}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {loading ? (
          <p className="text-slate-400">{t('loading')}</p>
        ) : quotations.length === 0 ? (
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-8 text-center text-slate-400">
              {t('no_quotations')}
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {quotations.map((q) => (
              <Card key={q.id} className="bg-slate-800 border-slate-700">
                <CardContent className="p-4 flex items-center justify-between">
                  <div>
                    <p className="text-white font-semibold">{q.quote_number}</p>
                    <p className="text-slate-400 text-sm">{q.customer_name || '—'}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge className="bg-slate-600 text-white">{q.status || 'draft'}</Badge>
                    <span className="text-brand-400 font-bold">{formatMoney(q.total_amount || 0, language)}</span>
                    <Button size="sm" variant="outline" onClick={() => openDocument(q.id)}
                      className="border-slate-600 text-slate-300 hover:bg-slate-700">
                      <Eye className="w-4 h-4" />
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => handleDelete(q.id)}
                      className="border-red-700 text-red-400 hover:bg-red-900/40">
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
