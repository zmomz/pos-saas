import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import NotFoundState from '@/components/states/NotFoundState';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getAgentPublicProfile } from '@/lib/api';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import {
  Store, ShieldCheck, ArrowRight, Eye, CheckCircle2, Coffee, Croissant, Drumstick,
  Sparkles, Shirt, QrCode, Zap, Box, Globe, TrendingUp, Repeat, MapPin, Headphones,
  Lock, CreditCard, Star, Check, X, Phone, Mail, Package,
} from 'lucide-react';

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

type Plan = { name: string; desc: string; price: string; features: { label: string; off?: boolean }[]; cta: string; feat?: boolean };
type Story = { quote: string; name: string; org: string; initials: string };

const content = {
  en: {
    loading: 'Loading...',
    not_found_title: 'Distributor Not Found',
    not_found_desc: "This distributor page doesn't exist or has been deactivated.",
    go_main: 'Go to Main Site',
    authorized_provider: 'AUTHORIZED PROVIDER',
    features: 'Features', pricing: 'Pricing', support: 'Support', login: 'Login',
    nav_cta: 'Start Free Trial',
    hero_badge: 'Authorized POS Provider',
    hero_title_a: 'An easy-to-use', hero_title_b: 'POS for your shop.',
    hero_subtitle: 'Fast checkout, ZATCA QR invoices and multi-language support — all in the cloud. Ring up sales in seconds on any tablet, with your inventory synced across every branch.',
    hero_cta: 'Start Free Trial', hero_demo: 'See Demo',
    trust_1: '14-day free trial', trust_2: 'No card required', trust_3: 'Setup in minutes',
    cat_all: 'All', cat_drinks: 'Drinks', cat_food: 'Food', cat_retail: 'Retail',
    current_sale: 'Current Sale', vat_label: 'VAT (15%)', total_label: 'Total', pay: 'Pay',
    zatca: 'ZATCA', qr_invoice: 'QR invoice',
    feat_eyebrow: 'Everything you need', feat_title: 'Built for shops & restaurants.',
    feat_sub: 'One simple app that handles checkout, inventory, invoicing and reporting.',
    featureItems: [
      { t: 'Fast checkout', d: 'Ring up a sale in seconds with big touch targets and barcode scanning.' },
      { t: 'ZATCA e-invoicing', d: 'Every receipt carries a compliant QR code — Phase 2 ready, automatically.' },
      { t: 'Inventory management', d: 'Track stock in real time, get low-stock alerts and manage suppliers.' },
      { t: 'Multi-language', d: 'English, Arabic, Hindi & Urdu with full right-to-left support.' },
      { t: 'Real-time reports', d: 'See sales, top products and shift totals from anywhere, live.' },
      { t: 'Cloud sync', d: 'All your branches in sync — pricing, stock and reports, everywhere.' },
    ],
    chips: ['ZATCA Certified', 'Saudi-made software', '24/7 Arabic support', 'GDPR & local compliance', 'mada · Visa · Apple Pay'],
    stats: [
      { v: '98%', k: 'Customer satisfaction' },
      { v: '5,000+', k: 'Merchants served' },
      { v: '2.3s', k: 'Average checkout' },
      { v: '4.9', star: true, k: 'App store rating' },
    ],
    storyItems: [
      { quote: '"My cashiers learned it in one shift. Checkout is genuinely faster than our old register."', name: 'Abu Faisal', org: 'Al-Baik Express · Restaurant', initials: 'AB' },
      { quote: '"The ZATCA QR is automatic — I stopped worrying about invoices completely. Huge relief."', name: 'Maha Al-Mutairi', org: 'Manqal Market · Grocery', initials: 'MM' },
      { quote: '"Two branches, one dashboard. I check today\'s sales from my phone over morning qahwa."', name: 'Qais B.', org: 'Qahwa & Beans · Café', initials: 'QB' },
    ] as Story[],
    price_eyebrow: 'Simple pricing', price_title: 'Plans that grow with you.',
    price_sub: 'Start with a 14-day free trial. Switch or cancel anytime.',
    most_popular: 'Most popular', per_mo: '/mo', cur: 'SAR', trial_cta: 'Start 14-day trial',
    plans: [
      { name: 'Basic', desc: 'For a single shop getting started.', price: '150',
        features: [{ label: '1 branch' }, { label: 'Inventory management' }, { label: 'ZATCA e-invoicing' }, { label: 'Daily sales reports' }, { label: 'Loyalty & gift cards', off: true }] },
      { name: 'Pro', desc: 'For growing shops & small chains.', price: '280', feat: true,
        features: [{ label: 'Up to 3 branches' }, { label: 'Everything in Basic' }, { label: 'Loyalty program' }, { label: 'Gift cards & discounts' }, { label: 'Cloud sync across branches' }] },
      { name: 'Premium', desc: 'For established multi-branch businesses.', price: '450',
        features: [{ label: 'Unlimited branches' }, { label: 'Everything in Pro' }, { label: 'API & integrations' }, { label: 'Advanced reports' }, { label: 'Priority 24/7 support' }] },
    ] as Omit<Plan, 'cta'>[],
    cta_title: 'Ready to modernize your checkout?',
    cta_sub: "Start your free trial today, or talk to our team — we'll have you set up the same day.",
    cta_whatsapp: 'WhatsApp us',
    foot_desc: 'Modern, ZATCA-compliant point of sale for Saudi shops and restaurants. Authorized Cloud POS provider.',
    foot_product: 'Product', foot_support: 'Support', foot_company: 'Company',
    foot_product_links: ['Features', 'Pricing', 'Live demo'],
    foot_made: 'Made in Saudi Arabia 🇸🇦',
    foot_powered: 'Powered by Cloud POS · ZATCA certified',
  },
  ar: {
    loading: 'جاري التحميل...',
    not_found_title: 'الموزع غير موجود',
    not_found_desc: 'هذه الصفحة غير موجودة أو تم إلغاء تفعيلها.',
    go_main: 'الذهاب للموقع الرئيسي',
    authorized_provider: 'مزود معتمد',
    features: 'المميزات', pricing: 'الأسعار', support: 'الدعم', login: 'تسجيل الدخول',
    nav_cta: 'ابدأ تجربة مجانية',
    hero_badge: 'مزود نقاط بيع معتمد',
    hero_title_a: 'نظام نقاط بيع', hero_title_b: 'سهل لمتجرك.',
    hero_subtitle: 'دفع سريع وفواتير زاتكا بصيغة QR ودعم متعدد اللغات — كل ذلك في السحابة. سجّل المبيعات في ثوانٍ على أي جهاز لوحي، مع مزامنة مخزونك عبر كل فرع.',
    hero_cta: 'ابدأ تجربة مجانية', hero_demo: 'شاهد العرض',
    trust_1: 'تجربة 14 يوماً مجاناً', trust_2: 'بدون بطاقة', trust_3: 'إعداد خلال دقائق',
    cat_all: 'الكل', cat_drinks: 'مشروبات', cat_food: 'طعام', cat_retail: 'تجزئة',
    current_sale: 'البيع الحالي', vat_label: 'ضريبة (15%)', total_label: 'الإجمالي', pay: 'ادفع',
    zatca: 'زاتكا', qr_invoice: 'فاتورة QR',
    feat_eyebrow: 'كل ما تحتاجه', feat_title: 'مصمم للمتاجر والمطاعم.',
    feat_sub: 'تطبيق واحد بسيط يتولى الدفع والمخزون والفوترة والتقارير.',
    featureItems: [
      { t: 'دفع سريع', d: 'سجّل عملية بيع في ثوانٍ بأزرار لمس كبيرة ومسح الباركود.' },
      { t: 'فوترة زاتكا الإلكترونية', d: 'كل إيصال يحمل رمز QR متوافقاً — جاهز للمرحلة الثانية تلقائياً.' },
      { t: 'إدارة المخزون', d: 'تتبّع المخزون لحظياً، واحصل على تنبيهات النقص وأدر الموردين.' },
      { t: 'متعدد اللغات', d: 'العربية والإنجليزية والهندية والأردية مع دعم كامل لليمين-لليسار.' },
      { t: 'تقارير فورية', d: 'شاهد المبيعات وأفضل المنتجات وإجماليات الورديات من أي مكان، مباشرة.' },
      { t: 'مزامنة سحابية', d: 'كل فروعك متزامنة — الأسعار والمخزون والتقارير، في كل مكان.' },
    ],
    chips: ['معتمد من زاتكا', 'برمجيات سعودية', 'دعم عربي 24/7', 'امتثال GDPR والمحلي', 'مدى · فيزا · Apple Pay'],
    stats: [
      { v: '98%', k: 'رضا العملاء' },
      { v: '+5,000', k: 'تاجر تم خدمته' },
      { v: '2.3 ث', k: 'متوسط الدفع' },
      { v: '4.9', star: true, k: 'تقييم المتجر' },
    ],
    storyItems: [
      { quote: '"تعلّمها أمناء الصندوق في وردية واحدة. الدفع أسرع فعلاً من جهازنا القديم."', name: 'أبو فيصل', org: 'البيك إكسبرس · مطعم', initials: 'AB' },
      { quote: '"رمز زاتكا تلقائي — توقفت عن القلق بشأن الفواتير تماماً. راحة كبيرة."', name: 'مها المطيري', org: 'سوق منقل · بقالة', initials: 'MM' },
      { quote: '"فرعان، لوحة واحدة. أتابع مبيعات اليوم من جوالي على قهوة الصباح."', name: 'قيس ب.', org: 'قهوة وحبوب · مقهى', initials: 'QB' },
    ] as Story[],
    price_eyebrow: 'أسعار بسيطة', price_title: 'باقات تنمو معك.',
    price_sub: 'ابدأ بتجربة مجانية 14 يوماً. غيّر أو ألغِ في أي وقت.',
    most_popular: 'الأكثر شعبية', per_mo: '/شهرياً', cur: 'ر.س', trial_cta: 'ابدأ تجربة 14 يوماً',
    plans: [
      { name: 'أساسي', desc: 'لمتجر واحد يبدأ للتو.', price: '150',
        features: [{ label: 'فرع واحد' }, { label: 'إدارة المخزون' }, { label: 'فوترة زاتكا الإلكترونية' }, { label: 'تقارير مبيعات يومية' }, { label: 'الولاء وبطاقات الهدايا', off: true }] },
      { name: 'احترافي', desc: 'للمتاجر النامية والسلاسل الصغيرة.', price: '280', feat: true,
        features: [{ label: 'حتى 3 فروع' }, { label: 'كل ما في الأساسي' }, { label: 'برنامج الولاء' }, { label: 'بطاقات الهدايا والخصومات' }, { label: 'مزامنة سحابية بين الفروع' }] },
      { name: 'مميز', desc: 'للأعمال متعددة الفروع الراسخة.', price: '450',
        features: [{ label: 'فروع غير محدودة' }, { label: 'كل ما في الاحترافي' }, { label: 'API وتكاملات' }, { label: 'تقارير متقدمة' }, { label: 'دعم أولوية 24/7' }] },
    ] as Omit<Plan, 'cta'>[],
    cta_title: 'مستعد لتحديث نقطة البيع لديك؟',
    cta_sub: 'ابدأ تجربتك المجانية اليوم، أو تحدث مع فريقنا — سنجهزك في اليوم نفسه.',
    cta_whatsapp: 'راسلنا واتساب',
    foot_desc: 'نقطة بيع حديثة ومتوافقة مع زاتكا للمتاجر والمطاعم السعودية. مزود معتمد لـ Cloud POS.',
    foot_product: 'المنتج', foot_support: 'الدعم', foot_company: 'الشركة',
    foot_product_links: ['المميزات', 'الأسعار', 'عرض مباشر'],
    foot_made: 'صُنع في السعودية 🇸🇦',
    foot_powered: 'مدعوم من Cloud POS · معتمد من زاتكا',
  },
  hi: {
    loading: 'लोड हो रहा है...',
    not_found_title: 'डिस्ट्रीब्यूटर नहीं मिला',
    not_found_desc: 'यह पेज मौजूद नहीं है या निष्क्रिय कर दिया गया है।',
    go_main: 'मुख्य साइट पर जाएं',
    authorized_provider: 'अधिकृत प्रदाता',
    features: 'सुविधाएं', pricing: 'मूल्य', support: 'सहायता', login: 'लॉगिन',
    nav_cta: 'मुफ्त ट्रायल शुरू करें',
    hero_badge: 'अधिकृत POS प्रदाता',
    hero_title_a: 'आपकी दुकान के लिए', hero_title_b: 'आसान POS।',
    hero_subtitle: 'तेज़ चेकआउट, ZATCA QR इनवॉइस और बहु-भाषा समर्थन — सब क्लाउड में। किसी भी टैबलेट पर सेकंडों में बिक्री करें, हर शाखा में इन्वेंटरी सिंक के साथ।',
    hero_cta: 'मुफ्त ट्रायल शुरू करें', hero_demo: 'डेमो देखें',
    trust_1: '14-दिन मुफ्त ट्रायल', trust_2: 'कार्ड की जरूरत नहीं', trust_3: 'मिनटों में सेटअप',
    cat_all: 'सभी', cat_drinks: 'पेय', cat_food: 'खाना', cat_retail: 'रिटेल',
    current_sale: 'वर्तमान बिक्री', vat_label: 'VAT (15%)', total_label: 'कुल', pay: 'भुगतान',
    zatca: 'ZATCA', qr_invoice: 'QR इनवॉइस',
    feat_eyebrow: 'आपको जो चाहिए', feat_title: 'दुकानों और रेस्तरां के लिए बना।',
    feat_sub: 'एक सरल ऐप जो चेकआउट, इन्वेंटरी, इनवॉइसिंग और रिपोर्टिंग संभालता है।',
    featureItems: [
      { t: 'तेज़ चेकआउट', d: 'बड़े टच टारगेट और बारकोड स्कैनिंग के साथ सेकंडों में बिक्री करें।' },
      { t: 'ZATCA ई-इनवॉइसिंग', d: 'हर रसीद पर अनुपालन QR कोड — Phase 2 तैयार, स्वचालित रूप से।' },
      { t: 'इन्वेंटरी प्रबंधन', d: 'रीयल-टाइम में स्टॉक ट्रैक करें, कम-स्टॉक अलर्ट पाएं और सप्लायर संभालें।' },
      { t: 'बहु-भाषा', d: 'अंग्रेजी, अरबी, हिंदी और उर्दू पूर्ण right-to-left समर्थन के साथ।' },
      { t: 'रीयल-टाइम रिपोर्ट', d: 'बिक्री, टॉप उत्पाद और शिफ्ट कुल कहीं से भी, लाइव देखें।' },
      { t: 'क्लाउड सिंक', d: 'आपकी सभी शाखाएं सिंक में — मूल्य, स्टॉक और रिपोर्ट, हर जगह।' },
    ],
    chips: ['ZATCA प्रमाणित', 'सऊदी-निर्मित सॉफ्टवेयर', '24/7 अरबी सहायता', 'GDPR व स्थानीय अनुपालन', 'mada · Visa · Apple Pay'],
    stats: [
      { v: '98%', k: 'ग्राहक संतुष्टि' },
      { v: '5,000+', k: 'व्यापारियों की सेवा' },
      { v: '2.3s', k: 'औसत चेकआउट' },
      { v: '4.9', star: true, k: 'ऐप स्टोर रेटिंग' },
    ],
    storyItems: [
      { quote: '"मेरे कैशियर ने इसे एक शिफ्ट में सीख लिया। चेकआउट हमारे पुराने रजिस्टर से सच में तेज़ है।"', name: 'अबू फैसल', org: 'अल-बैक एक्सप्रेस · रेस्तरां', initials: 'AB' },
      { quote: '"ZATCA QR स्वचालित है — मैंने इनवॉइस की चिंता पूरी तरह छोड़ दी। बड़ी राहत।"', name: 'महा अल-मुतैरी', org: 'मनक़ल मार्केट · किराना', initials: 'MM' },
      { quote: '"दो शाखाएं, एक डैशबोर्ड। सुबह की क़हवा पर फोन से आज की बिक्री देखता हूं।"', name: 'क़ैस बी.', org: 'क़हवा एंड बीन्स · कैफे', initials: 'QB' },
    ] as Story[],
    price_eyebrow: 'सरल मूल्य', price_title: 'योजनाएं जो आपके साथ बढ़ें।',
    price_sub: '14-दिन मुफ्त ट्रायल से शुरू करें। कभी भी बदलें या रद्द करें।',
    most_popular: 'सबसे लोकप्रिय', per_mo: '/माह', cur: 'SAR', trial_cta: '14-दिन ट्रायल शुरू करें',
    plans: [
      { name: 'बेसिक', desc: 'शुरुआत करती एकल दुकान के लिए।', price: '150',
        features: [{ label: '1 शाखा' }, { label: 'इन्वेंटरी प्रबंधन' }, { label: 'ZATCA ई-इनवॉइसिंग' }, { label: 'दैनिक बिक्री रिपोर्ट' }, { label: 'लॉयल्टी व गिफ्ट कार्ड', off: true }] },
      { name: 'प्रो', desc: 'बढ़ती दुकानों व छोटी चेन के लिए।', price: '280', feat: true,
        features: [{ label: '3 शाखाओं तक' }, { label: 'बेसिक की सभी सुविधाएं' }, { label: 'लॉयल्टी प्रोग्राम' }, { label: 'गिफ्ट कार्ड व छूट' }, { label: 'शाखाओं में क्लाउड सिंक' }] },
      { name: 'प्रीमियम', desc: 'स्थापित बहु-शाखा व्यवसायों के लिए।', price: '450',
        features: [{ label: 'असीमित शाखाएं' }, { label: 'प्रो की सभी सुविधाएं' }, { label: 'API व इंटीग्रेशन' }, { label: 'उन्नत रिपोर्ट' }, { label: 'प्राथमिकता 24/7 सहायता' }] },
    ] as Omit<Plan, 'cta'>[],
    cta_title: 'अपना चेकआउट आधुनिक बनाने के लिए तैयार?',
    cta_sub: 'आज ही मुफ्त ट्रायल शुरू करें, या हमारी टीम से बात करें — हम उसी दिन सेटअप कर देंगे।',
    cta_whatsapp: 'WhatsApp करें',
    foot_desc: 'सऊदी दुकानों और रेस्तरां के लिए आधुनिक, ZATCA-अनुपालन पॉइंट ऑफ सेल। अधिकृत Cloud POS प्रदाता।',
    foot_product: 'उत्पाद', foot_support: 'सहायता', foot_company: 'कंपनी',
    foot_product_links: ['सुविधाएं', 'मूल्य', 'लाइव डेमो'],
    foot_made: 'सऊदी अरब में निर्मित 🇸🇦',
    foot_powered: 'Cloud POS द्वारा संचालित · ZATCA प्रमाणित',
  },
  ur: {
    loading: 'لوڈ ہو رہا ہے...',
    not_found_title: 'ڈسٹریبیوٹر نہیں ملا',
    not_found_desc: 'یہ صفحہ موجود نہیں ہے یا غیر فعال کر دیا گیا ہے۔',
    go_main: 'مرکزی سائٹ پر جائیں',
    authorized_provider: 'مجاز فراہم کنندہ',
    features: 'خصوصیات', pricing: 'قیمتیں', support: 'سپورٹ', login: 'لاگ ان',
    nav_cta: 'مفت ٹرائل شروع کریں',
    hero_badge: 'مجاز POS فراہم کنندہ',
    hero_title_a: 'آپ کی دکان کے لیے', hero_title_b: 'آسان POS۔',
    hero_subtitle: 'تیز چیک آؤٹ، ZATCA QR انوائسز اور کثیر لسانی سپورٹ — سب کلاؤڈ میں۔ کسی بھی ٹیبلٹ پر سیکنڈوں میں سیلز کریں، ہر برانچ میں انوینٹری سنک کے ساتھ۔',
    hero_cta: 'مفت ٹرائل شروع کریں', hero_demo: 'ڈیمو دیکھیں',
    trust_1: '14 دن مفت ٹرائل', trust_2: 'کارڈ کی ضرورت نہیں', trust_3: 'منٹوں میں سیٹ اپ',
    cat_all: 'تمام', cat_drinks: 'مشروبات', cat_food: 'کھانا', cat_retail: 'ریٹیل',
    current_sale: 'موجودہ سیل', vat_label: 'VAT (15%)', total_label: 'کل', pay: 'ادائیگی',
    zatca: 'ZATCA', qr_invoice: 'QR انوائس',
    feat_eyebrow: 'جو کچھ آپ کو چاہیے', feat_title: 'دکانوں اور ریسٹورنٹس کے لیے بنایا گیا۔',
    feat_sub: 'ایک سادہ ایپ جو چیک آؤٹ، انوینٹری، انوائسنگ اور رپورٹنگ سنبھالتی ہے۔',
    featureItems: [
      { t: 'تیز چیک آؤٹ', d: 'بڑے ٹچ ٹارگٹس اور بارکوڈ اسکیننگ کے ساتھ سیکنڈوں میں سیل کریں۔' },
      { t: 'ZATCA ای-انوائسنگ', d: 'ہر رسید پر تعمیل QR کوڈ — Phase 2 تیار، خودکار طور پر۔' },
      { t: 'انوینٹری مینجمنٹ', d: 'ریئل ٹائم میں اسٹاک ٹریک کریں، کم اسٹاک الرٹس پائیں اور سپلائرز سنبھالیں۔' },
      { t: 'کثیر لسانی', d: 'انگریزی، عربی، ہندی اور اردو مکمل right-to-left سپورٹ کے ساتھ۔' },
      { t: 'ریئل ٹائم رپورٹس', d: 'سیلز، ٹاپ مصنوعات اور شفٹ ٹوٹل کہیں سے بھی، لائیو دیکھیں۔' },
      { t: 'کلاؤڈ سنک', d: 'آپ کی تمام برانچز سنک میں — قیمتیں، اسٹاک اور رپورٹس، ہر جگہ۔' },
    ],
    chips: ['ZATCA تصدیق شدہ', 'سعودی ساختہ سافٹ ویئر', '24/7 عربی سپورٹ', 'GDPR و مقامی تعمیل', 'mada · Visa · Apple Pay'],
    stats: [
      { v: '98%', k: 'گاہک کی اطمینان' },
      { v: '5,000+', k: 'تاجروں کی خدمت' },
      { v: '2.3s', k: 'اوسط چیک آؤٹ' },
      { v: '4.9', star: true, k: 'ایپ اسٹور ریٹنگ' },
    ],
    storyItems: [
      { quote: '"میرے کیشئرز نے ایک شفٹ میں سیکھ لیا۔ چیک آؤٹ ہمارے پرانے رجسٹر سے واقعی تیز ہے۔"', name: 'ابو فیصل', org: 'البیک ایکسپریس · ریسٹورنٹ', initials: 'AB' },
      { quote: '"ZATCA QR خودکار ہے — میں نے انوائسز کی فکر مکمل چھوڑ دی۔ بڑی راحت۔"', name: 'مہا المطیری', org: 'منقل مارکیٹ · گروسری', initials: 'MM' },
      { quote: '"دو برانچز، ایک ڈیش بورڈ۔ صبح کی قہوہ پر فون سے آج کی سیل دیکھتا ہوں۔"', name: 'قیس ب۔', org: 'قہوہ اینڈ بینز · کیفے', initials: 'QB' },
    ] as Story[],
    price_eyebrow: 'سادہ قیمتیں', price_title: 'پلانز جو آپ کے ساتھ بڑھیں۔',
    price_sub: '14 دن مفت ٹرائل سے شروع کریں۔ کسی بھی وقت بدلیں یا منسوخ کریں۔',
    most_popular: 'سب سے مقبول', per_mo: '/ماہ', cur: 'ر.س', trial_cta: '14 دن ٹرائل شروع کریں',
    plans: [
      { name: 'بنیادی', desc: 'شروعات کرتی واحد دکان کے لیے۔', price: '150',
        features: [{ label: '1 برانچ' }, { label: 'انوینٹری مینجمنٹ' }, { label: 'ZATCA ای-انوائسنگ' }, { label: 'روزانہ سیلز رپورٹس' }, { label: 'لائلٹی و گفٹ کارڈز', off: true }] },
      { name: 'پرو', desc: 'بڑھتی دکانوں و چھوٹی چینز کے لیے۔', price: '280', feat: true,
        features: [{ label: '3 برانچز تک' }, { label: 'بنیادی کی تمام خصوصیات' }, { label: 'لائلٹی پروگرام' }, { label: 'گفٹ کارڈز و رعایتیں' }, { label: 'برانچز میں کلاؤڈ سنک' }] },
      { name: 'پریمیم', desc: 'قائم ملٹی برانچ کاروبار کے لیے۔', price: '450',
        features: [{ label: 'لامحدود برانچز' }, { label: 'پرو کی تمام خصوصیات' }, { label: 'API و انٹیگریشنز' }, { label: 'ایڈوانسڈ رپورٹس' }, { label: 'ترجیحی 24/7 سپورٹ' }] },
    ] as Omit<Plan, 'cta'>[],
    cta_title: 'اپنا چیک آؤٹ جدید بنانے کے لیے تیار؟',
    cta_sub: 'آج ہی اپنا مفت ٹرائل شروع کریں، یا ہماری ٹیم سے بات کریں — ہم اسی دن سیٹ اپ کر دیں گے۔',
    cta_whatsapp: 'WhatsApp کریں',
    foot_desc: 'سعودی دکانوں اور ریسٹورنٹس کے لیے جدید، ZATCA-تعمیل پوائنٹ آف سیل۔ مجاز Cloud POS فراہم کنندہ۔',
    foot_product: 'پروڈکٹ', foot_support: 'سپورٹ', foot_company: 'کمپنی',
    foot_product_links: ['خصوصیات', 'قیمتیں', 'لائیو ڈیمو'],
    foot_made: 'سعودی عرب میں تیار 🇸🇦',
    foot_powered: 'Cloud POS سے تقویت یافتہ · ZATCA تصدیق شدہ',
  },
};

