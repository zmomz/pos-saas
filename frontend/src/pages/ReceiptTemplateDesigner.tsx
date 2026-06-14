import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  listReceiptTemplates,
  createReceiptTemplate,
  updateReceiptTemplate,
  type ReceiptTemplate,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Receipt as ReceiptIcon, QrCode } from 'lucide-react';

interface TemplateForm {
  name: string;
  header_text: string;
  footer_text: string;
  show_logo: boolean;
  show_vat_details: boolean;
  show_qr_code: boolean;
  paper_size: string;
  font_size: string;
}

const emptyForm: TemplateForm = {
  name: 'Default',
  header_text: '',
  footer_text: '',
  show_logo: true,
  show_vat_details: true,
  show_qr_code: true,
  paper_size: '80mm',
  font_size: 'medium',
};

// Mirror of escpos.py `_FONT_SCALE` so the preview scales like the real print.
const FONT_SCALE: Record<string, number> = { small: 0.85, medium: 1.0, large: 1.2 };
// Approximate on-screen widths (px) for each thermal paper size.
const PAPER_WIDTH_PX: Record<string, number> = { '80mm': 288, '58mm': 200 };

// Always-Arabic receipt labels (the fiscal invariant: every printable renders
// in Arabic regardless of UI language — mirrors escpos.py `_L`). The preview
// shows the same Arabic the printer would emit.
const AR = {
  store: 'المتجر',
  vat_no: 'الرقم الضريبي',
  tax_invoice: 'فاتورة ضريبية',
  sample_item: 'منتج',
  subtotal: 'المجموع الفرعي',
  vat: 'ضريبة القيمة المضافة',
  grand_total: 'الإجمالي شامل الضريبة',
  thanks: 'شكراً لزيارتكم',
};

function toForm(t: ReceiptTemplate): TemplateForm {
  return {
    name: t.name || 'Default',
    header_text: t.header_text ?? '',
    footer_text: t.footer_text ?? '',
    show_logo: t.show_logo ?? true,
    show_vat_details: t.show_vat_details ?? true,
    show_qr_code: t.show_qr_code ?? true,
    paper_size: t.paper_size || '80mm',
    font_size: t.font_size || 'medium',
  };
}

