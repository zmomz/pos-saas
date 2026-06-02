import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getAgentPublicProfile } from '@/lib/api';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { Zap, FileCheck, Package, Globe, BarChart3, Cloud, ShieldCheck, Headphones, CheckCircle2, ArrowRight, Phone, Mail, Monitor, CreditCard, Receipt, Store, Users, TrendingUp } from 'lucide-react';

interface AgentProfile {
  company_name: string;
  logo_url?: string;
  primary_color?: string;
  secondary_color?: string;
  tagline?: string;
  features: string[];
  contact_email?: string;
  contact_phone?: string;
  max_clients?: number;
  active_clients?: number;
}

const content = {
  en: {
    loading: 'Loading...',
    not_found_title: 'Distributor Not Found',
    not_found_desc: "This distributor page doesn't exist or has been deactivated.",
    go_main: 'Go to Main Site',
    hero_badge: 'Authorized POS Provider',
    hero_title: 'Easy to Use POS System',
    hero_subtitle: 'A modern, ZATCA-compliant Point of Sale system designed for Saudi businesses. Fast, reliable, and available in your language.',
    hero_cta: 'Start Free Trial',
    hero_cta2: 'Contact Us',
    features_title: 'Everything Your Business Needs',
    features_subtitle: 'Powerful features designed for Saudi merchants',
    feature_1: 'Fast Checkout',
    feature_1_desc: 'Process sales in seconds with our intuitive interface. No training needed.',
    feature_2: 'ZATCA QR Invoices',
    feature_2_desc: 'Generate compliant e-invoices with QR codes automatically.',
    feature_3: 'Inventory Management',
    feature_3_desc: 'Track stock levels, get low-stock alerts, and manage products easily.',
    feature_4: 'Multi-language',
    feature_4_desc: 'Full support for Arabic, English, Hindi, and Urdu with RTL.',
    feature_5: 'Real-time Reports',
    feature_5_desc: 'Sales analytics, top products, and revenue tracking at your fingertips.',
    feature_6: 'Cloud-based',
    feature_6_desc: 'Access your data anywhere, anytime. Automatic backups and updates.',
    trust_title: 'Trusted by Saudi Businesses',
    trust_zatca: 'ZATCA Certified',
    trust_saudi: 'Saudi Made',
    trust_support: '24/7 Support',
    trust_zatca_desc: 'Fully compliant with e-invoicing regulations',
    trust_saudi_desc: 'Built for the Saudi market',
    trust_support_desc: 'Always here when you need us',
    merchant_title: 'Join Thousands of Happy Merchants',
    merchant_desc: 'Our POS system helps businesses across Saudi Arabia streamline their operations, increase efficiency, and stay compliant.',
    pricing_title: 'Simple Pricing',
    pricing_subtitle: 'Choose the plan that fits your business',
    basic: 'Basic',
    pro: 'Professional',
    premium: 'Premium',
    per_month: '/month',
    basic_features: ['1 Terminal', 'Basic Reports', 'ZATCA Compliance', 'Email Support'],
    pro_features: ['3 Terminals', 'Advanced Reports', 'ZATCA Compliance', 'Priority Support', 'Inventory Management'],
    premium_features: ['Unlimited Terminals', 'Full Analytics', 'ZATCA Compliance', 'Dedicated Support', 'Inventory + Multi-branch', 'API Access'],
    recommended: 'Recommended',
    cta_title: 'Ready to Modernize Your Business?',
    cta_desc: 'Join hundreds of Saudi merchants who trust our POS system for their daily operations.',
    cta_button: 'Start Free Trial',
    footer_powered: 'Powered by CloudPOS',
  },
  ar: {
    loading: 'جاري التحميل...',
    not_found_title: 'الموزع غير موجود',
    not_found_desc: 'هذه الصفحة غير موجودة أو تم إلغاء تفعيلها.',
    go_main: 'الذهاب للموقع الرئيسي',
    hero_badge: 'مزود نقاط بيع معتمد',
    hero_title: 'نظام نقاط بيع سهل الاستخدام',
    hero_subtitle: 'نظام نقاط بيع حديث ومتوافق مع زاتكا مصمم للأعمال السعودية. سريع وموثوق ومتوفر بلغتك.',
    hero_cta: 'ابدأ تجربة مجانية',
    hero_cta2: 'تواصل معنا',
    features_title: 'كل ما يحتاجه عملك',
    features_subtitle: 'ميزات قوية مصممة للتجار السعوديين',
    feature_1: 'دفع سريع',
    feature_1_desc: 'معالجة المبيعات في ثوانٍ مع واجهة بديهية. لا حاجة لتدريب.',
    feature_2: 'فواتير زاتكا QR',
    feature_2_desc: 'إنشاء فواتير إلكترونية متوافقة مع رموز QR تلقائياً.',
    feature_3: 'إدارة المخزون',
    feature_3_desc: 'تتبع مستويات المخزون واحصل على تنبيهات وأدر المنتجات بسهولة.',
    feature_4: 'متعدد اللغات',
    feature_4_desc: 'دعم كامل للعربية والإنجليزية والهندية والأردية مع RTL.',
    feature_5: 'تقارير فورية',
    feature_5_desc: 'تحليلات المبيعات وأفضل المنتجات وتتبع الإيرادات.',
    feature_6: 'سحابي',
    feature_6_desc: 'الوصول لبياناتك في أي مكان وزمان. نسخ احتياطي وتحديثات تلقائية.',
    trust_title: 'موثوق من الأعمال السعودية',
    trust_zatca: 'معتمد من زاتكا',
    trust_saudi: 'صنع سعودي',
    trust_support: 'دعم 24/7',
    trust_zatca_desc: 'متوافق بالكامل مع لوائح الفوترة الإلكترونية',
    trust_saudi_desc: 'مبني للسوق السعودي',
    trust_support_desc: 'دائماً هنا عندما تحتاجنا',
    merchant_title: 'انضم لآلاف التجار السعداء',
    merchant_desc: 'نظام نقاط البيع لدينا يساعد الأعمال في جميع أنحاء المملكة على تبسيط عملياتها وزيادة الكفاءة.',
    pricing_title: 'أسعار بسيطة',
    pricing_subtitle: 'اختر الخطة المناسبة لعملك',
    basic: 'أساسي',
    pro: 'احترافي',
    premium: 'مميز',
    per_month: '/شهرياً',
    basic_features: ['1 جهاز', 'تقارير أساسية', 'توافق زاتكا', 'دعم بالبريد'],
    pro_features: ['3 أجهزة', 'تقارير متقدمة', 'توافق زاتكا', 'دعم أولوية', 'إدارة المخزون'],
    premium_features: ['أجهزة غير محدودة', 'تحليلات كاملة', 'توافق زاتكا', 'دعم مخصص', 'مخزون + فروع', 'وصول API'],
    recommended: 'موصى به',
    cta_title: 'مستعد لتحديث عملك؟',
    cta_desc: 'انضم لمئات التجار السعوديين الذين يثقون بنظام نقاط البيع لدينا.',
    cta_button: 'ابدأ تجربة مجانية',
    footer_powered: 'مدعوم من كلاود بوس',
  },
  hi: {
    loading: 'लोड हो रहा है...',
    not_found_title: 'डिस्ट्रीब्यूटर नहीं मिला',
    not_found_desc: 'यह पेज मौजूद नहीं है या निष्क्रिय कर दिया गया है।',
    go_main: 'मुख्य साइट पर जाएं',
    hero_badge: 'अधिकृत POS प्रदाता',
    hero_title: 'उपयोग में आसान POS सिस्टम',
    hero_subtitle: 'सऊदी व्यवसायों के लिए डिज़ाइन किया गया आधुनिक, ZATCA-अनुपालन POS सिस्टम। तेज़, विश्वसनीय, और आपकी भाषा में उपलब्ध।',
    hero_cta: 'मुफ्त ट्रायल शुरू करें',
    hero_cta2: 'संपर्क करें',
    features_title: 'आपके व्यवसाय को जो चाहिए',
    features_subtitle: 'सऊदी व्यापारियों के लिए डिज़ाइन की गई शक्तिशाली सुविधाएं',
    feature_1: 'तेज़ चेकआउट',
    feature_1_desc: 'सहज इंटरफ़ेस के साथ सेकंडों में बिक्री प्रोसेस करें।',
    feature_2: 'ZATCA QR इनवॉइस',
    feature_2_desc: 'QR कोड के साथ अनुपालन ई-इनवॉइस स्वचालित रूप से बनाएं।',
    feature_3: 'इन्वेंटरी प्रबंधन',
    feature_3_desc: 'स्टॉक स्तर ट्रैक करें, कम-स्टॉक अलर्ट प्राप्त करें।',
    feature_4: 'बहु-भाषा',
    feature_4_desc: 'अरबी, अंग्रेजी, हिंदी और उर्दू के लिए पूर्ण समर्थन।',
    feature_5: 'रीयल-टाइम रिपोर्ट',
    feature_5_desc: 'बिक्री एनालिटिक्स और राजस्व ट्रैकिंग।',
    feature_6: 'क्लाउड-आधारित',
    feature_6_desc: 'कहीं भी, कभी भी अपना डेटा एक्सेस करें।',
    trust_title: 'सऊदी व्यवसायों द्वारा विश्वसनीय',
    trust_zatca: 'ZATCA प्रमाणित',
    trust_saudi: 'सऊदी निर्मित',
    trust_support: '24/7 सहायता',
    trust_zatca_desc: 'ई-इनवॉइसिंग नियमों के साथ पूर्ण अनुपालन',
    trust_saudi_desc: 'सऊदी बाजार के लिए बनाया गया',
    trust_support_desc: 'जब आपको जरूरत हो हमेशा यहां',
    merchant_title: 'हजारों खुश व्यापारियों से जुड़ें',
    merchant_desc: 'हमारा POS सिस्टम सऊदी अरब भर के व्यवसायों की मदद करता है।',
    pricing_title: 'सरल मूल्य निर्धारण',
    pricing_subtitle: 'अपने व्यवसाय के लिए सही योजना चुनें',
    basic: 'बेसिक',
    pro: 'प्रोफेशनल',
    premium: 'प्रीमियम',
    per_month: '/माह',
    basic_features: ['1 टर्मिनल', 'बेसिक रिपोर्ट', 'ZATCA अनुपालन', 'ईमेल सहायता'],
    pro_features: ['3 टर्मिनल', 'उन्नत रिपोर्ट', 'ZATCA अनुपालन', 'प्राथमिकता सहायता', 'इन्वेंटरी प्रबंधन'],
    premium_features: ['असीमित टर्मिनल', 'पूर्ण एनालिटिक्स', 'ZATCA अनुपालन', 'समर्पित सहायता', 'इन्वेंटरी + मल्टी-ब्रांच', 'API एक्सेस'],
    recommended: 'अनुशंसित',
    cta_title: 'अपने व्यवसाय को आधुनिक बनाने के लिए तैयार?',
    cta_desc: 'सैकड़ों सऊदी व्यापारियों से जुड़ें जो हमारे POS सिस्टम पर भरोसा करते हैं।',
    cta_button: 'मुफ्त ट्रायल शुरू करें',
    footer_powered: 'CloudPOS द्वारा संचालित',
  },
  ur: {
    loading: 'لوڈ ہو رہا ہے...',
    not_found_title: 'ڈسٹریبیوٹر نہیں ملا',
    not_found_desc: 'یہ صفحہ موجود نہیں ہے یا غیر فعال کر دیا گیا ہے۔',
    go_main: 'مرکزی سائٹ پر جائیں',
    hero_badge: 'مجاز POS فراہم کنندہ',
    hero_title: 'استعمال میں آسان POS سسٹم',
    hero_subtitle: 'سعودی کاروبار کے لیے ڈیزائن کیا گیا جدید، ZATCA تعمیل POS سسٹم۔ تیز، قابل اعتماد، اور آپ کی زبان میں دستیاب۔',
    hero_cta: 'مفت ٹرائل شروع کریں',
    hero_cta2: 'ہم سے رابطہ کریں',
    features_title: 'آپ کے کاروبار کو جو کچھ چاہیے',
    features_subtitle: 'سعودی تاجروں کے لیے ڈیزائن کی گئی طاقتور خصوصیات',
    feature_1: 'تیز چیک آؤٹ',
    feature_1_desc: 'بدیہی انٹرفیس کے ساتھ سیکنڈوں میں سیلز پروسیس کریں۔',
    feature_2: 'ZATCA QR انوائس',
    feature_2_desc: 'QR کوڈز کے ساتھ تعمیل ای-انوائس خودکار طور پر بنائیں۔',
    feature_3: 'انوینٹری مینجمنٹ',
    feature_3_desc: 'اسٹاک لیول ٹریک کریں، کم اسٹاک الرٹس حاصل کریں۔',
    feature_4: 'کثیر لسانی',
    feature_4_desc: 'عربی، انگریزی، ہندی اور اردو کے لیے مکمل سپورٹ۔',
    feature_5: 'ریئل ٹائم رپورٹس',
    feature_5_desc: 'سیلز اینالیٹکس اور ریونیو ٹریکنگ۔',
    feature_6: 'کلاؤڈ بیسڈ',
    feature_6_desc: 'کہیں بھی، کبھی بھی اپنا ڈیٹا ایکسیس کریں۔',
    trust_title: 'سعودی کاروبار کا اعتماد',
    trust_zatca: 'ZATCA تصدیق شدہ',
    trust_saudi: 'سعودی ساختہ',
    trust_support: '24/7 سپورٹ',
    trust_zatca_desc: 'ای-انوائسنگ ضوابط کے ساتھ مکمل تعمیل',
    trust_saudi_desc: 'سعودی مارکیٹ کے لیے بنایا گیا',
    trust_support_desc: 'جب آپ کو ضرورت ہو ہمیشہ یہاں',
    merchant_title: 'ہزاروں خوش تاجروں سے جڑیں',
    merchant_desc: 'ہمارا POS سسٹم سعودی عرب بھر کے کاروبار کی مدد کرتا ہے۔',
    pricing_title: 'سادہ قیمتیں',
    pricing_subtitle: 'اپنے کاروبار کے لیے صحیح پلان منتخب کریں',
    basic: 'بنیادی',
    pro: 'پروفیشنل',
    premium: 'پریمیم',
    per_month: '/ماہ',
    basic_features: ['1 ٹرمینل', 'بنیادی رپورٹس', 'ZATCA تعمیل', 'ای میل سپورٹ'],
    pro_features: ['3 ٹرمینل', 'ایڈوانسڈ رپورٹس', 'ZATCA تعمیل', 'ترجیحی سپورٹ', 'انوینٹری مینجمنٹ'],
    premium_features: ['لامحدود ٹرمینل', 'مکمل اینالیٹکس', 'ZATCA تعمیل', 'مخصوص سپورٹ', 'انوینٹری + ملٹی برانچ', 'API رسائی'],
    recommended: 'تجویز کردہ',
    cta_title: 'اپنے کاروبار کو جدید بنانے کے لیے تیار؟',
    cta_desc: 'سینکڑوں سعودی تاجروں سے جڑیں جو ہمارے POS سسٹم پر بھروسہ کرتے ہیں۔',
    cta_button: 'مفت ٹرائل شروع کریں',
    footer_powered: 'کلاؤڈ پوس کے ذریعے تقویت یافتہ',
  },
};