/**
 * Public, white-labelled agent storefront.
 *
 * Phase 5 decision: like the partner landing page, this is intentionally light.
 * It uses fixed palettes (`slate-*` + the agent's own `primary_color`, applied
 * via inline styles) and never the inverting app tokens, so a logged-out shopper
 * always sees a clean light brochure regardless of any persisted app theme.
 */
export default function AgentLandingPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const [profile, setProfile] = useState<AgentProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const navigate = useNavigate();
  const { language, setLanguage, isRTL } = useLanguage();
  const c = content[language] || content.en;

  useEffect(() => {
    if (agentId) loadProfile(agentId);
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
          <div className="w-12 h-12 border-4 border-slate-200 border-t-brand-500 rounded-full animate-spin mx-auto" />
          <p className="text-slate-600">{c.loading}</p>
        </div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <NotFoundState
        code=""
        icon={Package}
        title={c.not_found_title}
        description={c.not_found_desc}
        action={<Button onClick={() => navigate('/')}>{c.go_main}</Button>}
      />
    );
  }

  const brand = profile.primary_color || '#006C35';
  // Derived brand shades (work for any hex via color-mix).
  const brand700 = `color-mix(in srgb, ${brand}, #000 22%)`;
  const brandDark = `color-mix(in srgb, ${brand} 60%, #0a0a0a)`;
  const tint = (a: string) => `${brand}${a}`; // hex + alpha for light tints

  const phone = profile.contact_phone || '920 00 1234';
  const email = profile.contact_email || 'hello@najdpos.sa';
  const subtitle = profile.tagline || c.hero_subtitle;

  const featureTones: { cls?: string; brandIcon?: boolean }[] = [
    { brandIcon: true },
    { cls: 'bg-sky/10 text-sky' },
    { cls: 'bg-gold-50 text-gold-600' },
    { cls: 'bg-violet/10 text-violet' },
    { cls: 'bg-success/10 text-success' },
    { brandIcon: true },
  ];
  const featureIcons = [Zap, QrCode, Box, Globe, TrendingUp, Repeat];

  const chipIcons = [ShieldCheck, MapPin, Headphones, Lock, CreditCard];

  const tiles: { Icon: typeof Coffee; cls?: string; brandIcon?: boolean }[] = [
    { Icon: Coffee, cls: 'bg-warning/10 text-warning' },
    { Icon: Coffee, cls: 'bg-sky/10 text-sky' },
    { Icon: Croissant, cls: 'bg-gold-50 text-gold-600' },
    { Icon: Drumstick, cls: 'bg-success/10 text-success' },
    { Icon: Sparkles, cls: 'bg-violet/10 text-violet' },
    { Icon: Shirt, brandIcon: true },
  ];
  const saleLines = [
    { tone: 'bg-warning/15', price: 'SAR 16' },
    { tone: 'bg-gold-50', price: 'SAR 13' },
    { tone: 'bg-success/15', price: 'SAR 24' },
  ];

  return (
    <div className={`min-h-screen bg-white text-slate-900 ${isRTL ? 'font-arabic' : ''}`} dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Nav */}
      <nav className="sticky top-0 z-40 bg-white/85 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {profile.logo_url ? (
              <img src={profile.logo_url} alt={profile.company_name} className="w-9 h-9 rounded-[9px] object-cover" />
            ) : (
              <span className="w-9 h-9 rounded-[9px] text-white grid place-items-center" style={{ backgroundColor: brand }}>
                <Store className="w-5 h-5" />
              </span>
            )}
            <span className="leading-none">
              <b className="text-[17px] font-bold tracking-tight block">{profile.company_name}</b>
              <small className="font-mono text-[9.5px] text-slate-400 tracking-wide">{c.authorized_provider}</small>
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })} className="hidden md:inline-flex text-sm font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-3.5 py-2 rounded-lg transition-colors">{c.features}</button>
            <button onClick={() => document.getElementById('pricing')?.scrollIntoView({ behavior: 'smooth' })} className="hidden md:inline-flex text-sm font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-3.5 py-2 rounded-lg transition-colors">{c.pricing}</button>
            <button onClick={() => document.getElementById('contact-section')?.scrollIntoView({ behavior: 'smooth' })} className="hidden lg:inline-flex text-sm font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-3.5 py-2 rounded-lg transition-colors">{c.support}</button>
            <button onClick={() => navigate('/login')} className="hidden md:inline-flex text-sm font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-3.5 py-2 rounded-lg transition-colors">{c.login}</button>
            <Select value={language} onValueChange={(v) => setLanguage(v as Language)}>
              <SelectTrigger className="w-24 bg-slate-50 border-slate-200 text-slate-700 text-sm h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-white border-slate-200">
                {languageOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value} className="text-slate-700">{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={() => navigate('/login')} className="text-white font-semibold h-9 px-4" style={{ backgroundColor: brand }}>{c.nav_cta}</Button>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <header className="relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(760px 460px at 80% 4%, ${tint('14')}, transparent 60%)` }} />
        <div className="relative max-w-[1180px] mx-auto px-6 lg:px-8 pt-16 pb-20 grid lg:grid-cols-[1.05fr_0.95fr] gap-14 items-center">
          <div className={isRTL ? 'lg:order-2' : ''}>
            <span className="inline-flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-full mb-6 border" style={{ backgroundColor: tint('12'), color: brand700, borderColor: tint('33') }}>
              <ShieldCheck className="w-3.5 h-3.5" /> {c.hero_badge}
            </span>
            <h1 className="text-[40px] md:text-[54px] font-bold leading-[1.03] tracking-tight text-slate-900">
              {c.hero_title_a}<br />{c.hero_title_b}
            </h1>
            <p className="text-lg md:text-[19px] text-slate-600 leading-relaxed mt-5 max-w-xl">{subtitle}</p>
            <div className="flex flex-wrap gap-3 mt-8">
              <Button onClick={() => document.getElementById('pricing')?.scrollIntoView({ behavior: 'smooth' })} className="text-white px-6 py-6 text-base font-semibold" style={{ backgroundColor: brand, boxShadow: `0 10px 30px ${tint('30')}` }}>
                {c.hero_cta}<ArrowRight className={`w-5 h-5 ${isRTL ? 'mr-2 rotate-180' : 'ml-2'}`} />
              </Button>
              <Button variant="outline" onClick={() => navigate('/login')} className="px-6 py-6 text-base font-semibold border-slate-300 !bg-white" style={{ color: brand700 }}>
                <Eye className={`w-5 h-5 ${isRTL ? 'ml-2' : 'mr-2'}`} />{c.hero_demo}
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-5 mt-8">
              {[c.trust_1, c.trust_2, c.trust_3].map((t) => (
                <div key={t} className="flex items-center gap-2 text-[13px] font-medium text-slate-500">
                  <CheckCircle2 className="w-[17px] h-[17px] text-success" />{t}
                </div>
              ))}
            </div>
          </div>

          {/* POS terminal mockup */}
          <div className={`relative ${isRTL ? 'lg:order-1' : ''}`}>
            <div className="grid grid-cols-[1.5fr_1fr] rounded-[18px] border border-slate-200 shadow-2xl overflow-hidden bg-white">
              {/* left: catalog */}
              <div className="p-4 bg-slate-50">
                <div className="flex gap-1.5 mb-3 overflow-hidden">
                  {[{ l: c.cat_all, on: true }, { l: c.cat_drinks }, { l: c.cat_food }, { l: c.cat_retail }].map((cat, i) => (
                    <span key={i} className="text-[10px] font-semibold px-2.5 py-1 rounded-full border whitespace-nowrap" style={cat.on ? { backgroundColor: brand, color: '#fff', borderColor: brand } : { backgroundColor: '#fff', borderColor: '#e2e8f0', color: '#64748b' }}>{cat.l}</span>
                  ))}
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {tiles.map(({ Icon, cls, brandIcon }, i) => (
                    <div key={i} className="bg-white border border-slate-200 rounded-[9px] overflow-hidden">
                      <div className="h-[34px] grid place-items-center" {...(brandIcon ? { style: { backgroundColor: tint('14'), color: brand700 } } : {})}>
                        <span className={brandIcon ? '' : cls + ' w-full h-full grid place-items-center'}><Icon className="w-[17px] h-[17px]" /></span>
                      </div>
                      <div className="px-2 py-1.5">
                        <div className="h-1.5 w-4/5 bg-slate-100 rounded-sm" />
                        <div className="h-[7px] w-[45%] rounded-sm mt-1.5" style={{ backgroundColor: tint('22') }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {/* right: current sale */}
              <div className="p-4 flex flex-col">
                <div className="text-xs font-bold mb-3">{c.current_sale}</div>
                {saleLines.map((ln, i) => (
                  <div key={i} className="flex items-center gap-2 py-2 border-b border-dashed border-slate-200">
                    <div className={`w-[26px] h-[26px] rounded-[7px] flex-none ${ln.tone}`} />
                    <div className="flex-1">
                      <div className="h-[7px] w-[70%] bg-slate-100 rounded-sm" />
                      <div className="h-1.5 w-2/5 bg-slate-100 rounded-sm mt-1" />
                    </div>
                    <div className="text-[11px] font-bold tabular-nums">{ln.price}</div>
                  </div>
                ))}
                <div className="mt-auto pt-3">
                  <div className="flex justify-between text-[11px] text-slate-500 mb-1"><span>{c.vat_label}</span><span>SAR 7.95</span></div>
                  <div className="flex justify-between items-baseline mb-2.5"><span className="text-xs font-bold">{c.total_label}</span><b className="text-[19px] font-extrabold tabular-nums">SAR 60.95</b></div>
                  <div className="text-center py-2.5 rounded-[9px] text-white text-[13px] font-bold" style={{ backgroundColor: brand }}>{c.pay}</div>
                </div>
              </div>
            </div>
            {/* floating ZATCA QR badge */}
            <div className={`hidden lg:flex absolute top-[60px] ${isRTL ? '-right-5' : '-left-5'} items-center gap-2.5 bg-white border border-slate-200 rounded-xl px-4 py-3 shadow-lg`}>
              <span className="w-[34px] h-[34px] rounded-[9px] grid place-items-center bg-sky/10 text-sky"><QrCode className="w-[18px] h-[18px]" /></span>
              <div>
                <b className="text-sm leading-none block">{c.zatca}</b>
                <span className="text-[11px] text-slate-500">{c.qr_invoice}</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Feature grid */}
      <section id="features" className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px]">
        <div className="text-center max-w-[720px] mx-auto mb-12">
          <span className="font-mono text-xs font-semibold tracking-[0.1em] uppercase mb-3.5 inline-block" style={{ color: brand700 }}>{c.feat_eyebrow}</span>
          <h2 className="text-[32px] md:text-[38px] font-bold leading-[1.08]">{c.feat_title}</h2>
          <p className="text-[17px] text-slate-500 mt-4">{c.feat_sub}</p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-[22px]">
          {c.featureItems.map((item, idx) => {
            const Icon = featureIcons[idx];
            const tone = featureTones[idx];
            return (
              <div key={item.t} className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all">
                <span className="w-[46px] h-[46px] rounded-xl grid place-items-center mb-4" {...(tone.brandIcon ? { style: { backgroundColor: tint('14'), color: brand700 } } : { className: `w-[46px] h-[46px] rounded-xl grid place-items-center mb-4 ${tone.cls ?? ''}` })}>
                  <Icon className="w-[23px] h-[23px]" />
                </span>
                <h3 className="text-[18px] font-bold mb-2">{item.t}</h3>
                <p className="text-[14.5px] text-slate-500 leading-relaxed">{item.d}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Trust chips */}
      <section className="bg-slate-50">
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 py-14">
          <div className="flex flex-wrap gap-3.5 justify-center">
            {c.chips.map((chip, i) => {
              const Icon = chipIcons[i];
              return (
                <span key={chip} className="inline-flex items-center gap-2.5 px-[18px] py-3 border border-slate-200 rounded-full bg-white text-[13.5px] font-semibold text-slate-600">
                  <Icon className="w-[18px] h-[18px]" style={{ color: brand }} />{chip}
                </span>
              );
            })}
          </div>
        </div>
      </section>

      {/* Social proof */}
      <section className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px]">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-7 mb-16">
          {c.stats.map((s) => (
            <div key={s.k} className="text-center">
              <div className="text-[44px] font-extrabold tracking-tight tabular-nums">
                {s.v}{(s as { star?: boolean }).star ? <span className="text-[22px] text-gold">★</span> : null}
              </div>
              <div className="text-sm text-slate-500 mt-1">{s.k}</div>
            </div>
          ))}
        </div>
        <div className="grid md:grid-cols-3 gap-[22px]">
          {c.storyItems.map((s) => (
            <div key={s.name} className="bg-white border border-slate-200 rounded-2xl p-7 shadow-sm flex flex-col gap-[18px]">
              <div className="flex gap-0.5">
                {[...Array(5)].map((_, i) => <Star key={i} className="w-4 h-4 fill-gold text-gold" />)}
              </div>
              <p className="text-base leading-relaxed text-slate-800 font-medium">{s.quote}</p>
              <div className="flex items-center gap-3">
                <span className="w-[42px] h-[42px] rounded-full grid place-items-center font-bold text-[13px] text-white flex-none" style={{ background: `linear-gradient(135deg, ${brand}, ${brand700})` }}>{s.initials}</span>
                <div>
                  <b className="text-sm block">{s.name}</b>
                  <span className="text-[12.5px] text-slate-500">{s.org}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="bg-slate-50">
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px]">
          <div className="text-center max-w-[720px] mx-auto mb-12">
            <span className="font-mono text-xs font-semibold tracking-[0.1em] uppercase mb-3.5 inline-block" style={{ color: brand700 }}>{c.price_eyebrow}</span>
            <h2 className="text-[32px] md:text-[38px] font-bold leading-[1.08]">{c.price_title}</h2>
            <p className="text-[17px] text-slate-500 mt-4">{c.price_sub}</p>
          </div>
          <div className="grid md:grid-cols-3 gap-[22px] items-stretch max-w-5xl mx-auto">
            {c.plans.map((plan) => (
              <div key={plan.name} className="relative bg-white rounded-2xl p-7 flex flex-col shadow-sm border" style={plan.feat ? { borderColor: brand, boxShadow: '0 10px 20px -6px rgba(0,0,0,0.12)' } : { borderColor: '#e2e8f0' }}>
                {plan.feat && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-gold text-gold-900 text-xs font-bold px-3.5 py-1 rounded-full whitespace-nowrap">{c.most_popular}</span>
                )}
                <div className="text-[15px] font-bold">{plan.name}</div>
                <div className="text-[13px] text-slate-500 mt-1 min-h-[38px]">{plan.desc}</div>
                <div className="text-[40px] font-extrabold tracking-tight mt-3.5 mb-0.5 tabular-nums">
                  <span className="text-[18px] text-slate-600 align-super me-0.5">{c.cur}</span>{plan.price}<small className="text-[15px] text-slate-500 font-semibold">{c.per_mo}</small>
                </div>
                <ul className="list-none p-0 mt-5 mb-6 flex flex-col gap-3 flex-1">
                  {plan.features.map((f) => (
                    <li key={f.label} className={`flex items-start gap-2.5 text-sm ${f.off ? 'text-slate-400' : 'text-slate-600'}`}>
                      {f.off ? <X className="w-[18px] h-[18px] text-slate-400 flex-none mt-px" /> : <Check className="w-[18px] h-[18px] text-success flex-none mt-px" />}
                      {f.label}
                    </li>
                  ))}
                </ul>
                {plan.feat ? (
                  <Button onClick={() => navigate('/login')} className="w-full py-6 font-semibold text-base text-white" style={{ backgroundColor: brand }}>{c.trial_cta}</Button>
                ) : (
                  <Button variant="outline" onClick={() => navigate('/login')} className="w-full py-6 font-semibold text-base border-slate-300 !bg-white" style={{ color: brand700 }}>{c.trial_cta}</Button>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Contact CTA */}
      <section id="contact-section" style={{ backgroundColor: brandDark }}>
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px] text-center text-white">
          <h2 className="text-[32px] md:text-[40px] font-bold text-white">{c.cta_title}</h2>
          <p className="text-lg text-white/80 mt-4 mb-7 max-w-[540px] mx-auto">{c.cta_sub}</p>
          <div className="flex flex-wrap justify-center gap-3 mb-6">
            <Button onClick={() => navigate('/login')} className="text-white px-7 py-6 text-base font-semibold" style={{ backgroundColor: brand }}>{c.hero_cta}</Button>
            {profile.contact_phone && (
              <Button onClick={() => window.open(`https://wa.me/${phone.replace(/\D/g, '')}`)} className="bg-white/10 hover:bg-white/20 text-white border border-white/20 px-7 py-6 text-base font-semibold">
                <Phone className={`w-5 h-5 ${isRTL ? 'ml-2' : 'mr-2'}`} />{c.cta_whatsapp}
              </Button>
            )}
          </div>
          <div className="flex flex-wrap justify-center gap-6 text-sm text-white/85">
            <span className="flex items-center gap-2"><Phone className="w-4 h-4" /> {phone}</span>
            <span className="flex items-center gap-2"><Mail className="w-4 h-4" /> {email}</span>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ backgroundColor: brandDark }} className="text-white/80 border-t border-white/10">
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 pt-14 pb-9">
          <div className="grid md:grid-cols-[1.6fr_1fr_1fr_1fr] gap-9 pb-9 border-b border-white/10">
            <div>
              <div className="flex items-center gap-3 mb-1">
                {profile.logo_url ? (
                  <img src={profile.logo_url} alt={profile.company_name} className="w-[34px] h-[34px] rounded-lg object-cover" />
                ) : (
                  <span className="w-[34px] h-[34px] rounded-lg bg-white/15 grid place-items-center text-white"><Store className="w-5 h-5" /></span>
                )}
                <b className="text-white text-[17px]">{profile.company_name}</b>
              </div>
              <p className="text-[13.5px] leading-relaxed mt-3 max-w-[280px] text-white/70">{c.foot_desc}</p>
            </div>
            <div>
              <h4 className="text-white text-[13px] font-bold mb-3.5">{c.foot_product}</h4>
              {c.foot_product_links.map((l) => <a key={l} href="#" className="block text-[13.5px] py-1.5 text-white/80 hover:text-white">{l}</a>)}
            </div>
            <div>
              <h4 className="text-white text-[13px] font-bold mb-3.5">{c.foot_support}</h4>
              <a href="#" className="block text-[13.5px] py-1.5 text-white/80 hover:text-white">{c.support}</a>
              <a href="#" className="block text-[13.5px] py-1.5 text-white/80 hover:text-white">WhatsApp</a>
              <a href="#" className="block text-[13.5px] py-1.5 text-white/80 hover:text-white">{phone}</a>
            </div>
            <div>
              <h4 className="text-white text-[13px] font-bold mb-3.5">{c.foot_company}</h4>
              <a href="#" className="block text-[13.5px] py-1.5 text-white/80 hover:text-white">{profile.company_name}</a>
              <a href="#" className="block text-[13.5px] py-1.5 text-white/80 hover:text-white">{email}</a>
            </div>
          </div>
          <div className="flex flex-wrap justify-between items-center gap-3 pt-6 text-[12.5px] text-white/70">
            <span>© 2026 {profile.company_name} · {c.foot_powered}</span>
            <span>{c.foot_made}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
