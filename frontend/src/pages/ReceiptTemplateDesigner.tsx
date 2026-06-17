import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import ErrorState from '@/components/states/ErrorState';
import LoadingState from '@/components/states/LoadingState';
import {
  listReceiptTemplates,
  createReceiptTemplate,
  updateReceiptTemplate,
  type ReceiptTemplate,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Receipt as ReceiptIcon, QrCode } from 'lucide-react';
import { toast } from 'sonner';

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
  const [error, setError] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    setError(false);
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
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  function change<K extends keyof TemplateForm>(field: K, value: TemplateForm[K]) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSave() {
    setSaving(true);
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
      toast.success(t('template_saved'));
    } catch (err) {
      console.error('Failed to save receipt template:', err);
      toast.error(t('template_save_failed'));
    } finally {
      setSaving(false);
    }
  }

  const scale = FONT_SCALE[form.font_size] ?? 1.0;
  const widthPx = PAPER_WIDTH_PX[form.paper_size] ?? PAPER_WIDTH_PX['80mm'];
  const base = useMemo(() => 11 * scale, [scale]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState onRetry={load} />;

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><ReceiptIcon className="h-[18px] w-[18px]" /></span>}
        title={t('receipt_template')}
        subtitle={t('receipt_template_intro')}
      >
        <Button onClick={handleSave} disabled={saving} className="h-11 rounded-[10px] shadow-brand">
          {saving ? t('loading') : t('save')}
        </Button>
      </PageHeading>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ---- Editor ---- */}
        <div className="dxr-tile">
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="tpl-name" className="text-muted-foreground">
                {t('template_name')}
              </Label>
              <Input
                id="tpl-name"
                value={form.name}
                onChange={(e) => change('name', e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tpl-header" className="text-muted-foreground">
                {t('header_text')}
              </Label>
              <Input
                id="tpl-header"
                value={form.header_text}
                onChange={(e) => change('header_text', e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tpl-footer" className="text-muted-foreground">
                {t('footer_text')}
              </Label>
              <Input
                id="tpl-footer"
                value={form.footer_text}
                onChange={(e) => change('footer_text', e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-muted-foreground">{t('font_size')}</Label>
              <Select value={form.font_size} onValueChange={(v) => change('font_size', v)}>
                <SelectTrigger aria-label={t('font_size')}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="small">{t('font_small')}</SelectItem>
                  <SelectItem value="medium">{t('font_medium')}</SelectItem>
                  <SelectItem value="large">{t('font_large')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-muted-foreground">{t('paper_size')}</Label>
              <Select value={form.paper_size} onValueChange={(v) => change('paper_size', v)}>
                <SelectTrigger aria-label={t('paper_size')}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="80mm">80mm</SelectItem>
                  <SelectItem value="58mm">58mm</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Label htmlFor="tpl-show-logo" className="flex items-center gap-2 text-sm">
              <Checkbox
                id="tpl-show-logo"
                checked={form.show_logo}
                onCheckedChange={(c) => change('show_logo', c === true)}
              />
              {t('show_logo')}
            </Label>
            <Label htmlFor="tpl-show-vat" className="flex items-center gap-2 text-sm">
              <Checkbox
                id="tpl-show-vat"
                checked={form.show_vat_details}
                onCheckedChange={(c) => change('show_vat_details', c === true)}
              />
              {t('show_vat_details')}
            </Label>
            <Label htmlFor="tpl-show-qr" className="flex items-center gap-2 text-sm">
              <Checkbox
                id="tpl-show-qr"
                checked={form.show_qr_code}
                onCheckedChange={(c) => change('show_qr_code', c === true)}
              />
              {t('show_qr_code')}
            </Label>
          </div>
        </div>

        {/* ---- Live preview ---- */}
        <div className="dxr-tile">
          <div>
            <h3 className="mb-3 text-[16px] font-extrabold tracking-tight">{t('preview')}</h3>
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
          </div>
        </div>
      </div>
    </div>
  );
}
