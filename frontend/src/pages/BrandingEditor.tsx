import { useState, useEffect } from 'react';
import { Palette } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { useLanguage, languageOptions } from '@/lib/i18n';
import { normalizeHex, readableTextColor, DARK_INK } from '@/lib/contrast';
import { getAgentBranding, updateBranding, uploadAgentLogo } from '@/lib/api';
import { config } from '@/lib/config';
import { toast } from 'sonner';

export const fontOptions = [
  { value: 'Hanken Grotesk', label: 'Hanken Grotesk' },
  { value: 'Inter', label: 'Inter' },
  { value: 'Roboto', label: 'Roboto' },
  { value: 'Poppins', label: 'Poppins' },
  { value: 'Cairo', label: 'Cairo' },
  { value: 'Noto Sans', label: 'Noto Sans' },
];

const radiusOptions = [
  { value: '0px', label: '0px (Square)' },
  { value: '4px', label: '4px (Slight)' },
  { value: '8px', label: '8px (Medium)' },
  { value: '12px', label: '12px (Rounded)' },
  { value: '20px', label: '20px (Pill)' },
];

export default function BrandingEditor() {
  const { t, isRTL } = useLanguage();

  const [logoUrl, setLogoUrl] = useState('');
  const [primaryColor, setPrimaryColor] = useState('#1488a6');
  const [secondaryColor, setSecondaryColor] = useState('#0d6079');
  const [fontFamily, setFontFamily] = useState('Hanken Grotesk');
  const [buttonRadius, setButtonRadius] = useState('8px');
  const [companyName, setCompanyName] = useState('My Company');
  const [defaultLanguage, setDefaultLanguage] = useState('en');
  const [customDomain, setCustomDomain] = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [emailBody, setEmailBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [denied, setDenied] = useState(false);

  async function handleLogoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const { logo_url } = await uploadAgentLogo(file);
      const absolute = logo_url.startsWith('http') ? logo_url : `${config.API_BASE_URL}${logo_url}`;
      setLogoUrl(absolute);
      toast.success(t('logo_uploaded'));
    } catch (err) {
      console.error('Logo upload failed:', err);
      toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('logo_upload_failed'));
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  }

  useEffect(() => {
    loadBranding();
  }, []);

  async function loadBranding() {
    try {
      setLoading(true);
      setLoadError(false);
      setDenied(false);
      const data = await getAgentBranding();
      if (data) {
        setLogoUrl(data.logo_url || '');
        setPrimaryColor(data.primary_color || '#1488a6');
        setSecondaryColor(data.secondary_color || '#0d6079');
        setFontFamily(data.font_family || 'Hanken Grotesk');
        setButtonRadius(data.button_radius || '8px');
        setCompanyName(data.company_name || 'My Company');
        setDefaultLanguage(data.default_language || 'en');
        setCustomDomain(data.custom_domain || '');
        setEmailSubject(data.email_template_subject || '');
        setEmailBody(data.email_template_body || '');
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setDenied(true);
      else if (status !== 404) setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    // Reject (don't silently store) an invalid colour — the preview and runtime
    // both consume these hex values, so a malformed colour would ship a broken
    // theme. normalizeHex repairs a missing # / 3-digit shorthand and lowercases.
    const primary = normalizeHex(primaryColor);
    const secondary = normalizeHex(secondaryColor);
    if (!primary || !secondary) {
      toast.error(t('invalid_hex_color'));
      return;
    }
    setPrimaryColor(primary);
    setSecondaryColor(secondary);

    setSaving(true);
    try {
      await updateBranding({
        logo_url: logoUrl,
        primary_color: primary,
        secondary_color: secondary,
        font_family: fontFamily,
        button_radius: buttonRadius,
        default_language: defaultLanguage,
        custom_domain: customDomain,
        email_template_subject: emailSubject,
        email_template_body: emailBody,
      });
      toast.success(t('branding_saved'));
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      toast.error(status === 409 ? t('domain_in_use') : t('branding_save_failed'));
    } finally {
      setSaving(false);
    }
  }

  const labelCls = 'text-muted-foreground';

  // Mirror the runtime contrast guard (BrandingContext.readableForeground) so the
  // preview shows the exact text colour the live theme will paint on each solid
  // brand surface — and warn when a pale brand forces the flip to dark ink.
  const primaryInk = readableTextColor(primaryColor);
  const secondaryInk = readableTextColor(secondaryColor);
  const primaryPale = primaryInk === DARK_INK;
  const secondaryPale = secondaryInk === DARK_INK;

  return (
    <div className="animate-fade-up space-y-5" dir={isRTL ? 'rtl' : 'ltr'}>
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-9 w-9"><Palette className="h-[18px] w-[18px]" /></span>}
        title={t('brand_editor')}
        subtitle={t('white_label_subtitle') || 'Customize your white-label look'}
      />

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand border-t-transparent" />
          <span className="ms-3 text-muted-foreground">{t('loading')}</span>
        </div>
      )}

      {!loading && denied && <PermissionDenied />}
      {!loading && !denied && loadError && <ErrorState onRetry={loadBranding} />}

      {!loading && !denied && !loadError && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* Form panel */}
          <div className="dxr-tile">
            <h2 className="mb-4 text-[16px] font-extrabold tracking-tight">{t('branding_settings')}</h2>
            <div className="space-y-5">
              {/* Logo */}
              <div className="space-y-2">
                <Label className={labelCls}>{t('logo')}</Label>
                <div className="flex items-center gap-3">
                  {logoUrl && <img src={logoUrl} alt="logo" className="h-12 w-12 rounded-lg bg-white object-contain p-1 ring-1 ring-border" />}
                  <label className="cursor-pointer">
                    <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={handleLogoUpload} className="hidden" />
                    <span className="inline-block rounded-lg bg-gradient-to-b from-brand to-brand-600 px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition hover:-translate-y-px">
                      {uploading ? t('loading') : t('upload_logo')}
                    </span>
                  </label>
                </div>
                <Input value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)} placeholder="https://example.com/logo.png" dir="ltr" />
              </div>

              {/* Primary color */}
              <div className="space-y-2">
                <Label className={labelCls}>{t('primary_color')}</Label>
                <div className="flex items-center gap-3">
                  <input type="color" aria-label={t('primary_color_picker')} value={primaryColor} onChange={(e) => setPrimaryColor(e.target.value)} className="h-10 w-12 cursor-pointer rounded-lg border border-input bg-transparent" />
                  <Input aria-label={t('primary_color')} value={primaryColor} onChange={(e) => setPrimaryColor(e.target.value)} className="flex-1 font-mono" dir="ltr" />
                </div>
                {primaryPale && <p className="text-xs text-amber-600">{t('pale_color_warning')}</p>}
              </div>

              {/* Secondary color */}
              <div className="space-y-2">
                <Label className={labelCls}>{t('secondary_color')}</Label>
                <div className="flex items-center gap-3">
                  <input type="color" aria-label={t('secondary_color_picker')} value={secondaryColor} onChange={(e) => setSecondaryColor(e.target.value)} className="h-10 w-12 cursor-pointer rounded-lg border border-input bg-transparent" />
                  <Input aria-label={t('secondary_color')} value={secondaryColor} onChange={(e) => setSecondaryColor(e.target.value)} className="flex-1 font-mono" dir="ltr" />
                </div>
                {secondaryPale && <p className="text-xs text-amber-600">{t('pale_color_warning')}</p>}
              </div>

              {/* Font family */}
              <div className="space-y-2">
                <Label className={labelCls}>{t('font_family')}</Label>
                <Select value={fontFamily} onValueChange={setFontFamily}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{fontOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>

              {/* Button radius */}
              <div className="space-y-2">
                <Label className={labelCls}>{t('button_radius')}</Label>
                <Select value={buttonRadius} onValueChange={setButtonRadius}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{radiusOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>

              {/* Default language */}
              <div className="space-y-2">
                <Label className={labelCls}>{t('default_language')}</Label>
                <Select value={defaultLanguage} onValueChange={setDefaultLanguage}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{languageOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>

              {/* Custom domain */}
              <div className="space-y-2">
                <Label className={labelCls}>{t('custom_domain')}</Label>
                <Input value={customDomain} onChange={(e) => setCustomDomain(e.target.value)} placeholder="pos.yourbrand.sa" dir="ltr" />
                <p className="text-xs text-muted-foreground">{t('custom_domain_hint')}</p>
              </div>

              {/* Branded email */}
              <div className="space-y-2">
                <Label className={labelCls}>{t('branded_email')}</Label>
                <Input value={emailSubject} onChange={(e) => setEmailSubject(e.target.value)} placeholder={t('email_subject')} />
                <Textarea value={emailBody} onChange={(e) => setEmailBody(e.target.value)} placeholder={t('email_body')} rows={5} />
                <p className="text-xs text-muted-foreground">{t('email_template_hint')}</p>
              </div>

              <Button onClick={handleSave} disabled={saving} className="mt-2 w-full shadow-brand">
                {saving ? t('loading') : t('save')}
              </Button>
            </div>
          </div>

          {/* Live preview panel */}
          <div className="dxr-tile">
            <h2 className="mb-4 text-[16px] font-extrabold tracking-tight">{t('live_preview')}</h2>
            <div className="space-y-6 rounded-2xl border border-border bg-muted/40 p-6">
              {logoUrl && (
                <div className="flex justify-center">
                  <img src={logoUrl} alt="Logo preview" className="max-h-16 object-contain" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                </div>
              )}

              <div className="text-center">
                <h3 className="text-2xl font-bold text-foreground" style={{ fontFamily }}>{companyName}</h3>
                <p className="mt-1 text-sm text-muted-foreground" style={{ fontFamily }}>{t('wl_pos_tagline')}</p>
              </div>

              <div className="flex items-center justify-center gap-4">
                <div className="text-center">
                  <div className="h-16 w-16 rounded-xl ring-1 ring-border" style={{ backgroundColor: primaryColor }} />
                  <p className="mt-1 text-xs text-muted-foreground">{t('primary_color')}</p>
                </div>
                <div className="text-center">
                  <div className="h-16 w-16 rounded-xl ring-1 ring-border" style={{ backgroundColor: secondaryColor }} />
                  <p className="mt-1 text-xs text-muted-foreground">{t('secondary_color')}</p>
                </div>
              </div>

              <div className="rounded-xl border p-4" style={{ borderColor: primaryColor, backgroundColor: `${primaryColor}14` }}>
                <h4 className="mb-2 font-semibold text-foreground" style={{ fontFamily }}>{t('sample_product_card')}</h4>
                <p className="text-sm text-muted-foreground" style={{ fontFamily }}>{t('sample_card_desc')}</p>
                <button className="mt-3 px-4 py-2 text-sm font-medium" style={{ backgroundColor: primaryColor, color: primaryInk, borderRadius: buttonRadius, fontFamily }}>{t('add_to_cart')}</button>
              </div>

              <div className="flex flex-wrap justify-center gap-3">
                <button className="px-5 py-2 text-sm font-medium" style={{ backgroundColor: primaryColor, color: primaryInk, borderRadius: buttonRadius, fontFamily }}>{t('primary_button')}</button>
                <button className="px-5 py-2 text-sm font-medium" style={{ backgroundColor: secondaryColor, color: secondaryInk, borderRadius: buttonRadius, fontFamily }}>{t('secondary_button')}</button>
              </div>

              <div className="border-t border-border pt-4">
                <p className="mb-1 text-xs text-muted-foreground">{t('font_label')}: {fontFamily}</p>
                <p className="text-foreground" style={{ fontFamily }}>The quick brown fox jumps over the lazy dog. 0123456789</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
