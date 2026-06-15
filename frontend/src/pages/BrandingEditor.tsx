import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { getAgentBranding, updateBranding, uploadAgentLogo } from '@/lib/api';
import { config } from '@/lib/config';
import { toast } from 'sonner';

const fontOptions = [
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
  const navigate = useNavigate();
  const { language, setLanguage, t, isRTL } = useLanguage();

  const [logoUrl, setLogoUrl] = useState('');
  const [primaryColor, setPrimaryColor] = useState('#1488a6');
  const [secondaryColor, setSecondaryColor] = useState('#0d6079');
  const [fontFamily, setFontFamily] = useState('Hanken Grotesk');
  const [buttonRadius, setButtonRadius] = useState('8px');
  const [companyName, setCompanyName] = useState('My Company');
  const [defaultLanguage, setDefaultLanguage] = useState('en');
  // AG-05 / AG-06 deep white-label.
  const [customDomain, setCustomDomain] = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [emailBody, setEmailBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  // UX-02 (F-051): distinguish a real load failure / a 403 from the normal
  // "no branding saved yet" case so the editor never masquerades a permission
  // wall or a server error as an empty, editable form.
  const [loadError, setLoadError] = useState(false);
  const [denied, setDenied] = useState(false);

  async function handleLogoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const { logo_url } = await uploadAgentLogo(file);
      // Store an absolute URL so client apps on another origin can load it.
      const absolute = logo_url.startsWith('http') ? logo_url : `${config.API_BASE_URL}${logo_url}`;
      setLogoUrl(absolute);
      toast.success(t('upload_logo') || 'Logo uploaded');
    } catch (err) {
      console.error('Logo upload failed:', err);
      toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Upload failed');
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
      // A 403 gets its own permission state; a 404 (no branding yet) is normal —
      // fall through to the defaults-filled editor. Anything else is a real error.
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setDenied(true);
      else if (status !== 404) setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      await updateBranding({
        logo_url: logoUrl,
        primary_color: primaryColor,
        secondary_color: secondaryColor,
        font_family: fontFamily,
        button_radius: buttonRadius,
        default_language: defaultLanguage,
        custom_domain: customDomain,
        email_template_subject: emailSubject,
        email_template_body: emailBody,
      });
      toast.success(t('save') + ' ✓', {
        description: 'Branding updated successfully',
      });
    } catch (err) {
      // A 409 means the custom domain is already claimed by another agent (AG-05).
      const status = (err as { response?: { status?: number } })?.response?.status;
      toast.error(status === 409 ? t('domain_in_use') : 'Failed to save branding');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`min-h-screen bg-slate-900 text-white ${isRTL ? 'rtl' : 'ltr'}`} dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Header */}
      <header className="border-b border-slate-700 bg-slate-800 px-6 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate('/agent')}
              className="text-slate-300 hover:text-white"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <h1 className="text-xl font-bold">🎨 {t('brand_editor')}</h1>
          </div>
          <Select value={language} onValueChange={(val) => setLanguage(val as Language)}>
            <SelectTrigger className="w-32 border-slate-700 bg-slate-700 text-white">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="border-slate-700 bg-slate-800 text-white">
              {languageOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl p-6">
        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-600 border-t-transparent" />
            <span className="ml-3 text-slate-400">{t('loading')}</span>
          </div>
        )}

        {/* Permission-denied state (in-page, UX-02) */}
        {!loading && denied && <PermissionDenied />}

        {/* Error state — distinct from the normal fresh editor (UX-02) */}
        {!loading && !denied && loadError && <ErrorState onRetry={loadBranding} />}

        {!loading && !denied && !loadError && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Form Panel */}
            <Card className="bg-slate-800 border-slate-700">
              <CardHeader>
                <CardTitle className="text-white">{t('branding_settings')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-5">
                {/* Logo: upload a file (AG-01) or paste a URL */}
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('logo')}</Label>
                  <div className="flex items-center gap-3">
                    {logoUrl && (
                      <img src={logoUrl} alt="logo" className="w-12 h-12 rounded object-contain bg-white p-1" />
                    )}
                    <label className="cursor-pointer">
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/svg+xml"
                        onChange={handleLogoUpload}
                        className="hidden"
                      />
                      <span className="inline-block px-3 py-2 rounded-md bg-brand-600 hover:bg-brand-700 text-white text-sm">
                        {uploading ? t('loading') : t('upload_logo')}
                      </span>
                    </label>
                  </div>
                  <Input
                    value={logoUrl}
                    onChange={(e) => setLogoUrl(e.target.value)}
                    placeholder="https://example.com/logo.png"
                    className="bg-slate-700 border-slate-600 text-white placeholder:text-slate-500"
                    dir="ltr"
                  />
                </div>

                {/* Primary Color */}
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('primary_color')}</Label>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={primaryColor}
                      onChange={(e) => setPrimaryColor(e.target.value)}
                      className="w-12 h-10 rounded border border-slate-600 cursor-pointer bg-transparent"
                    />
                    <Input
                      value={primaryColor}
                      onChange={(e) => setPrimaryColor(e.target.value)}
                      className="bg-slate-700 border-slate-600 text-white font-mono flex-1"
                      dir="ltr"
                    />
                  </div>
                </div>

                {/* Secondary Color */}
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('secondary_color')}</Label>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={secondaryColor}
                      onChange={(e) => setSecondaryColor(e.target.value)}
                      className="w-12 h-10 rounded border border-slate-600 cursor-pointer bg-transparent"
                    />
                    <Input
                      value={secondaryColor}
                      onChange={(e) => setSecondaryColor(e.target.value)}
                      className="bg-slate-700 border-slate-600 text-white font-mono flex-1"
                      dir="ltr"
                    />
                  </div>
                </div>

                {/* Font Family */}
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('font_family')}</Label>
                  <Select value={fontFamily} onValueChange={setFontFamily}>
                    <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-700 border-slate-600 text-white">
                      {fontOptions.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Button Radius */}
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('button_radius')}</Label>
                  <Select value={buttonRadius} onValueChange={setButtonRadius}>
                    <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-700 border-slate-600 text-white">
                      {radiusOptions.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Default Language (propagated to new clients — L10N-05) */}
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('default_language')}</Label>
                  <Select value={defaultLanguage} onValueChange={setDefaultLanguage}>
                    <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-700 border-slate-600 text-white">
                      {languageOptions.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Custom Domain (AG-05) — serves the merchant login/funnel branded */}
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('custom_domain')}</Label>
                  <Input
                    value={customDomain}
                    onChange={(e) => setCustomDomain(e.target.value)}
                    placeholder="pos.yourbrand.sa"
                    className="bg-slate-700 border-slate-600 text-white placeholder:text-slate-500"
                    dir="ltr"
                  />
                  <p className="text-xs text-slate-500">{t('custom_domain_hint')}</p>
                </div>

                {/* Branded provisioning email (AG-06) */}
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('branded_email')}</Label>
                  <Input
                    value={emailSubject}
                    onChange={(e) => setEmailSubject(e.target.value)}
                    placeholder={t('email_subject')}
                    className="bg-slate-700 border-slate-600 text-white placeholder:text-slate-500"
                  />
                  <Textarea
                    value={emailBody}
                    onChange={(e) => setEmailBody(e.target.value)}
                    placeholder={t('email_body')}
                    rows={5}
                    className="bg-slate-700 border-slate-600 text-white placeholder:text-slate-500"
                  />
                  <p className="text-xs text-slate-500">{t('email_template_hint')}</p>
                </div>

                {/* Save Button */}
                <Button
                  onClick={handleSave}
                  disabled={saving}
                  className="w-full bg-brand-600 hover:bg-brand-700 text-white mt-4"
                >
                  {saving ? t('loading') : t('save')}
                </Button>
              </CardContent>
            </Card>

            {/* Live Preview Panel */}
            <Card className="bg-slate-800 border-slate-700">
              <CardHeader>
                <CardTitle className="text-white">{t('live_preview')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="rounded-lg border border-slate-600 bg-slate-900 p-6 space-y-6">
                  {/* Logo Preview */}
                  {logoUrl && (
                    <div className="flex justify-center">
                      <img
                        src={logoUrl}
                        alt="Logo preview"
                        className="max-h-16 object-contain"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = 'none';
                        }}
                      />
                    </div>
                  )}

                  {/* Company Name with Font */}
                  <div className="text-center">
                    <h2
                      className="text-2xl font-bold text-white"
                      style={{ fontFamily }}
                    >
                      {companyName}
                    </h2>
                    <p className="text-slate-400 text-sm mt-1" style={{ fontFamily }}>
                      {t('wl_pos_tagline')}
                    </p>
                  </div>

                  {/* Color Swatches */}
                  <div className="flex items-center justify-center gap-4">
                    <div className="text-center">
                      <div
                        className="w-16 h-16 rounded-lg border border-slate-600"
                        style={{ backgroundColor: primaryColor }}
                      />
                      <p className="text-xs text-slate-400 mt-1">{t('primary_color')}</p>
                    </div>
                    <div className="text-center">
                      <div
                        className="w-16 h-16 rounded-lg border border-slate-600"
                        style={{ backgroundColor: secondaryColor }}
                      />
                      <p className="text-xs text-slate-400 mt-1">{t('secondary_color')}</p>
                    </div>
                  </div>

                  {/* Sample Card */}
                  <div
                    className="rounded-lg p-4 border"
                    style={{
                      borderColor: primaryColor,
                      backgroundColor: `${primaryColor}10`,
                    }}
                  >
                    <h3
                      className="font-semibold text-white mb-2"
                      style={{ fontFamily }}
                    >
                      {t('sample_product_card')}
                    </h3>
                    <p className="text-slate-400 text-sm" style={{ fontFamily }}>
                      {t('sample_card_desc')}
                    </p>
                    <button
                      className="mt-3 px-4 py-2 text-white font-medium text-sm"
                      style={{
                        backgroundColor: primaryColor,
                        borderRadius: buttonRadius,
                        fontFamily,
                      }}
                    >
                      {t('add_to_cart')}
                    </button>
                  </div>

                  {/* Sample Buttons Row */}
                  <div className="flex gap-3 justify-center flex-wrap">
                    <button
                      className="px-5 py-2 text-white font-medium text-sm"
                      style={{
                        backgroundColor: primaryColor,
                        borderRadius: buttonRadius,
                        fontFamily,
                      }}
                    >
                      {t('primary_button')}
                    </button>
                    <button
                      className="px-5 py-2 text-white font-medium text-sm"
                      style={{
                        backgroundColor: secondaryColor,
                        borderRadius: buttonRadius,
                        fontFamily,
                      }}
                    >
                      {t('secondary_button')}
                    </button>
                  </div>

                  {/* Font Preview */}
                  <div className="border-t border-slate-700 pt-4">
                    <p className="text-xs text-slate-500 mb-1">{t('font_label')}: {fontFamily}</p>
                    <p className="text-slate-300" style={{ fontFamily }}>
                      The quick brown fox jumps over the lazy dog. 0123456789
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}
