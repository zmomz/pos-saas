import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { Building2, TrendingUp, Headphones, ShieldCheck, Users, BarChart3, ArrowRight, Star, CheckCircle2, Monitor, Smartphone, CreditCard, Receipt, Store, Layers } from 'lucide-react';

const content = {
  en: {
    nav_brand: 'CloudPOS',
    hero_badge: 'Saudi Vision 2030 Partner',
    hero_title_1: 'Start Your Software Company',
    hero_title_2: 'Increase Your Income',
    hero_subtitle: 'We are your technical partner. Get a fully white-labeled POS system, sell it under your brand, and earn recurring revenue — no coding required.',
    hero_cta: 'Start Your Business Today',
    hero_cta2: 'Learn How It Works',
    partnership_badge: 'Business Model',
    partnership_title: 'Your Brand. Our Technology.',
    partnership_desc: 'We provide the complete POS infrastructure — you customize it with your brand and sell to merchants across Saudi Arabia. Keep 100% of your client relationships.',
    features_title: 'Everything You Need to Succeed',
    features_subtitle: 'A complete business-in-a-box solution designed for Saudi entrepreneurs',
    feature_1_title: 'White-Label System',
    feature_1_desc: 'Your logo, your colors, your brand name. Clients will never know about us.',
    feature_2_title: 'Recurring Revenue',
    feature_2_desc: 'Earn monthly subscription fees from every client. Build passive income.',
    feature_3_title: 'Full Technical Support',
    feature_3_desc: '24/7 support team handles all technical issues. You focus on sales.',
    feature_4_title: 'ZATCA Compliant',
    feature_4_desc: 'Fully compliant with Saudi tax authority e-invoicing requirements.',
    feature_5_title: 'Multi-Tenant Platform',
    feature_5_desc: 'Manage unlimited clients from one dashboard with complete data isolation.',
    feature_6_title: 'Analytics & Reports',
    feature_6_desc: 'Track your revenue, client growth, and business performance in real-time.',
    how_title: 'How It Works',
    how_subtitle: 'Four simple steps to launch your POS business',
    step_1: 'Sign Up',
    step_1_desc: 'Register as a distributor and choose your package',
    step_2: 'Customize',
    step_2_desc: 'Add your brand, logo, colors, and domain',
    step_3: 'Sell',
    step_3_desc: 'Market to merchants and onboard clients',
    step_4: 'Earn',
    step_4_desc: 'Collect monthly fees and grow your business',
    testimonial_title: 'Success Stories',
    testimonial_quote: '"I started with 3 clients and now manage 47 merchants across Riyadh. CloudPOS made it possible to run a tech company without writing a single line of code."',
    testimonial_name: 'Mohammed Al-Rashid',
    testimonial_role: 'Founder, AlRashid POS Solutions',
    pricing_title: 'Distributor Packages',
    pricing_subtitle: 'Choose the package that matches your ambition',
    starter: 'Starter',
    business: 'Business',
    enterprise: 'Enterprise',
    per_month: '/month',
    popular: 'Most Popular',
    starter_features: ['Up to 5 clients', 'Basic branding', 'Email support', 'ZATCA compliant', 'Standard reports'],
    business_features: ['Up to 25 clients', 'Full white-label', 'Priority support', 'ZATCA compliant', 'Advanced analytics', 'Custom domain'],
    enterprise_features: ['Unlimited clients', 'Premium branding', 'Dedicated manager', 'ZATCA compliant', 'API access', 'Custom features', 'SLA guarantee'],
    footer_brand: 'CloudPOS',
    footer_desc: 'Empowering Saudi entrepreneurs with world-class POS technology.',
    footer_cr: 'CR: 1234567890',
    footer_vat: 'VAT: 300000000000003',
    footer_rights: '© 2026 CloudPOS. All rights reserved.',
    footer_privacy: 'Privacy Policy',
    footer_terms: 'Terms of Service',
    footer_contact: 'Contact Us',
  },
  ar: {
    nav_brand: 'كلاود بوس',
    hero_badge: 'شريك رؤية السعودية 2030',
    hero_title_1: 'ابدأ شركتك التقنية',
    hero_title_2: 'زِد دخلك',
    hero_subtitle: 'نحن شريكك التقني. احصل على نظام نقاط بيع كامل بعلامتك التجارية، وبعه باسمك، واكسب دخلاً متكرراً — بدون برمجة.',
    hero_cta: 'ابدأ عملك اليوم',
    hero_cta2: 'تعرف على طريقة العمل',
    partnership_badge: 'نموذج العمل',
    partnership_title: 'علامتك التجارية. تقنيتنا.',
    partnership_desc: 'نحن نوفر البنية التحتية الكاملة لنقاط البيع — أنت تخصصها بعلامتك التجارية وتبيعها للتجار في جميع أنحاء المملكة.',
    features_title: 'كل ما تحتاجه للنجاح',
    features_subtitle: 'حل متكامل مصمم لرواد الأعمال السعوديين',
    feature_1_title: 'نظام العلامة البيضاء',
    feature_1_desc: 'شعارك، ألوانك، اسم علامتك. عملاؤك لن يعرفوا عنا.',
    feature_2_title: 'دخل متكرر',
    feature_2_desc: 'اكسب رسوم اشتراك شهرية من كل عميل. ابنِ دخلاً سلبياً.',
    feature_3_title: 'دعم فني كامل',
    feature_3_desc: 'فريق دعم على مدار الساعة يتولى جميع المشاكل التقنية.',
    feature_4_title: 'متوافق مع زاتكا',
    feature_4_desc: 'متوافق بالكامل مع متطلبات الفوترة الإلكترونية لهيئة الزكاة والضريبة.',
    feature_5_title: 'منصة متعددة المستأجرين',
    feature_5_desc: 'إدارة عملاء غير محدودين من لوحة تحكم واحدة مع عزل كامل للبيانات.',
    feature_6_title: 'تحليلات وتقارير',
    feature_6_desc: 'تتبع إيراداتك ونمو عملائك وأداء عملك في الوقت الفعلي.',
    how_title: 'كيف يعمل',
    how_subtitle: 'أربع خطوات بسيطة لإطلاق عملك',
    step_1: 'سجّل',
    step_1_desc: 'سجّل كموزع واختر باقتك',
    step_2: 'خصّص',
    step_2_desc: 'أضف علامتك التجارية وشعارك وألوانك',
    step_3: 'بِع',
    step_3_desc: 'سوّق للتجار وأضف العملاء',
    step_4: 'اكسب',
    step_4_desc: 'اجمع الرسوم الشهرية ونمِّ عملك',
    testimonial_title: 'قصص نجاح',
    testimonial_quote: '"بدأت بـ 3 عملاء والآن أدير 47 تاجراً في الرياض. كلاود بوس جعل من الممكن إدارة شركة تقنية بدون كتابة سطر برمجي واحد."',
    testimonial_name: 'محمد الراشد',
    testimonial_role: 'مؤسس، حلول الراشد لنقاط البيع',
    pricing_title: 'باقات الموزعين',
    pricing_subtitle: 'اختر الباقة التي تناسب طموحك',
    starter: 'المبتدئ',
    business: 'الأعمال',
    enterprise: 'المؤسسات',
    per_month: '/شهرياً',
    popular: 'الأكثر شعبية',
    starter_features: ['حتى 5 عملاء', 'علامة تجارية أساسية', 'دعم بالبريد', 'متوافق مع زاتكا', 'تقارير قياسية'],
    business_features: ['حتى 25 عميل', 'علامة بيضاء كاملة', 'دعم أولوية', 'متوافق مع زاتكا', 'تحليلات متقدمة', 'نطاق مخصص'],
    enterprise_features: ['عملاء غير محدودين', 'علامة تجارية مميزة', 'مدير مخصص', 'متوافق مع زاتكا', 'وصول API', 'ميزات مخصصة', 'ضمان SLA'],
    footer_brand: 'كلاود بوس',
    footer_desc: 'تمكين رواد الأعمال السعوديين بتقنية نقاط بيع عالمية.',
    footer_cr: 'سجل تجاري: 1234567890',
    footer_vat: 'رقم ضريبي: 300000000000003',
    footer_rights: '© 2026 كلاود بوس. جميع الحقوق محفوظة.',
    footer_privacy: 'سياسة الخصوصية',
    footer_terms: 'شروط الخدمة',
    footer_contact: 'اتصل بنا',
  },
  hi: {
    nav_brand: 'CloudPOS',
    hero_badge: 'सऊदी विजन 2030 पार्टनर',
    hero_title_1: 'अपनी सॉफ्टवेयर कंपनी शुरू करें',
    hero_title_2: 'अपनी आय बढ़ाएं',
    hero_subtitle: 'हम आपके तकनीकी साझेदार हैं। एक पूर्ण व्हाइट-लेबल POS सिस्टम प्राप्त करें, इसे अपने ब्रांड के तहत बेचें, और आवर्ती राजस्व अर्जित करें।',
    hero_cta: 'आज ही अपना व्यवसाय शुरू करें',
    hero_cta2: 'जानें कैसे काम करता है',
    partnership_badge: 'बिज़नेस मॉडल',
    partnership_title: 'आपका ब्रांड। हमारी तकनीक।',
    partnership_desc: 'हम पूर्ण POS बुनियादी ढांचा प्रदान करते हैं — आप इसे अपने ब्रांड के साथ अनुकूलित करें और सऊदी अरब भर के व्यापारियों को बेचें।',
    features_title: 'सफलता के लिए सब कुछ',
    features_subtitle: 'सऊदी उद्यमियों के लिए डिज़ाइन किया गया संपूर्ण समाधान',
    feature_1_title: 'व्हाइट-लेबल सिस्टम',
    feature_1_desc: 'आपका लोगो, आपके रंग, आपका ब्रांड नाम। ग्राहकों को हमारे बारे में पता नहीं चलेगा।',
    feature_2_title: 'आवर्ती राजस्व',
    feature_2_desc: 'हर ग्राहक से मासिक सदस्यता शुल्क अर्जित करें।',
    feature_3_title: 'पूर्ण तकनीकी सहायता',
    feature_3_desc: '24/7 सहायता टीम सभी तकनीकी समस्याओं को संभालती है।',
    feature_4_title: 'ZATCA अनुपालन',
    feature_4_desc: 'सऊदी कर प्राधिकरण ई-इनवॉइसिंग आवश्यकताओं के साथ पूर्ण अनुपालन।',
    feature_5_title: 'मल्टी-टेनेंट प्लेटफॉर्म',
    feature_5_desc: 'एक डैशबोर्ड से असीमित ग्राहकों का प्रबंधन करें।',
    feature_6_title: 'एनालिटिक्स और रिपोर्ट',
    feature_6_desc: 'अपने राजस्व और व्यवसाय प्रदर्शन को रियल-टाइम में ट्रैक करें।',
    how_title: 'कैसे काम करता है',
    how_subtitle: 'अपना POS व्यवसाय शुरू करने के चार सरल कदम',
    step_1: 'साइन अप',
    step_1_desc: 'डिस्ट्रीब्यूटर के रूप में पंजीकरण करें',
    step_2: 'कस्टमाइज़',
    step_2_desc: 'अपना ब्रांड, लोगो, रंग जोड़ें',
    step_3: 'बेचें',
    step_3_desc: 'व्यापारियों को मार्केट करें और ग्राहक जोड़ें',
    step_4: 'कमाएं',
    step_4_desc: 'मासिक शुल्क एकत्र करें और बढ़ें',
    testimonial_title: 'सफलता की कहानियां',
    testimonial_quote: '"मैंने 3 ग्राहकों से शुरू किया और अब रियाद में 47 व्यापारियों का प्रबंधन करता हूं।"',
    testimonial_name: 'मोहम्मद अल-राशिद',
    testimonial_role: 'संस्थापक, अल-राशिद POS सॉल्यूशंस',
    pricing_title: 'डिस्ट्रीब्यूटर पैकेज',
    pricing_subtitle: 'अपनी महत्वाकांक्षा से मेल खाने वाला पैकेज चुनें',
    starter: 'स्टार्टर',
    business: 'बिज़नेस',
    enterprise: 'एंटरप्राइज़',
    per_month: '/माह',
    popular: 'सबसे लोकप्रिय',
    starter_features: ['5 ग्राहक तक', 'बेसिक ब्रांडिंग', 'ईमेल सहायता', 'ZATCA अनुपालन', 'मानक रिपोर्ट'],
    business_features: ['25 ग्राहक तक', 'पूर्ण व्हाइट-लेबल', 'प्राथमिकता सहायता', 'ZATCA अनुपालन', 'उन्नत एनालिटिक्स', 'कस्टम डोमेन'],
    enterprise_features: ['असीमित ग्राहक', 'प्रीमियम ब्रांडिंग', 'समर्पित प्रबंधक', 'ZATCA अनुपालन', 'API एक्सेस', 'कस्टम सुविधाएं', 'SLA गारंटी'],
    footer_brand: 'CloudPOS',
    footer_desc: 'विश्व स्तरीय POS तकनीक के साथ सऊदी उद्यमियों को सशक्त बनाना।',
    footer_cr: 'CR: 1234567890',
    footer_vat: 'VAT: 300000000000003',
    footer_rights: '© 2026 CloudPOS. सर्वाधिकार सुरक्षित।',
    footer_privacy: 'गोपनीयता नीति',
    footer_terms: 'सेवा की शर्तें',
    footer_contact: 'संपर्क करें',
  },
  ur: {
    nav_brand: 'کلاؤڈ پوس',
    hero_badge: 'سعودی ویژن 2030 پارٹنر',
    hero_title_1: 'اپنی سافٹ ویئر کمپنی شروع کریں',
    hero_title_2: 'اپنی آمدنی بڑھائیں',
    hero_subtitle: 'ہم آپ کے تکنیکی شراکت دار ہیں۔ مکمل وائٹ لیبل POS سسٹم حاصل کریں، اپنے برانڈ کے تحت بیچیں، اور بار بار آمدنی کمائیں۔',
    hero_cta: 'آج ہی اپنا کاروبار شروع کریں',
    hero_cta2: 'جانیں کیسے کام کرتا ہے',
    partnership_badge: 'بزنس ماڈل',
    partnership_title: 'آپ کا برانڈ۔ ہماری ٹیکنالوجی۔',
    partnership_desc: 'ہم مکمل POS انفراسٹرکچر فراہم کرتے ہیں — آپ اسے اپنے برانڈ کے ساتھ حسب ضرورت بنائیں اور سعودی عرب بھر کے تاجروں کو بیچیں۔',
    features_title: 'کامیابی کے لیے سب کچھ',
    features_subtitle: 'سعودی کاروباری افراد کے لیے ڈیزائن کیا گیا مکمل حل',
    feature_1_title: 'وائٹ لیبل سسٹم',
    feature_1_desc: 'آپ کا لوگو، آپ کے رنگ، آپ کا برانڈ نام۔',
    feature_2_title: 'بار بار آمدنی',
    feature_2_desc: 'ہر کلائنٹ سے ماہانہ سبسکرپشن فیس کمائیں۔',
    feature_3_title: 'مکمل تکنیکی مدد',
    feature_3_desc: '24/7 سپورٹ ٹیم تمام تکنیکی مسائل سنبھالتی ہے۔',
    feature_4_title: 'ZATCA تعمیل',
    feature_4_desc: 'سعودی ٹیکس اتھارٹی ای-انوائسنگ کے ساتھ مکمل تعمیل۔',
    feature_5_title: 'ملٹی ٹیننٹ پلیٹ فارم',
    feature_5_desc: 'ایک ڈیش بورڈ سے لامحدود کلائنٹس کا انتظام کریں۔',
    feature_6_title: 'تجزیات اور رپورٹس',
    feature_6_desc: 'اپنی آمدنی اور کاروباری کارکردگی کو ریئل ٹائم میں ٹریک کریں۔',
    how_title: 'کیسے کام کرتا ہے',
    how_subtitle: 'اپنا POS کاروبار شروع کرنے کے چار آسان مراحل',
    step_1: 'سائن اپ',
    step_1_desc: 'ڈسٹریبیوٹر کے طور پر رجسٹر کریں',
    step_2: 'حسب ضرورت بنائیں',
    step_2_desc: 'اپنا برانڈ، لوگو، رنگ شامل کریں',
    step_3: 'بیچیں',
    step_3_desc: 'تاجروں کو مارکیٹ کریں اور کلائنٹس شامل کریں',
    step_4: 'کمائیں',
    step_4_desc: 'ماہانہ فیس جمع کریں اور بڑھیں',
    testimonial_title: 'کامیابی کی کہانیاں',
    testimonial_quote: '"میں نے 3 کلائنٹس سے شروع کیا اور اب ریاض میں 47 تاجروں کا انتظام کرتا ہوں۔"',
    testimonial_name: 'محمد الراشد',
    testimonial_role: 'بانی، الراشد POS سلوشنز',
    pricing_title: 'ڈسٹریبیوٹر پیکجز',
    pricing_subtitle: 'اپنی خواہش سے مطابقت رکھنے والا پیکج منتخب کریں',
    starter: 'اسٹارٹر',
    business: 'بزنس',
    enterprise: 'انٹرپرائز',
    per_month: '/ماہ',
    popular: 'سب سے مقبول',
    starter_features: ['5 کلائنٹس تک', 'بنیادی برانڈنگ', 'ای میل سپورٹ', 'ZATCA تعمیل', 'معیاری رپورٹس'],
    business_features: ['25 کلائنٹس تک', 'مکمل وائٹ لیبل', 'ترجیحی سپورٹ', 'ZATCA تعمیل', 'ایڈوانسڈ تجزیات', 'کسٹم ڈومین'],
    enterprise_features: ['لامحدود کلائنٹس', 'پریمیم برانڈنگ', 'مخصوص مینیجر', 'ZATCA تعمیل', 'API رسائی', 'کسٹم فیچرز', 'SLA گارنٹی'],
    footer_brand: 'کلاؤڈ پوس',
    footer_desc: 'عالمی معیار کی POS ٹیکنالوجی کے ساتھ سعودی کاروباری افراد کو بااختیار بنانا۔',
    footer_cr: 'CR: 1234567890',
    footer_vat: 'VAT: 300000000000003',
    footer_rights: '© 2026 کلاؤڈ پوس۔ جملہ حقوق محفوظ ہیں۔',
    footer_privacy: 'رازداری کی پالیسی',
    footer_terms: 'سروس کی شرائط',
    footer_contact: 'ہم سے رابطہ کریں',
  },
};