function AgentGeometricPattern({ color = '#006C35' }: { color?: string }) {
  return (
    <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <pattern id="agent-geo-pattern" x="0" y="0" width="50" height="50" patternUnits="userSpaceOnUse">
          <path d="M25 0L50 12.5L50 37.5L25 50L0 37.5L0 12.5Z" fill="none" stroke={color} strokeWidth="0.4" opacity="0.15" />
          <circle cx="25" cy="25" r="6" fill="none" stroke={color} strokeWidth="0.4" opacity="0.1" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#agent-geo-pattern)" />
    </svg>
  );
}

export default function AgentLandingPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const [profile, setProfile] = useState<AgentProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const navigate = useNavigate();
  const { language, setLanguage, isRTL } = useLanguage();
  const c = content[language] || content.en;

  useEffect(() => {
    if (agentId) {
      loadProfile(agentId);
    }
  }, [agentId]);

  async function loadProfile(id: string) {
    try {
      const data = await getAgentPublicProfile(id);
      setProfile(data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-slate-200 border-t-[#006C35] rounded-full animate-spin mx-auto" />
          <p className="text-slate-600">{c.loading}</p>
        </div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
        <Card className="bg-white border-slate-200 max-w-md w-full shadow-lg">
          <CardContent className="p-8 text-center space-y-4">
            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto">
              <Package className="w-8 h-8 text-slate-400" />
            </div>
            <h2 className="text-xl font-bold text-slate-900">{c.not_found_title}</h2>
            <p className="text-slate-600">{c.not_found_desc}</p>
            <Button onClick={() => navigate('/')} className="bg-[#006C35] hover:bg-[#005a2c] text-white">
              {c.go_main}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const primaryColor = profile.primary_color || '#006C35';
  const secondaryColor = profile.secondary_color || '#C8A415';

  const featureItems = [
    { icon: Zap, title: c.feature_1, desc: c.feature_1_desc },
    { icon: FileCheck, title: c.feature_2, desc: c.feature_2_desc },
    { icon: Package, title: c.feature_3, desc: c.feature_3_desc },
    { icon: Globe, title: c.feature_4, desc: c.feature_4_desc },
    { icon: BarChart3, title: c.feature_5, desc: c.feature_5_desc },
    { icon: Cloud, title: c.feature_6, desc: c.feature_6_desc },
  ];

  const trustItems = [
    { icon: ShieldCheck, title: c.trust_zatca, desc: c.trust_zatca_desc },
    { icon: Globe, title: c.trust_saudi, desc: c.trust_saudi_desc },
    { icon: Headphones, title: c.trust_support, desc: c.trust_support_desc },
  ];

  const plans = [
    { name: c.basic, price: '49', features: c.basic_features, highlight: false },
    { name: c.pro, price: '129', features: c.pro_features, highlight: true },
    { name: c.premium, price: '299', features: c.premium_features, highlight: false },
  ];

  return (
    <div className={`min-h-screen bg-white text-slate-900 ${isRTL ? 'font-arabic' : ''}`} dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Top accent bar */}
      <div className="h-1.5 w-full" style={{ background: `linear-gradient(to right, ${primaryColor}, ${secondaryColor}, ${primaryColor})` }} />

      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white/95 backdrop-blur-md border-b border-slate-100 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {profile.logo_url ? (
              <img src={profile.logo_url} alt={profile.company_name} className="h-10 w-10 rounded-xl object-cover" />
            ) : (
              <div
                className="h-10 w-10 rounded-xl flex items-center justify-center font-bold text-white text-lg shadow-md"
                style={{ backgroundColor: primaryColor }}
              >
                {profile.company_name?.charAt(0) || 'D'}
              </div>
            )}
            <span className="text-xl font-bold" style={{ color: primaryColor }}>{profile.company_name}</span>
          </div>
          <div className="flex items-center gap-3">
            <Select value={language} onValueChange={(v) => setLanguage(v as Language)}>
              <SelectTrigger className="w-28 bg-slate-50 border-slate-200 text-slate-700 text-sm h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-white border-slate-200">
                {languageOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value} className="text-slate-700 hover:bg-slate-50">
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              onClick={() => navigate('/login')}
              className="text-white font-semibold px-6"
              style={{ backgroundColor: primaryColor }}
            >
              {c.hero_cta}
            </Button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="py-20 px-6 relative overflow-hidden">
        {/* Geometric pattern background */}
        <div className="absolute inset-0 opacity-100">
          <AgentGeometricPattern color={primaryColor} />
        </div>
        {/* Decorative blurs */}
        <div className="absolute top-10 right-10 w-64 h-64 rounded-full blur-3xl opacity-10" style={{ backgroundColor: primaryColor }} />
        <div className="absolute bottom-10 left-10 w-80 h-80 rounded-full blur-3xl opacity-5" style={{ backgroundColor: secondaryColor }} />

        <div className="relative max-w-7xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
          <div className={`space-y-8 ${isRTL ? 'lg:order-2' : ''}`}>
            <Badge
              className="px-4 py-2 text-sm font-medium border"
              style={{ backgroundColor: `${primaryColor}10`, color: primaryColor, borderColor: `${primaryColor}30` }}
            >
              {c.hero_badge}
            </Badge>
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight text-slate-900">
              {c.hero_title}
            </h1>
            <p className="text-lg text-slate-600 leading-relaxed max-w-xl">
              {c.hero_subtitle}
            </p>
            <div className="flex flex-wrap gap-4 pt-2">
              <Button
                onClick={() => navigate('/login')}
                className="text-white px-8 py-6 text-lg font-bold shadow-xl transition-all hover:scale-105"
                style={{ backgroundColor: primaryColor, boxShadow: `0 10px 30px ${primaryColor}30` }}
              >
                {c.hero_cta}
                <ArrowRight className={`w-5 h-5 ${isRTL ? 'mr-2 rotate-180' : 'ml-2'}`} />
              </Button>
              <Button
                variant="outline"
                className="px-8 py-6 text-lg font-medium border-2 !bg-transparent"
                style={{ borderColor: primaryColor, color: primaryColor }}
                onClick={() => document.getElementById('contact-section')?.scrollIntoView({ behavior: 'smooth' })}
              >
                {c.hero_cta2}
              </Button>
            </div>
          </div>
          <div className={`relative ${isRTL ? 'lg:order-1' : ''}`}>
            {/* POS Terminal illustration using icons and gradients */}
            <div className="relative w-full max-w-sm mx-auto">
              {/* Main terminal shape */}
              <div className="rounded-3xl p-8 border border-slate-200 shadow-2xl" style={{ background: `linear-gradient(135deg, ${primaryColor}08, ${secondaryColor}08)` }}>
                {/* Screen */}
                <div className="rounded-2xl p-6 mb-6 border border-slate-100" style={{ background: `linear-gradient(180deg, white, ${primaryColor}05)` }}>
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${primaryColor}15` }}>
                        <Store className="w-4 h-4" style={{ color: primaryColor }} />
                      </div>
                      <div className="h-2 w-16 rounded-full bg-slate-200" />
                    </div>
                    <div className="h-2 w-10 rounded-full" style={{ backgroundColor: `${secondaryColor}40` }} />
                  </div>
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
                        <CreditCard className="w-5 h-5 text-slate-400" />
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="h-2 w-3/4 rounded-full bg-slate-200" />
                        <div className="h-2 w-1/2 rounded-full bg-slate-100" />
                      </div>
                      <div className="h-3 w-12 rounded-full" style={{ backgroundColor: `${primaryColor}20` }} />
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
                        <Receipt className="w-5 h-5 text-slate-400" />
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="h-2 w-2/3 rounded-full bg-slate-200" />
                        <div className="h-2 w-1/3 rounded-full bg-slate-100" />
                      </div>
                      <div className="h-3 w-12 rounded-full" style={{ backgroundColor: `${secondaryColor}20` }} />
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
                        <Package className="w-5 h-5 text-slate-400" />
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="h-2 w-4/5 rounded-full bg-slate-200" />
                        <div className="h-2 w-2/5 rounded-full bg-slate-100" />
                      </div>
                      <div className="h-3 w-12 rounded-full" style={{ backgroundColor: `${primaryColor}20` }} />
                    </div>
                  </div>
                </div>
                {/* Bottom bar */}
                <div className="flex items-center justify-between">
                  <div className="flex gap-2">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${primaryColor}15` }}>
                      <Monitor className="w-5 h-5" style={{ color: primaryColor }} />
                    </div>
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${secondaryColor}15` }}>
                      <BarChart3 className="w-5 h-5" style={{ color: secondaryColor }} />
                    </div>
                  </div>
                  <div className="px-4 py-2 rounded-xl text-white text-sm font-bold" style={{ backgroundColor: primaryColor }}>
                    SAR 1,250
                  </div>
                </div>
              </div>
              {/* Floating badges */}
              <div className="absolute -top-3 -right-3 w-14 h-14 rounded-2xl shadow-lg flex items-center justify-center bg-white border border-slate-100">
                <ShieldCheck className="w-7 h-7" style={{ color: primaryColor }} />
              </div>
              <div className="absolute -bottom-3 -left-3 w-14 h-14 rounded-2xl shadow-lg flex items-center justify-center bg-white border border-slate-100">
                <Zap className="w-7 h-7" style={{ color: secondaryColor }} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24 px-6 bg-slate-50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16 space-y-4">
            <h2 className="text-3xl md:text-4xl font-bold text-slate-900">{c.features_title}</h2>
            <p className="text-lg text-slate-600 max-w-2xl mx-auto">{c.features_subtitle}</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {featureItems.map((item, idx) => {
              const Icon = item.icon;
              return (
                <Card key={idx} className="bg-white border-slate-200 shadow-sm hover:shadow-lg transition-all duration-300 group hover:-translate-y-1">
                  <CardContent className="p-8 space-y-4">
                    <div
                      className="w-14 h-14 rounded-2xl flex items-center justify-center transition-all duration-300"
                      style={{ backgroundColor: `${primaryColor}10` }}
                    >
                      <Icon className="w-7 h-7" style={{ color: primaryColor }} />
                    </div>
                    <h3 className="text-xl font-bold text-slate-900">{item.title}</h3>
                    <p className="text-slate-600 leading-relaxed">{item.desc}</p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      </section>

      {/* Trust Badges Section */}
      <section className="py-20 px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-12 text-slate-900">{c.trust_title}</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {trustItems.map((item, idx) => {
              const Icon = item.icon;
              return (
                <div key={idx} className="text-center space-y-4 p-8 rounded-2xl border border-slate-200 bg-white shadow-sm">
                  <div
                    className="w-16 h-16 rounded-full mx-auto flex items-center justify-center"
                    style={{ backgroundColor: `${primaryColor}10` }}
                  >
                    <Icon className="w-8 h-8" style={{ color: primaryColor }} />
                  </div>
                  <h3 className="text-xl font-bold text-slate-900">{item.title}</h3>
                  <p className="text-slate-600">{item.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Happy Merchants Section */}
      <section className="py-24 px-6 bg-slate-50">
        <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
          <div className={`${isRTL ? 'lg:order-2' : ''}`}>
            {/* Abstract merchant success illustration */}
            <div className="relative rounded-3xl p-8 border border-slate-200" style={{ background: `linear-gradient(135deg, ${primaryColor}05, ${secondaryColor}08)` }}>
              <div className="flex flex-col items-center justify-center py-6 space-y-6">
                <div className="w-20 h-20 rounded-full flex items-center justify-center shadow-lg" style={{ background: `linear-gradient(135deg, ${primaryColor}, ${primaryColor}cc)` }}>
                  <Users className="w-10 h-10 text-white" />
                </div>
                <div className="grid grid-cols-3 gap-4 w-full">
                  <div className="bg-white rounded-xl p-4 text-center border border-slate-100 shadow-sm">
                    <TrendingUp className="w-6 h-6 mx-auto mb-2" style={{ color: primaryColor }} />
                    <div className="text-lg font-bold" style={{ color: primaryColor }}>+85%</div>
                    <div className="text-xs text-slate-500">{language === 'ar' || language === 'ur' ? 'كفاءة' : 'Efficiency'}</div>
                  </div>
                  <div className="bg-white rounded-xl p-4 text-center border border-slate-100 shadow-sm">
                    <Zap className="w-6 h-6 mx-auto mb-2" style={{ color: secondaryColor }} />
                    <div className="text-lg font-bold" style={{ color: secondaryColor }}>3s</div>
                    <div className="text-xs text-slate-500">{language === 'ar' || language === 'ur' ? 'دفع' : 'Checkout'}</div>
                  </div>
                  <div className="bg-white rounded-xl p-4 text-center border border-slate-100 shadow-sm">
                    <ShieldCheck className="w-6 h-6 mx-auto mb-2" style={{ color: primaryColor }} />
                    <div className="text-lg font-bold" style={{ color: primaryColor }}>100%</div>
                    <div className="text-xs text-slate-500">ZATCA</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className={`space-y-6 ${isRTL ? 'lg:order-1' : ''}`}>
            <h2 className="text-3xl md:text-4xl font-bold text-slate-900 leading-tight">
              {c.merchant_title}
            </h2>
            <p className="text-lg text-slate-600 leading-relaxed">
              {c.merchant_desc}
            </p>
            <div className="grid grid-cols-2 gap-4 pt-4">
              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="text-3xl font-bold" style={{ color: primaryColor }}>2,500+</div>
                <div className="text-sm text-slate-500">{language === 'ar' || language === 'ur' ? 'تاجر نشط' : 'Active Merchants'}</div>
              </div>
              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="text-3xl font-bold" style={{ color: secondaryColor }}>98%</div>
                <div className="text-sm text-slate-500">{language === 'ar' || language === 'ur' ? 'رضا العملاء' : 'Satisfaction'}</div>
              </div>
            </div>
            <Button
              onClick={() => navigate('/login')}
              className="text-white px-8 py-6 text-lg font-bold mt-4"
              style={{ backgroundColor: primaryColor }}
            >
              {c.hero_cta}
            </Button>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16 space-y-4">
            <h2 className="text-3xl md:text-4xl font-bold text-slate-900">{c.pricing_title}</h2>
            <p className="text-lg text-slate-600">{c.pricing_subtitle}</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {plans.map((plan, idx) => (
              <Card
                key={idx}
                className={`relative overflow-hidden transition-all duration-300 hover:scale-105 ${
                  plan.highlight
                    ? 'border-2 shadow-xl bg-white'
                    : 'border-slate-200 bg-white shadow-sm'
                }`}
                style={plan.highlight ? { borderColor: primaryColor, boxShadow: `0 10px 40px ${primaryColor}15` } : {}}
              >
                {plan.highlight && (
                  <>
                    <div className="absolute top-0 inset-x-0 h-1.5" style={{ background: `linear-gradient(to right, ${primaryColor}, ${secondaryColor})` }} />
                    <div className="absolute top-0 right-0">
                      <Badge className="text-white border-0 rounded-none rounded-bl-lg px-3 py-1 text-xs font-bold" style={{ backgroundColor: secondaryColor }}>
                        {c.recommended}
                      </Badge>
                    </div>
                  </>
                )}
                <CardContent className="p-8 space-y-6">
                  <div>
                    <h3 className="text-xl font-bold text-slate-900">{plan.name}</h3>
                    <div className="mt-4 flex items-baseline gap-1">
                      <span className="text-sm text-slate-500">SAR</span>
                      <span className="text-4xl font-bold" style={{ color: primaryColor }}>{plan.price}</span>
                      <span className="text-slate-500">{c.per_month}</span>
                    </div>
                  </div>
                  <ul className="space-y-3">
                    {plan.features.map((feature, fIdx) => (
                      <li key={fIdx} className="flex items-center gap-3 text-slate-700 text-sm">
                        <CheckCircle2 className="w-5 h-5 flex-shrink-0" style={{ color: primaryColor }} />
                        {feature}
                      </li>
                    ))}
                  </ul>
                  <Button
                    className={`w-full py-6 font-bold text-base ${plan.highlight ? 'text-white' : ''}`}
                    style={plan.highlight ? { backgroundColor: primaryColor } : { backgroundColor: '#f1f5f9', color: '#1e293b' }}
                    onClick={() => navigate('/login')}
                  >
                    {c.hero_cta}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section id="contact-section" className="py-20 px-6 relative overflow-hidden" style={{ background: `linear-gradient(135deg, ${primaryColor}, ${primaryColor}dd)` }}>
        {/* Decorative elements */}
        <div className="absolute inset-0 opacity-100">
          <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <pattern id="cta-pattern" x="0" y="0" width="40" height="40" patternUnits="userSpaceOnUse">
                <circle cx="20" cy="20" r="1.5" fill="white" opacity="0.1" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#cta-pattern)" />
          </svg>
        </div>
        <div className="absolute top-0 right-0 w-64 h-64 rounded-full blur-3xl opacity-20" style={{ backgroundColor: secondaryColor }} />
        <div className="absolute bottom-0 left-0 w-48 h-48 rounded-full blur-3xl opacity-10 bg-white" />

        <div className="relative max-w-4xl mx-auto text-center space-y-8">
          <h2 className="text-3xl md:text-4xl font-bold text-white">{c.cta_title}</h2>
          <p className="text-xl text-white/80 max-w-2xl mx-auto">{c.cta_desc}</p>
          <div className="flex flex-wrap justify-center gap-4">
            <Button
              onClick={() => navigate('/login')}
              className="px-10 py-6 text-lg font-bold shadow-xl transition-all hover:scale-105"
              style={{ backgroundColor: secondaryColor, color: 'white' }}
            >
              {c.cta_button}
              <ArrowRight className={`w-5 h-5 ${isRTL ? 'mr-2 rotate-180' : 'ml-2'}`} />
            </Button>
          </div>
          {(profile.contact_email || profile.contact_phone) && (
            <div className="flex flex-wrap justify-center gap-6 pt-4 text-white/90">
              {profile.contact_email && (
                <div className="flex items-center gap-2">
                  <Mail className="w-5 h-5" />
                  <span>{profile.contact_email}</span>
                </div>
              )}
              {profile.contact_phone && (
                <div className="flex items-center gap-2">
                  <Phone className="w-5 h-5" />
                  <span>{profile.contact_phone}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-slate-900 text-white py-12 px-6">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            {profile.logo_url ? (
              <img src={profile.logo_url} alt={profile.company_name} className="h-8 w-8 rounded-lg object-cover" />
            ) : (
              <div
                className="h-8 w-8 rounded-lg flex items-center justify-center font-bold text-white text-sm"
                style={{ backgroundColor: primaryColor }}
              >
                {profile.company_name?.charAt(0) || 'D'}
              </div>
            )}
            <span className="font-bold">{profile.company_name}</span>
          </div>
          <div className="text-sm text-slate-400">
            © 2026 {profile.company_name}. {c.footer_powered}
          </div>
          <div className="flex gap-6 text-sm text-slate-400">
            {profile.contact_email && <span>{profile.contact_email}</span>}
            {profile.contact_phone && <span>{profile.contact_phone}</span>}
          </div>
        </div>
      </footer>
    </div>
  );
}