export default function ReceiptTemplateDesigner() {
  const { t } = useLanguage();
  const [form, setForm] = useState<TemplateForm>(emptyForm);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<'saved' | 'error' | null>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const items = await listReceiptTemplates();
      // The renderer loads the `is_default` template; fall back to the first.
      const chosen = items.find((it) => it.is_default) ?? items[0];
      if (chosen) {
        setTemplateId(chosen.id);
        setForm(toForm(chosen));
      }
    } catch (err) {
      console.error('Failed to load receipt template:', err);
    } finally {
      setLoading(false);
    }
  }

  function change<K extends keyof TemplateForm>(field: K, value: TemplateForm[K]) {
    setForm((prev) => ({ ...prev, [field]: value }));
    setStatus(null);
  }

  async function handleSave() {
    setSaving(true);
    setStatus(null);
    const payload = {
      name: form.name?.trim() || 'Default',
      header_text: form.header_text,
      footer_text: form.footer_text,
      show_logo: form.show_logo,
      show_vat_details: form.show_vat_details,
      show_qr_code: form.show_qr_code,
      paper_size: form.paper_size,
      font_size: form.font_size,
      // Persist as the merchant's default so the ESC/POS renderer loads it (#45).
      is_default: true,
    };
    try {
      if (templateId != null) {
        await updateReceiptTemplate(templateId, payload);
      } else {
        const created = await createReceiptTemplate(payload);
        setTemplateId(created.id);
      }
      setStatus('saved');
    } catch (err) {
      console.error('Failed to save receipt template:', err);
      setStatus('error');
    } finally {
      setSaving(false);
    }
  }

  const scale = FONT_SCALE[form.font_size] ?? 1.0;
  const widthPx = PAPER_WIDTH_PX[form.paper_size] ?? PAPER_WIDTH_PX['80mm'];
  const base = useMemo(() => 11 * scale, [scale]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 flex items-center gap-3">
          <ReceiptIcon className="h-8 w-8 text-brand-400" />
          <div>
            <h2 className="text-lg font-bold text-white">{t('receipt_template')}</h2>
            <p className="text-slate-400 text-sm">{t('receipt_template_intro')}</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ---- Editor ---- */}
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 space-y-4">
            <div>
              <label htmlFor="tpl-name" className="text-sm text-slate-400 mb-1 block">
                {t('template_name')}
              </label>
              <Input
                id="tpl-name"
                value={form.name}
                onChange={(e) => change('name', e.target.value)}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>

            <div>
              <label htmlFor="tpl-header" className="text-sm text-slate-400 mb-1 block">
                {t('header_text')}
              </label>
              <Input
                id="tpl-header"
                value={form.header_text}
                onChange={(e) => change('header_text', e.target.value)}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>

            <div>
              <label htmlFor="tpl-footer" className="text-sm text-slate-400 mb-1 block">
                {t('footer_text')}
              </label>
              <Input
                id="tpl-footer"
                value={form.footer_text}
                onChange={(e) => change('footer_text', e.target.value)}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>

            <div>
              <label htmlFor="tpl-font" className="text-sm text-slate-400 mb-1 block">
                {t('font_size')}
              </label>
              <select
                id="tpl-font"
                aria-label={t('font_size')}
                value={form.font_size}
                onChange={(e) => change('font_size', e.target.value)}
                className="w-full rounded-md bg-slate-700 border border-slate-600 text-white p-2 text-sm"
              >
                <option value="small">{t('font_small')}</option>
                <option value="medium">{t('font_medium')}</option>
                <option value="large">{t('font_large')}</option>
              </select>
            </div>

            <div>
              <label htmlFor="tpl-paper" className="text-sm text-slate-400 mb-1 block">
                {t('paper_size')}
              </label>
              <select
                id="tpl-paper"
                aria-label={t('paper_size')}
                value={form.paper_size}
                onChange={(e) => change('paper_size', e.target.value)}
                className="w-full rounded-md bg-slate-700 border border-slate-600 text-white p-2 text-sm"
              >
                <option value="80mm">80mm</option>
                <option value="58mm">58mm</option>
              </select>
            </div>

            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={form.show_logo}
                onChange={(e) => change('show_logo', e.target.checked)}
              />
              {t('show_logo')}
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={form.show_vat_details}
                onChange={(e) => change('show_vat_details', e.target.checked)}
              />
              {t('show_vat_details')}
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={form.show_qr_code}
                onChange={(e) => change('show_qr_code', e.target.checked)}
              />
              {t('show_qr_code')}
            </label>

            <div className="flex items-center gap-3 pt-2">
              <Button
                onClick={handleSave}
                disabled={saving}
                className="bg-brand-600 hover:bg-brand-700 text-white"
              >
                {saving ? t('loading') : t('save')}
              </Button>
              {status === 'saved' && (
                <span className="text-sm text-emerald-400">{t('template_saved')}</span>
              )}
              {status === 'error' && (
                <span className="text-sm text-red-400">{t('template_save_failed')}</span>
              )}
            </div>
          </CardContent>
        </Card>

        {/* ---- Live preview ---- */}
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">{t('preview')}</h3>
            <div className="flex justify-center">
              <div
                data-testid="receipt-preview"
                dir="rtl"
                lang="ar"
                style={{ width: widthPx, fontSize: base }}
                className="bg-white text-black rounded-md shadow-lg p-3 font-mono leading-relaxed"
              >
                <div
                  className="text-center font-bold"
                  style={{ fontSize: form.show_logo ? base * 1.5 : base }}
                >
                  {AR.store}
                </div>
                {form.header_text && (
                  <div className="text-center">{form.header_text}</div>
                )}
                {form.show_vat_details && (
                  <div className="flex justify-between">
                    <span>300000000000003</span>
                    <span>{AR.vat_no}</span>
                  </div>
                )}
                <div className="text-center font-semibold my-1">{AR.tax_invoice}</div>
                <hr className="border-dashed border-black/40 my-1" />
                <div className="flex justify-between">
                  <span>٢ × ١٠٫٠٠ = ٢٠٫٠٠</span>
                  <span>{AR.sample_item}</span>
                </div>
                <hr className="border-dashed border-black/40 my-1" />
                <div className="flex justify-between">
                  <span>٢٠٫٠٠</span>
                  <span>{AR.subtotal}</span>
                </div>
                <div className="flex justify-between">
                  <span>٣٫٠٠</span>
                  <span>{AR.vat}</span>
                </div>
                <div className="flex justify-between font-bold">
                  <span>٢٣٫٠٠</span>
                  <span>{AR.grand_total}</span>
                </div>
                {form.show_qr_code && (
                  <div className="flex justify-center my-2" data-testid="preview-qr">
                    <QrCode className="h-16 w-16 text-black" aria-label="QR" />
                  </div>
                )}
                <div className="text-center mt-1">
                  {form.footer_text || AR.thanks}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