function GeometricPattern({ className = '' }: { className?: string }) {
  return (
    <svg className={className} width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <pattern id="islamic-geo" x="0" y="0" width="60" height="60" patternUnits="userSpaceOnUse">
          <path d="M30 0L60 15L60 45L30 60L0 45L0 15Z" fill="none" stroke="currentColor" strokeWidth="0.5" opacity="0.3" />
          <circle cx="30" cy="30" r="8" fill="none" stroke="currentColor" strokeWidth="0.5" opacity="0.2" />
          <path d="M30 0L30 60M0 30L60 30" stroke="currentColor" strokeWidth="0.3" opacity="0.1" />
          <path d="M15 7.5L45 7.5M15 52.5L45 52.5" stroke="currentColor" strokeWidth="0.3" opacity="0.15" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#islamic-geo)" />
    </svg>
  );
}

function HeroIllustration({ isRTL }: { isRTL: boolean }) {
  return (
    <div className={`hidden lg:flex items-center justify-center ${isRTL ? 'lg:order-1' : ''}`}>
      <div className="relative w-80 h-80">
        {/* Outer ring */}
        <div className="absolute inset-0 rounded-full border-2 border-[#C8A415]/30 animate-[spin_20s_linear_infinite]" />
        {/* Inner decorative circles */}
        <div className="absolute inset-4 rounded-full border border-white/20" />
        <div className="absolute inset-8 rounded-full border border-white/10" />
        {/* Center icon cluster */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-32 h-32 rounded-3xl bg-white/10 backdrop-blur-sm border border-white/20 flex items-center justify-center shadow-2xl">
            <Monitor className="w-16 h-16 text-white" />
          </div>
        </div>
        {/* Floating icons */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 w-12 h-12 rounded-xl bg-[#C8A415]/20 backdrop-blur-sm flex items-center justify-center border border-[#C8A415]/30">
          <CreditCard className="w-6 h-6 text-[#C8A415]" />
        </div>
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 w-12 h-12 rounded-xl bg-white/10 backdrop-blur-sm flex items-center justify-center border border-white/20">
          <Receipt className="w-6 h-6 text-white" />
        </div>
        <div className="absolute left-4 top-1/2 -translate-y-1/2 w-12 h-12 rounded-xl bg-white/10 backdrop-blur-sm flex items-center justify-center border border-white/20">
          <Store className="w-6 h-6 text-white" />
        </div>
        <div className="absolute right-4 top-1/2 -translate-y-1/2 w-12 h-12 rounded-xl bg-[#C8A415]/20 backdrop-blur-sm flex items-center justify-center border border-[#C8A415]/30">
          <Smartphone className="w-6 h-6 text-[#C8A415]" />
        </div>
        {/* Corner dots */}
        <div className="absolute top-12 left-12 w-3 h-3 rounded-full bg-[#C8A415]/60" />
        <div className="absolute top-12 right-12 w-3 h-3 rounded-full bg-white/40" />
        <div className="absolute bottom-12 left-12 w-3 h-3 rounded-full bg-white/40" />
        <div className="absolute bottom-12 right-12 w-3 h-3 rounded-full bg-[#C8A415]/60" />
      </div>
    </div>
  );
}

export default function LandingPage() {
  const navigate = useNavigate();
  const { language, setLanguage, isRTL } = useLanguage();
  const c = content[language] || content.en;

  const featureIcons = [Building2, TrendingUp, Headphones, ShieldCheck, Users, BarChart3];
  const featureTitles = [c.feature_1_title, c.feature_2_title, c.feature_3_title, c.feature_4_title, c.feature_5_title, c.feature_6_title];
  const featureDescs = [c.feature_1_desc, c.feature_2_desc, c.feature_3_desc, c.feature_4_desc, c.feature_5_desc, c.feature_6_desc];

  const steps = [
    { num: '01', title: c.step_1, desc: c.step_1_desc },
    { num: '02', title: c.step_2, desc: c.step_2_desc },
    { num: '03', title: c.step_3, desc: c.step_3_desc },
    { num: '04', title: c.step_4, desc: c.step_4_desc },
  ];

  const plans = [
    { name: c.starter, price: '109', features: c.starter_features, highlight: false },
    { name: c.business, price: '299', features: c.business_features, highlight: true },
    { name: c.enterprise, price: '749', features: c.enterprise_features, highlight: false },
  ];

  return (
    <div className={`min-h-screen bg-white text-slate-900 ${isRTL ? 'font-arabic' : ''}`} dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Navigation */}
      <nav className="fixed top-0 w-full z-50 bg-white/95 backdrop-blur-md border-b border-slate-100 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-[#006C35] to-[#004d27] rounded-xl flex items-center justify-center">
              <span className="text-white font-bold text-sm">POS</span>
            </div>
            <span className="text-xl font-bold text-[#006C35]">{c.nav_brand}</span>
          </div>
          <div className="flex items-center gap-4">
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
              className="bg-[#006C35] hover:bg-[#005a2c] text-white font-semibold px-6"
            >
              {content[language]?.hero_cta || 'Get Started'}
            </Button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-20 min-h-[90vh] flex items-center overflow-hidden">
        {/* Gradient Background */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#004d27] via-[#006C35] to-[#008540]" />
        {/* Decorative geometric overlay */}
        <div className="absolute inset-0 text-white/[0.04]">
          <GeometricPattern />
        </div>
        {/* Decorative circles */}
        <div className="absolute top-20 right-10 w-72 h-72 rounded-full bg-[#C8A415]/10 blur-3xl" />
        <div className="absolute bottom-10 left-10 w-96 h-96 rounded-full bg-[#006C35]/30 blur-3xl" />
        <div className="absolute top-40 left-1/3 w-48 h-48 rounded-full bg-white/5 blur-2xl" />
        {/* Gold accent bar */}
        <div className="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-[#C8A415] via-[#E8C840] to-[#C8A415]" />

        <div className="relative max-w-7xl mx-auto px-6 py-20 w-full grid lg:grid-cols-2 gap-12 items-center">
          <div className="max-w-2xl space-y-8">
            <Badge className="bg-[#C8A415]/20 text-[#C8A415] border-[#C8A415]/40 px-4 py-2 text-sm font-medium backdrop-blur-sm">
              <Star className="w-4 h-4 mr-1 inline" />
              {c.hero_badge}
            </Badge>
            <div className="space-y-4">
              <h1 className="text-4xl md:text-6xl font-bold text-white leading-tight">
                {c.hero_title_1}
              </h1>
              <h2 className="text-3xl md:text-5xl font-bold text-[#C8A415] leading-tight">
                {c.hero_title_2}
              </h2>
            </div>
            <p className="text-lg md:text-xl text-white/90 leading-relaxed max-w-xl">
              {c.hero_subtitle}
            </p>
            <div className="flex flex-wrap gap-4 pt-4">
              <Button
                onClick={() => navigate('/login')}
                className="bg-[#C8A415] hover:bg-[#b8940f] text-white px-8 py-6 text-lg font-bold shadow-xl shadow-[#C8A415]/30 transition-all hover:scale-105"
              >
                {c.hero_cta}
                <ArrowRight className={`w-5 h-5 ${isRTL ? 'mr-2 rotate-180' : 'ml-2'}`} />
              </Button>
              <Button
                variant="outline"
                className="border-white/40 text-white hover:bg-white/10 px-8 py-6 text-lg backdrop-blur-sm !bg-transparent"
                onClick={() => document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' })}
              >
                {c.hero_cta2}
              </Button>
            </div>
          </div>
          <HeroIllustration isRTL={isRTL} />
        </div>
      </section>

      {/* Partnership Section */}
      <section className="py-24 px-6 bg-slate-50">
        <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
          <div className={`space-y-6 ${isRTL ? 'lg:order-2' : ''}`}>
            <Badge className="bg-[#006C35]/10 text-[#006C35] border-[#006C35]/20 px-3 py-1">
              {c.partnership_badge}
            </Badge>
            <h2 className="text-3xl md:text-4xl font-bold text-slate-900 leading-tight">
              {c.partnership_title}
            </h2>
            <p className="text-lg text-slate-600 leading-relaxed">
              {c.partnership_desc}
            </p>
            <div className="grid grid-cols-2 gap-4 pt-4">
              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="text-3xl font-bold text-[#006C35]">500+</div>
                <div className="text-sm text-slate-500">{language === 'ar' || language === 'ur' ? 'موزع نشط' : 'Active Distributors'}</div>
              </div>
              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="text-3xl font-bold text-[#C8A415]">12K+</div>
                <div className="text-sm text-slate-500">{language === 'ar' || language === 'ur' ? 'تاجر' : 'Merchants'}</div>
              </div>
              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="text-3xl font-bold text-[#006C35]">99.9%</div>
                <div className="text-sm text-slate-500">{language === 'ar' || language === 'ur' ? 'وقت التشغيل' : 'Uptime'}</div>
              </div>
              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="text-3xl font-bold text-[#C8A415]">SAR 2M+</div>
                <div className="text-sm text-slate-500">{language === 'ar' || language === 'ur' ? 'إيرادات الموزعين' : 'Distributor Revenue'}</div>
              </div>
            </div>
          </div>
          <div className={`relative ${isRTL ? 'lg:order-1' : ''}`}>
            {/* Abstract partnership illustration using icons and gradients */}
            <div className="relative bg-gradient-to-br from-[#006C35]/5 to-[#C8A415]/5 rounded-3xl p-8 border border-slate-200">
              <div className="grid grid-cols-3 gap-4">
                {[
                  { icon: Building2, label: language === 'ar' || language === 'ur' ? 'علامتك' : 'Your Brand', color: '#006C35' },
                  { icon: Layers, label: language === 'ar' || language === 'ur' ? 'منصتنا' : 'Our Platform', color: '#C8A415' },
                  { icon: Users, label: language === 'ar' || language === 'ur' ? 'عملاؤك' : 'Your Clients', color: '#006C35' },
                  { icon: Monitor, label: language === 'ar' || language === 'ur' ? 'لوحة تحكم' : 'Dashboard', color: '#C8A415' },
                  { icon: ShieldCheck, label: 'ZATCA', color: '#006C35' },
                  { icon: TrendingUp, label: language === 'ar' || language === 'ur' ? 'نمو' : 'Growth', color: '#C8A415' },
                ].map((item, idx) => {
                  const Icon = item.icon;
                  return (
                    <div key={idx} className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100 flex flex-col items-center gap-3 hover:shadow-md transition-shadow">
                      <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${item.color}15` }}>
                        <Icon className="w-6 h-6" style={{ color: item.color }} />
                      </div>
                      <span className="text-xs font-medium text-slate-600 text-center">{item.label}</span>
                    </div>
                  );
                })}
              </div>
              {/* Connecting lines decoration */}
              <div className="absolute inset-0 pointer-events-none">
                <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <linearGradient id="line-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#006C35" stopOpacity="0.1" />
                      <stop offset="100%" stopColor="#C8A415" stopOpacity="0.1" />
                    </linearGradient>
                  </defs>
                  <line x1="33%" y1="25%" x2="66%" y2="25%" stroke="url(#line-grad)" strokeWidth="2" strokeDasharray="4 4" />
                  <line x1="33%" y1="75%" x2="66%" y2="75%" stroke="url(#line-grad)" strokeWidth="2" strokeDasharray="4 4" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24 px-6 relative overflow-hidden">
        {/* Geometric pattern background */}
        <div className="absolute inset-0 text-[#006C35]/[0.03]">
          <GeometricPattern />
        </div>
        <div className="relative max-w-7xl mx-auto">
          <div className="text-center mb-16 space-y-4">
            <h2 className="text-3xl md:text-4xl font-bold text-slate-900">{c.features_title}</h2>
            <p className="text-lg text-slate-600 max-w-2xl mx-auto">{c.features_subtitle}</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {featureTitles.map((title, idx) => {
              const Icon = featureIcons[idx];
              return (
                <Card key={idx} className="bg-white border-slate-200 shadow-sm hover:shadow-lg hover:border-[#006C35]/30 transition-all duration-300 group">
                  <CardContent className="p-8 space-y-4">
                    <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#006C35]/10 to-[#006C35]/5 flex items-center justify-center group-hover:from-[#006C35] group-hover:to-[#004d27] transition-all duration-300">
                      <Icon className="w-7 h-7 text-[#006C35] group-hover:text-white transition-colors duration-300" />
                    </div>
                    <h3 className="text-xl font-bold text-slate-900">{title}</h3>
                    <p className="text-slate-600 leading-relaxed">{featureDescs[idx]}</p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-24 px-6 bg-gradient-to-b from-[#006C35] to-[#004d27] text-white relative overflow-hidden">
        {/* Decorative elements */}
        <div className="absolute top-0 right-0 w-64 h-64 rounded-full bg-[#C8A415]/10 blur-3xl" />
        <div className="absolute bottom-0 left-0 w-80 h-80 rounded-full bg-white/5 blur-3xl" />
        <div className="relative max-w-7xl mx-auto">
          <div className="text-center mb-16 space-y-4">
            <h2 className="text-3xl md:text-4xl font-bold">{c.how_title}</h2>
            <p className="text-lg text-white/80">{c.how_subtitle}</p>
          </div>
          <div className="grid md:grid-cols-4 gap-8">
            {steps.map((step, idx) => (
              <div key={idx} className="text-center space-y-4 relative">
                {idx < 3 && (
                  <div className={`hidden md:block absolute top-8 ${isRTL ? 'right-full' : 'left-full'} w-full h-0.5 bg-[#C8A415]/40`} />
                )}
                <div className="w-16 h-16 mx-auto rounded-full bg-[#C8A415] flex items-center justify-center text-2xl font-bold text-white shadow-lg shadow-[#C8A415]/30">
                  {step.num}
                </div>
                <h3 className="text-xl font-bold">{step.title}</h3>
                <p className="text-white/80 text-sm">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonial Section */}
      <section className="py-24 px-6 bg-slate-50">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-16">{c.testimonial_title}</h2>
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className={`${isRTL ? 'lg:order-2' : ''}`}>
              {/* Abstract testimonial illustration */}
              <div className="relative bg-gradient-to-br from-[#006C35]/5 to-[#C8A415]/10 rounded-3xl p-12 border border-slate-200">
                <div className="absolute top-6 left-6 w-16 h-16 rounded-full bg-[#C8A415]/20 flex items-center justify-center">
                  <Star className="w-8 h-8 text-[#C8A415]" />
                </div>
                <div className="absolute bottom-6 right-6 w-12 h-12 rounded-full bg-[#006C35]/10 flex items-center justify-center">
                  <TrendingUp className="w-6 h-6 text-[#006C35]" />
                </div>
                <div className="flex flex-col items-center justify-center py-8 space-y-6">
                  <div className="w-24 h-24 rounded-full bg-gradient-to-br from-[#006C35] to-[#004d27] flex items-center justify-center shadow-xl">
                    <Users className="w-12 h-12 text-white" />
                  </div>
                  <div className="text-center space-y-2">
                    <div className="text-4xl font-bold text-[#006C35]">47</div>
                    <div className="text-sm text-slate-500">{language === 'ar' || language === 'ur' ? 'تاجر نشط' : 'Active Merchants'}</div>
                  </div>
                  <div className="flex gap-2">
                    {[...Array(5)].map((_, i) => (
                      <div key={i} className="w-8 h-8 rounded-lg bg-[#C8A415]/20 flex items-center justify-center">
                        <Star className="w-4 h-4 text-[#C8A415] fill-[#C8A415]" />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            <div className={`space-y-6 ${isRTL ? 'lg:order-1' : ''}`}>
              <div className="flex gap-1">
                {[...Array(5)].map((_, i) => (
                  <Star key={i} className="w-6 h-6 fill-[#C8A415] text-[#C8A415]" />
                ))}
              </div>
              <blockquote className="text-xl md:text-2xl text-slate-700 leading-relaxed italic">
                {c.testimonial_quote}
              </blockquote>
              <div>
                <div className="font-bold text-lg text-slate-900">{c.testimonial_name}</div>
                <div className="text-[#006C35] font-medium">{c.testimonial_role}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="py-24 px-6 relative overflow-hidden">
        {/* Subtle geometric pattern */}
        <div className="absolute inset-0 text-[#006C35]/[0.02]">
          <GeometricPattern />
        </div>
        <div className="relative max-w-7xl mx-auto">
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
                    ? 'border-[#006C35] border-2 shadow-xl shadow-[#006C35]/10 bg-white'
                    : 'border-slate-200 bg-white shadow-sm'
                }`}
              >
                {plan.highlight && (
                  <>
                    <div className="absolute top-0 inset-x-0 h-1.5 bg-gradient-to-r from-[#006C35] via-[#C8A415] to-[#006C35]" />
                    <div className="absolute -top-0 -right-0">
                      <Badge className="bg-[#C8A415] text-white border-0 rounded-none rounded-bl-lg px-3 py-1 text-xs font-bold">
                        {c.popular}
                      </Badge>
                    </div>
                  </>
                )}
                <CardContent className="p-8 space-y-6">
                  <div>
                    <h3 className="text-xl font-bold text-slate-900">{plan.name}</h3>
                    <div className="mt-4 flex items-baseline gap-1">
                      <span className="text-sm text-slate-500">SAR</span>
                      <span className="text-4xl font-bold text-[#006C35]">{plan.price}</span>
                      <span className="text-slate-500">{c.per_month}</span>
                    </div>
                  </div>
                  <ul className="space-y-3">
                    {plan.features.map((feature, fIdx) => (
                      <li key={fIdx} className="flex items-center gap-3 text-slate-700 text-sm">
                        <CheckCircle2 className="w-5 h-5 text-[#006C35] flex-shrink-0" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                  <Button
                    className={`w-full py-6 font-bold text-base ${
                      plan.highlight
                        ? 'bg-[#006C35] hover:bg-[#005a2c] text-white shadow-lg'
                        : 'bg-slate-100 hover:bg-slate-200 text-slate-900'
                    }`}
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

      {/* Final CTA */}
      <section className="py-20 px-6 bg-gradient-to-r from-[#006C35] to-[#004d27] relative overflow-hidden">
        {/* Decorative elements instead of image */}
        <div className="absolute inset-0 text-white/[0.04]">
          <GeometricPattern />
        </div>
        <div className="absolute top-0 right-0 w-96 h-96 rounded-full bg-[#C8A415]/10 blur-3xl" />
        <div className="absolute bottom-0 left-0 w-64 h-64 rounded-full bg-white/5 blur-3xl" />
        <div className="relative max-w-4xl mx-auto text-center space-y-8">
          <h2 className="text-3xl md:text-4xl font-bold text-white">{c.hero_title_1}</h2>
          <p className="text-xl text-white/80">{c.hero_subtitle}</p>
          <Button
            onClick={() => navigate('/login')}
            className="bg-[#C8A415] hover:bg-[#b8940f] text-white px-10 py-6 text-lg font-bold shadow-xl shadow-[#C8A415]/30 transition-all hover:scale-105"
          >
            {c.hero_cta}
            <ArrowRight className={`w-5 h-5 ${isRTL ? 'mr-2 rotate-180' : 'ml-2'}`} />
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-slate-900 text-white py-16 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-3 gap-12 mb-12">
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gradient-to-br from-[#006C35] to-[#004d27] rounded-xl flex items-center justify-center">
                  <span className="text-white font-bold text-sm">POS</span>
                </div>
                <span className="text-xl font-bold">{c.footer_brand}</span>
              </div>
              <p className="text-slate-400 text-sm leading-relaxed">{c.footer_desc}</p>
            </div>
            <div className="space-y-3">
              <h4 className="font-bold text-white">{language === 'ar' || language === 'ur' ? 'معلومات قانونية' : 'Legal Information'}</h4>
              <p className="text-slate-400 text-sm">{c.footer_cr}</p>
              <p className="text-slate-400 text-sm">{c.footer_vat}</p>
            </div>
            <div className="space-y-3">
              <h4 className="font-bold text-white">{language === 'ar' || language === 'ur' ? 'روابط' : 'Links'}</h4>
              <div className="flex flex-col gap-2 text-sm text-slate-400">
                <span className="hover:text-white cursor-pointer transition-colors">{c.footer_privacy}</span>
                <span className="hover:text-white cursor-pointer transition-colors">{c.footer_terms}</span>
                <span className="hover:text-white cursor-pointer transition-colors">{c.footer_contact}</span>
              </div>
            </div>
          </div>
          <div className="border-t border-slate-800 pt-8 text-center text-sm text-slate-500">
            {c.footer_rights}
          </div>
        </div>
      </footer>
    </div>
  );
}