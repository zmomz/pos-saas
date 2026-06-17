import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import {
  Store, ArrowRight, Headphones, CheckCircle2, Palette, Users, Repeat, Zap,
  MapPin, Handshake, Star, Check, X,
} from 'lucide-react';

type Plan = { name: string; desc: string; price: string; features: { label: string; off?: boolean }[]; cta: string; feat?: boolean };
type Story = { quote: string; name: string; org: string; initials: string; growth: string; growthLabel: string };

const content = {
  en: {
    program: 'Program', packages: 'Packages', stories: 'Success stories', login: 'Login',
    partner_program: 'PARTNER PROGRAM',
    nav_cta: 'Start Your Business',
    hero_badge: 'Saudi Vision 2030 Partner',
    hero_title_a: 'Start your own', hero_title_b: 'software company.',
    hero_sub_a: 'Launch a white-label POS platform under ', hero_sub_b: 'your', hero_sub_c: ' brand. We handle the tech, compliance and uptime — you keep 100% of your client relationships and recurring revenue.',
    hero_cta: 'Start Your Business Today', hero_sales: 'Talk to Sales',
    trust_1: 'No code required', trust_2: 'Recurring revenue', trust_3: '24/7 partner support',
    rev_label: 'Your monthly recurring revenue', rev_live: 'Live',
    rev_merchants: 'Active merchants', rev_margin: 'Net margin', rev_newclients: 'new clients / mo',
    model_eyebrow: 'The model', model_title_a: 'Your brand.', model_title_b: 'Our technology.',
    model_desc: 'You get a branded landing page, your own domain and full control of pricing and client relationships. We run the ZATCA-compliant POS engine, payments and infrastructure behind the scenes.',
    model_1_t: 'White-label POS', model_1_d: 'Your logo, colors and domain — not ours.',
    model_2_t: 'Full technical support', model_2_d: 'We handle updates, uptime and compliance.',
    model_3_t: 'Keep 100% of client relationships', model_3_d: 'You own the merchants and the billing.',
    mock_1: 'Your Brand POS', mock_2: 'Another Agent',
    why_eyebrow: 'Why partner with us', why_title: 'A business that pays you every month.',
    why_1_t: 'Recurring revenue', why_1_d: 'Earn a margin on every merchant subscription, every single month.',
    why_2_t: 'Zero coding', why_2_d: 'Brand and launch in days. No engineers, no servers, no DevOps.',
    why_3_t: 'Saudi market expertise', why_3_d: 'Built for KSA — ZATCA, Arabic RTL and local payment rails.',
    why_4_t: '24/7 partner support', why_4_d: 'A dedicated team behind you, in Arabic and English, around the clock.',
    how_eyebrow: 'How it works', how_title: 'From sign-up to monthly income in four steps.',
    step_1_t: 'Brand it', step_1_d: 'Add your logo, colors and domain in the branding editor.',
    step_2_t: 'Sell it', step_2_d: 'Share your landing page and close shop & restaurant owners.',
    step_3_t: 'Onboard merchants', step_3_d: 'Spin up each client in minutes — packages, features, done.',
    step_4_t: 'Collect monthly fees', step_4_d: 'We bill, you keep the margin. Watch your MRR compound.',
    pkg_eyebrow: 'Distributor packages', pkg_title: 'Choose your slot capacity.',
    pkg_sub: 'Pick a package by how many merchants you plan to serve. Upgrade anytime.',
    most_popular: 'Most popular', per_mo: '/mo', cur: 'SAR',
    plans: [
      { name: 'Starter', desc: 'For new resellers testing the market.', price: '1,490',
        features: [{ label: 'Up to 25 merchant slots' }, { label: 'White-label landing page' }, { label: 'Branding editor' }, { label: 'Email support' }, { label: 'Custom domain', off: true }],
        cta: 'Choose Starter' },
      { name: 'Growth', desc: 'For established agencies scaling up.', price: '3,900', feat: true,
        features: [{ label: 'Up to 100 merchant slots' }, { label: 'Custom domain + SSL' }, { label: 'Priority partner support' }, { label: 'Advanced reports' }, { label: 'Feature override controls' }],
        cta: 'Choose Growth' },
      { name: 'Enterprise', desc: 'For large distributors & chains.', price: '8,500',
        features: [{ label: '250+ merchant slots' }, { label: 'Dedicated account manager' }, { label: 'API & webhooks' }, { label: 'Custom SLA & onboarding' }, { label: 'Co-marketing budget' }],
        cta: 'Choose Enterprise' },
    ] as Plan[],
    stories_eyebrow: 'Success stories', stories_title: 'Partners growing across the Kingdom.',
    storyItems: [
      { quote: '"We went from zero to 180 merchants in eight months. Cloud POS handles everything technical — we just sell and support."', name: 'Khalid Tamimi', org: 'Tamkeen Tech · Riyadh', initials: 'TT', growth: '+186', growthLabel: 'merchants' },
      { quote: '"The white-label is genuinely ours. Our clients have no idea there’s a platform behind it. That’s the whole game."', name: 'Nora Al-Bayan', org: 'Bayan Solutions · Jeddah', initials: 'BS', growth: 'SAR 35K', growthLabel: 'MRR' },
      { quote: '"Recurring revenue changed our agency. Predictable income every month, and it keeps compounding as we add merchants."', name: 'Yousef Qimam', org: 'Qimam Digital · Dammam', initials: 'QD', growth: '+132', growthLabel: 'merchants' },
    ] as Story[],
    cta_title: 'Ready to build your POS business?',
    cta_sub: 'Join the partner program and launch your branded platform this week.',
    cta_primary: 'Start Your Business Today', cta_secondary: 'Book a demo',
    foot_desc: 'The white-label POS platform for the Saudi market. Build your software company on top of ours.',
    foot_program: 'Program', foot_company: 'Company', foot_legal: 'Legal',
    foot_program_links: ['How it works', 'Packages', 'Partner login'],
    foot_company_links: ['About', 'Success stories', 'Contact sales'],
    foot_legal_links: ['Terms', 'Privacy', 'ZATCA compliance'],
    foot_bottom: '© 2026 Cloud POS · Riyadh, KSA · CR 1010XXXXXX',
  },
  ar: {
    program: 'البرنامج', packages: 'الباقات', stories: 'قصص النجاح', login: 'تسجيل الدخول',
    partner_program: 'برنامج الشركاء',
    nav_cta: 'ابدأ عملك',
    hero_badge: 'شريك رؤية السعودية 2030',
    hero_title_a: 'ابدأ شركتك', hero_title_b: 'البرمجية الخاصة.',
    hero_sub_a: 'أطلق منصة نقاط بيع بعلامة بيضاء تحت علامتك ', hero_sub_b: 'أنت', hero_sub_c: '. نحن نتولى التقنية والامتثال ووقت التشغيل — وتحتفظ أنت بـ100% من علاقات عملائك ودخلك المتكرر.',
    hero_cta: 'ابدأ عملك اليوم', hero_sales: 'تحدث مع المبيعات',
    trust_1: 'بدون برمجة', trust_2: 'دخل متكرر', trust_3: 'دعم شركاء 24/7',
    rev_label: 'دخلك الشهري المتكرر', rev_live: 'مباشر',
    rev_merchants: 'التجار النشطون', rev_margin: 'صافي الهامش', rev_newclients: 'عميل جديد / شهرياً',
    model_eyebrow: 'النموذج', model_title_a: 'علامتك التجارية.', model_title_b: 'تقنيتنا نحن.',
    model_desc: 'تحصل على صفحة هبوط بعلامتك ونطاقك الخاص وتحكم كامل في التسعير وعلاقات العملاء. نحن ندير محرك نقاط البيع المتوافق مع زاتكا والمدفوعات والبنية التحتية خلف الكواليس.',
    model_1_t: 'نقاط بيع بعلامة بيضاء', model_1_d: 'شعارك وألوانك ونطاقك — وليس نطاقنا.',
    model_2_t: 'دعم فني كامل', model_2_d: 'نتولى التحديثات ووقت التشغيل والامتثال.',
    model_3_t: 'احتفظ بـ100% من علاقات العملاء', model_3_d: 'أنت تملك التجار والفوترة.',
    mock_1: 'نقاط بيع علامتك', mock_2: 'وكيل آخر',
    why_eyebrow: 'لماذا الشراكة معنا', why_title: 'عمل يدفع لك كل شهر.',
    why_1_t: 'دخل متكرر', why_1_d: 'اكسب هامشاً على كل اشتراك تاجر، كل شهر.',
    why_2_t: 'بدون أي برمجة', why_2_d: 'علامتك وإطلاقك خلال أيام. بدون مهندسين أو خوادم.',
    why_3_t: 'خبرة بالسوق السعودي', why_3_d: 'مبني للمملكة — زاتكا والعربية والمدفوعات المحلية.',
    why_4_t: 'دعم شركاء 24/7', why_4_d: 'فريق مخصص خلفك، بالعربية والإنجليزية، على مدار الساعة.',
    how_eyebrow: 'كيف يعمل', how_title: 'من التسجيل إلى الدخل الشهري في أربع خطوات.',
    step_1_t: 'خصّص علامتك', step_1_d: 'أضف شعارك وألوانك ونطاقك في محرر العلامة.',
    step_2_t: 'بِعها', step_2_d: 'شارك صفحتك وأغلق صفقات أصحاب المتاجر والمطاعم.',
    step_3_t: 'أضف التجار', step_3_d: 'أنشئ كل عميل في دقائق — باقات وميزات، تم.',
    step_4_t: 'احصّل الرسوم الشهرية', step_4_d: 'نحن نفوتر وأنت تحتفظ بالهامش. شاهد دخلك ينمو.',
    pkg_eyebrow: 'باقات الموزعين', pkg_title: 'اختر سعة الحصص.',
    pkg_sub: 'اختر باقة حسب عدد التجار الذين تنوي خدمتهم. رقِّ في أي وقت.',
    most_popular: 'الأكثر شعبية', per_mo: '/شهرياً', cur: 'ر.س',
    plans: [
      { name: 'المبتدئ', desc: 'للموزعين الجدد الذين يختبرون السوق.', price: '1,490',
        features: [{ label: 'حتى 25 حصة تاجر' }, { label: 'صفحة هبوط بعلامة بيضاء' }, { label: 'محرر العلامة التجارية' }, { label: 'دعم بالبريد' }, { label: 'نطاق مخصص', off: true }],
        cta: 'اختر المبتدئ' },
      { name: 'النمو', desc: 'للوكالات الراسخة التي تتوسع.', price: '3,900', feat: true,
        features: [{ label: 'حتى 100 حصة تاجر' }, { label: 'نطاق مخصص + SSL' }, { label: 'دعم شركاء أولوية' }, { label: 'تقارير متقدمة' }, { label: 'تحكم في تجاوز الميزات' }],
        cta: 'اختر النمو' },
      { name: 'المؤسسات', desc: 'للموزعين الكبار والسلاسل.', price: '8,500',
        features: [{ label: '+250 حصة تاجر' }, { label: 'مدير حساب مخصص' }, { label: 'API وWebhooks' }, { label: 'SLA وتهيئة مخصصة' }, { label: 'ميزانية تسويق مشترك' }],
        cta: 'اختر المؤسسات' },
    ] as Plan[],
    stories_eyebrow: 'قصص النجاح', stories_title: 'شركاء ينمون في أنحاء المملكة.',
    storyItems: [
      { quote: '"انتقلنا من الصفر إلى 180 تاجراً في ثمانية أشهر. كلاود بوس يتولى كل ما هو تقني — ونحن نبيع وندعم فقط."', name: 'خالد التميمي', org: 'تمكين تك · الرياض', initials: 'TT', growth: '+186', growthLabel: 'تاجر' },
      { quote: '"العلامة البيضاء ملكنا حقاً. عملاؤنا لا يعرفون أن هناك منصة خلفها. هذا هو بيت القصيد."', name: 'نورة البيان', org: 'حلول بيان · جدة', initials: 'BS', growth: '35 ألف ر.س', growthLabel: 'دخل شهري' },
      { quote: '"الدخل المتكرر غيّر وكالتنا. دخل متوقع كل شهر، ويتراكم كلما أضفنا تجاراً."', name: 'يوسف قمم', org: 'قمم ديجيتال · الدمام', initials: 'QD', growth: '+132', growthLabel: 'تاجر' },
    ] as Story[],
    cta_title: 'مستعد لبناء عمل نقاط البيع الخاص بك؟',
    cta_sub: 'انضم لبرنامج الشركاء وأطلق منصتك بعلامتك هذا الأسبوع.',
    cta_primary: 'ابدأ عملك اليوم', cta_secondary: 'احجز عرضاً',
    foot_desc: 'منصة نقاط البيع بالعلامة البيضاء للسوق السعودي. ابنِ شركتك البرمجية فوق شركتنا.',
    foot_program: 'البرنامج', foot_company: 'الشركة', foot_legal: 'قانوني',
    foot_program_links: ['كيف يعمل', 'الباقات', 'دخول الشركاء'],
    foot_company_links: ['من نحن', 'قصص النجاح', 'تواصل مع المبيعات'],
    foot_legal_links: ['الشروط', 'الخصوصية', 'الامتثال لزاتكا'],
    foot_bottom: '© 2026 كلاود بوس · الرياض، السعودية · سجل تجاري 1010XXXXXX',
  },
  hi: {
    program: 'प्रोग्राम', packages: 'पैकेज', stories: 'सफलता की कहानियां', login: 'लॉगिन',
    partner_program: 'पार्टनर प्रोग्राम',
    nav_cta: 'व्यवसाय शुरू करें',
    hero_badge: 'सऊदी विजन 2030 पार्टनर',
    hero_title_a: 'अपनी खुद की', hero_title_b: 'सॉफ्टवेयर कंपनी शुरू करें।',
    hero_sub_a: 'अपने ब्रांड के तहत व्हाइट-लेबल POS प्लेटफॉर्म लॉन्च करें — ', hero_sub_b: 'आपका', hero_sub_c: ' ब्रांड। हम तकनीक, अनुपालन और अपटाइम संभालते हैं — आप अपने 100% क्लाइंट संबंध और आवर्ती राजस्व रखते हैं।',
    hero_cta: 'आज ही व्यवसाय शुरू करें', hero_sales: 'सेल्स से बात करें',
    trust_1: 'कोई कोडिंग नहीं', trust_2: 'आवर्ती राजस्व', trust_3: '24/7 पार्टनर सहायता',
    rev_label: 'आपका मासिक आवर्ती राजस्व', rev_live: 'लाइव',
    rev_merchants: 'सक्रिय व्यापारी', rev_margin: 'शुद्ध मार्जिन', rev_newclients: 'नए क्लाइंट / माह',
    model_eyebrow: 'मॉडल', model_title_a: 'आपका ब्रांड।', model_title_b: 'हमारी तकनीक।',
    model_desc: 'आपको ब्रांडेड लैंडिंग पेज, अपना डोमेन और मूल्य निर्धारण व क्लाइंट संबंधों पर पूर्ण नियंत्रण मिलता है। हम पर्दे के पीछे ZATCA-अनुपालन POS इंजन, भुगतान और इन्फ्रास्ट्रक्चर चलाते हैं।',
    model_1_t: 'व्हाइट-लेबल POS', model_1_d: 'आपका लोगो, रंग और डोमेन — हमारा नहीं।',
    model_2_t: 'पूर्ण तकनीकी सहायता', model_2_d: 'हम अपडेट, अपटाइम और अनुपालन संभालते हैं।',
    model_3_t: '100% क्लाइंट संबंध रखें', model_3_d: 'व्यापारी और बिलिंग आपके।',
    mock_1: 'आपका ब्रांड POS', mock_2: 'अन्य एजेंट',
    why_eyebrow: 'हमारे साथ साझेदारी क्यों', why_title: 'एक व्यवसाय जो हर महीने आपको भुगतान करता है।',
    why_1_t: 'आवर्ती राजस्व', why_1_d: 'हर व्यापारी सदस्यता पर, हर महीने मार्जिन कमाएं।',
    why_2_t: 'शून्य कोडिंग', why_2_d: 'दिनों में ब्रांड करें और लॉन्च करें। कोई इंजीनियर या सर्वर नहीं।',
    why_3_t: 'सऊदी बाजार विशेषज्ञता', why_3_d: 'KSA के लिए बना — ZATCA, अरबी RTL और स्थानीय भुगतान।',
    why_4_t: '24/7 पार्टनर सहायता', why_4_d: 'अरबी और अंग्रेजी में, चौबीसों घंटे एक समर्पित टीम।',
    how_eyebrow: 'कैसे काम करता है', how_title: 'साइन-अप से मासिक आय तक चार कदम।',
    step_1_t: 'ब्रांड करें', step_1_d: 'ब्रांडिंग एडिटर में अपना लोगो, रंग और डोमेन जोड़ें।',
    step_2_t: 'बेचें', step_2_d: 'अपना पेज साझा करें और दुकान व रेस्तरां मालिकों को जोड़ें।',
    step_3_t: 'व्यापारी जोड़ें', step_3_d: 'हर क्लाइंट को मिनटों में सेट करें — पैकेज, सुविधाएं, हो गया।',
    step_4_t: 'मासिक शुल्क लें', step_4_d: 'हम बिल करते हैं, आप मार्जिन रखते हैं। अपना MRR बढ़ते देखें।',
    pkg_eyebrow: 'डिस्ट्रीब्यूटर पैकेज', pkg_title: 'अपनी स्लॉट क्षमता चुनें।',
    pkg_sub: 'आप कितने व्यापारियों की सेवा करना चाहते हैं, उसके अनुसार पैकेज चुनें। कभी भी अपग्रेड करें।',
    most_popular: 'सबसे लोकप्रिय', per_mo: '/माह', cur: 'SAR',
    plans: [
      { name: 'स्टार्टर', desc: 'बाजार आज़माने वाले नए रीसेलर्स के लिए।', price: '1,490',
        features: [{ label: '25 व्यापारी स्लॉट तक' }, { label: 'व्हाइट-लेबल लैंडिंग पेज' }, { label: 'ब्रांडिंग एडिटर' }, { label: 'ईमेल सहायता' }, { label: 'कस्टम डोमेन', off: true }],
        cta: 'स्टार्टर चुनें' },
      { name: 'ग्रोथ', desc: 'स्केल करती स्थापित एजेंसियों के लिए।', price: '3,900', feat: true,
        features: [{ label: '100 व्यापारी स्लॉट तक' }, { label: 'कस्टम डोमेन + SSL' }, { label: 'प्राथमिकता पार्टनर सहायता' }, { label: 'उन्नत रिपोर्ट' }, { label: 'फीचर ओवरराइड नियंत्रण' }],
        cta: 'ग्रोथ चुनें' },
      { name: 'एंटरप्राइज़', desc: 'बड़े डिस्ट्रीब्यूटर और चेन के लिए।', price: '8,500',
        features: [{ label: '250+ व्यापारी स्लॉट' }, { label: 'समर्पित अकाउंट मैनेजर' }, { label: 'API और webhooks' }, { label: 'कस्टम SLA और ऑनबोर्डिंग' }, { label: 'को-मार्केटिंग बजट' }],
        cta: 'एंटरप्राइज़ चुनें' },
    ] as Plan[],
    stories_eyebrow: 'सफलता की कहानियां', stories_title: 'पूरे किंगडम में बढ़ते पार्टनर।',
    storyItems: [
      { quote: '"हम आठ महीनों में शून्य से 180 व्यापारियों तक पहुंचे। Cloud POS सब कुछ तकनीकी संभालता है — हम बस बेचते और सहायता करते हैं।"', name: 'खालिद तमीमी', org: 'तमकीन टेक · रियाद', initials: 'TT', growth: '+186', growthLabel: 'व्यापारी' },
      { quote: '"व्हाइट-लेबल वाकई हमारा है। हमारे क्लाइंट्स को पता ही नहीं कि पीछे कोई प्लेटफॉर्म है। यही पूरा खेल है।"', name: 'नोरा अल-बयान', org: 'बयान सॉल्यूशंस · जेद्दा', initials: 'BS', growth: 'SAR 35K', growthLabel: 'MRR' },
      { quote: '"आवर्ती राजस्व ने हमारी एजेंसी बदल दी। हर महीने अनुमानित आय, और व्यापारी जोड़ने पर बढ़ती जाती है।"', name: 'यूसुफ क़िमाम', org: 'क़िमाम डिजिटल · दम्माम', initials: 'QD', growth: '+132', growthLabel: 'व्यापारी' },
    ] as Story[],
    cta_title: 'अपना POS व्यवसाय बनाने के लिए तैयार?',
    cta_sub: 'पार्टनर प्रोग्राम से जुड़ें और इसी सप्ताह अपना ब्रांडेड प्लेटफॉर्म लॉन्च करें।',
    cta_primary: 'आज ही व्यवसाय शुरू करें', cta_secondary: 'डेमो बुक करें',
    foot_desc: 'सऊदी बाजार के लिए व्हाइट-लेबल POS प्लेटफॉर्म। हमारी कंपनी के ऊपर अपनी सॉफ्टवेयर कंपनी बनाएं।',
    foot_program: 'प्रोग्राम', foot_company: 'कंपनी', foot_legal: 'कानूनी',
    foot_program_links: ['कैसे काम करता है', 'पैकेज', 'पार्टनर लॉगिन'],
    foot_company_links: ['हमारे बारे में', 'सफलता की कहानियां', 'सेल्स से संपर्क'],
    foot_legal_links: ['शर्तें', 'गोपनीयता', 'ZATCA अनुपालन'],
    foot_bottom: '© 2026 Cloud POS · रियाद, KSA · CR 1010XXXXXX',
  },
  ur: {
    program: 'پروگرام', packages: 'پیکجز', stories: 'کامیابی کی کہانیاں', login: 'لاگ ان',
    partner_program: 'پارٹنر پروگرام',
    nav_cta: 'کاروبار شروع کریں',
    hero_badge: 'سعودی ویژن 2030 پارٹنر',
    hero_title_a: 'اپنی سافٹ ویئر', hero_title_b: 'کمپنی شروع کریں۔',
    hero_sub_a: 'اپنے برانڈ کے تحت وائٹ لیبل POS پلیٹ فارم لانچ کریں — ', hero_sub_b: 'آپ کا', hero_sub_c: ' برانڈ۔ ہم ٹیکنالوجی، تعمیل اور اپ ٹائم سنبھالتے ہیں — آپ اپنے 100% کلائنٹ تعلقات اور بار بار آمدنی رکھتے ہیں۔',
    hero_cta: 'آج ہی کاروبار شروع کریں', hero_sales: 'سیلز سے بات کریں',
    trust_1: 'کوئی کوڈنگ نہیں', trust_2: 'بار بار آمدنی', trust_3: '24/7 پارٹنر سپورٹ',
    rev_label: 'آپ کی ماہانہ بار بار آمدنی', rev_live: 'لائیو',
    rev_merchants: 'فعال تاجر', rev_margin: 'خالص مارجن', rev_newclients: 'نئے کلائنٹ / ماہ',
    model_eyebrow: 'ماڈل', model_title_a: 'آپ کا برانڈ۔', model_title_b: 'ہماری ٹیکنالوجی۔',
    model_desc: 'آپ کو برانڈڈ لینڈنگ پیج، اپنا ڈومین اور قیمتوں و کلائنٹ تعلقات پر مکمل کنٹرول ملتا ہے۔ ہم پردے کے پیچھے ZATCA-تعمیل POS انجن، ادائیگیاں اور انفراسٹرکچر چلاتے ہیں۔',
    model_1_t: 'وائٹ لیبل POS', model_1_d: 'آپ کا لوگو، رنگ اور ڈومین — ہمارا نہیں۔',
    model_2_t: 'مکمل تکنیکی سپورٹ', model_2_d: 'ہم اپڈیٹس، اپ ٹائم اور تعمیل سنبھالتے ہیں۔',
    model_3_t: '100% کلائنٹ تعلقات رکھیں', model_3_d: 'تاجر اور بلنگ آپ کے۔',
    mock_1: 'آپ کا برانڈ POS', mock_2: 'دوسرا ایجنٹ',
    why_eyebrow: 'ہمارے ساتھ شراکت کیوں', why_title: 'ایک کاروبار جو ہر ماہ آپ کو ادائیگی کرتا ہے۔',
    why_1_t: 'بار بار آمدنی', why_1_d: 'ہر تاجر سبسکرپشن پر، ہر ماہ مارجن کمائیں۔',
    why_2_t: 'صفر کوڈنگ', why_2_d: 'دنوں میں برانڈ اور لانچ کریں۔ کوئی انجینئر یا سرور نہیں۔',
    why_3_t: 'سعودی مارکیٹ مہارت', why_3_d: 'KSA کے لیے بنایا — ZATCA، عربی RTL اور مقامی ادائیگیاں۔',
    why_4_t: '24/7 پارٹنر سپورٹ', why_4_d: 'عربی اور انگریزی میں، چوبیس گھنٹے ایک مخصوص ٹیم۔',
    how_eyebrow: 'کیسے کام کرتا ہے', how_title: 'سائن اپ سے ماہانہ آمدنی تک چار مراحل۔',
    step_1_t: 'برانڈ کریں', step_1_d: 'برانڈنگ ایڈیٹر میں اپنا لوگو، رنگ اور ڈومین شامل کریں۔',
    step_2_t: 'بیچیں', step_2_d: 'اپنا پیج شیئر کریں اور دکان و ریسٹورنٹ مالکان کو شامل کریں۔',
    step_3_t: 'تاجر شامل کریں', step_3_d: 'ہر کلائنٹ کو منٹوں میں سیٹ کریں — پیکجز، فیچرز، ہو گیا۔',
    step_4_t: 'ماہانہ فیس وصول کریں', step_4_d: 'ہم بل کرتے ہیں، آپ مارجن رکھتے ہیں۔ اپنا MRR بڑھتے دیکھیں۔',
    pkg_eyebrow: 'ڈسٹریبیوٹر پیکجز', pkg_title: 'اپنی سلاٹ گنجائش منتخب کریں۔',
    pkg_sub: 'آپ کتنے تاجروں کی خدمت کرنا چاہتے ہیں اس کے مطابق پیکج منتخب کریں۔ کسی بھی وقت اپ گریڈ کریں۔',
    most_popular: 'سب سے مقبول', per_mo: '/ماہ', cur: 'ر.س',
    plans: [
      { name: 'اسٹارٹر', desc: 'مارکیٹ آزمانے والے نئے ری سیلرز کے لیے۔', price: '1,490',
        features: [{ label: '25 تاجر سلاٹ تک' }, { label: 'وائٹ لیبل لینڈنگ پیج' }, { label: 'برانڈنگ ایڈیٹر' }, { label: 'ای میل سپورٹ' }, { label: 'کسٹم ڈومین', off: true }],
        cta: 'اسٹارٹر منتخب کریں' },
      { name: 'گروتھ', desc: 'اسکیل کرتی قائم ایجنسیوں کے لیے۔', price: '3,900', feat: true,
        features: [{ label: '100 تاجر سلاٹ تک' }, { label: 'کسٹم ڈومین + SSL' }, { label: 'ترجیحی پارٹنر سپورٹ' }, { label: 'ایڈوانسڈ رپورٹس' }, { label: 'فیچر اوور رائیڈ کنٹرول' }],
        cta: 'گروتھ منتخب کریں' },
      { name: 'انٹرپرائز', desc: 'بڑے ڈسٹریبیوٹرز اور چینز کے لیے۔', price: '8,500',
        features: [{ label: '250+ تاجر سلاٹ' }, { label: 'مخصوص اکاؤنٹ مینیجر' }, { label: 'API اور webhooks' }, { label: 'کسٹم SLA اور آن بورڈنگ' }, { label: 'کو-مارکیٹنگ بجٹ' }],
        cta: 'انٹرپرائز منتخب کریں' },
    ] as Plan[],
    stories_eyebrow: 'کامیابی کی کہانیاں', stories_title: 'پورے مملکت میں بڑھتے پارٹنرز۔',
    storyItems: [
      { quote: '"ہم آٹھ ماہ میں صفر سے 180 تاجروں تک پہنچے۔ Cloud POS ہر تکنیکی چیز سنبھالتا ہے — ہم بس بیچتے اور سپورٹ کرتے ہیں۔"', name: 'خالد تمیمی', org: 'تمکین ٹیک · ریاض', initials: 'TT', growth: '+186', growthLabel: 'تاجر' },
      { quote: '"وائٹ لیبل واقعی ہمارا ہے۔ ہمارے کلائنٹس کو معلوم ہی نہیں کہ پیچھے کوئی پلیٹ فارم ہے۔ یہی سارا کھیل ہے۔"', name: 'نورہ البیان', org: 'بیان سلوشنز · جدہ', initials: 'BS', growth: 'SAR 35K', growthLabel: 'MRR' },
      { quote: '"بار بار آمدنی نے ہماری ایجنسی بدل دی۔ ہر ماہ متوقع آمدنی، اور تاجر شامل کرنے پر بڑھتی جاتی ہے۔"', name: 'یوسف قمم', org: 'قمم ڈیجیٹل · دمام', initials: 'QD', growth: '+132', growthLabel: 'تاجر' },
    ] as Story[],
    cta_title: 'اپنا POS کاروبار بنانے کے لیے تیار؟',
    cta_sub: 'پارٹنر پروگرام میں شامل ہوں اور اسی ہفتے اپنا برانڈڈ پلیٹ فارم لانچ کریں۔',
    cta_primary: 'آج ہی کاروبار شروع کریں', cta_secondary: 'ڈیمو بک کریں',
    foot_desc: 'سعودی مارکیٹ کے لیے وائٹ لیبل POS پلیٹ فارم۔ ہماری کمپنی کے اوپر اپنی سافٹ ویئر کمپنی بنائیں۔',
    foot_program: 'پروگرام', foot_company: 'کمپنی', foot_legal: 'قانونی',
    foot_program_links: ['کیسے کام کرتا ہے', 'پیکجز', 'پارٹنر لاگ ان'],
    foot_company_links: ['ہمارے بارے میں', 'کامیابی کی کہانیاں', 'سیلز سے رابطہ'],
    foot_legal_links: ['شرائط', 'رازداری', 'ZATCA تعمیل'],
    foot_bottom: '© 2026 Cloud POS · ریاض، KSA · CR 1010XXXXXX',
  },
};

/** Live MRR area+line chart used in the hero revenue card. */
function RevenueChart() {
  const data = [22, 25, 24, 29, 33, 36, 41, 44, 46, 48.2];
  const w = 440, h = 120, min = 18, max = 52;
  const x = (i: number) => (i / (data.length - 1)) * w;
  const y = (v: number) => h - 6 - ((v - min) / (max - min)) * (h - 18);
  let line = '';
  data.forEach((v, i) => { line += (i ? 'L' : 'M') + ` ${x(i).toFixed(1)} ${y(v).toFixed(1)} `; });
  let area = `M ${x(0)} ${y(data[0])} `;
  data.forEach((v, i) => { if (i) area += `L ${x(i).toFixed(1)} ${y(v).toFixed(1)} `; });
  area += `L ${w} ${h} L 0 ${h} Z`;
  const last = data.length - 1;
  return (
    <svg viewBox="0 0 440 120" preserveAspectRatio="none" className="w-full h-full overflow-visible">
      <defs>
        <linearGradient id="rg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="hsl(var(--primary))" stopOpacity="0.26" />
          <stop offset="1" stopColor="hsl(var(--primary))" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#rg)" />
      <path d={line} fill="none" stroke="hsl(var(--primary))" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={x(last).toFixed(1)} cy={y(data[last]).toFixed(1)} r="5" fill="hsl(var(--primary))" stroke="#fff" strokeWidth="2" />
    </svg>
  );
}

/**
 * Public partner-program landing page.
 *
 * Phase 5 decision: this marketing surface is intentionally light. It paints on
 * fixed palettes only (`slate-*` neutrals + `brand`/`gold`/`success`, none of
 * which are theme tokens), so it never half-inverts when a signed-in user has
 * the app in dark mode — and a logged-out visitor has no theme toggle here. We
 * deliberately do NOT route it through the inverting app tokens (`bg-background`
 * etc.); doing so would flip the brochure to dark and break the design.
 */
export default function LandingPage() {
  const navigate = useNavigate();
  const { language, setLanguage, isRTL } = useLanguage();
  const c = content[language] || content.en;

  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });

  const modelRows = [
    { icon: Palette, t: c.model_1_t, d: c.model_1_d, tone: 'bg-brand-50 text-brand-700' },
    { icon: Headphones, t: c.model_2_t, d: c.model_2_d, tone: 'bg-success/10 text-success' },
    { icon: Users, t: c.model_3_t, d: c.model_3_d, tone: 'bg-gold-50 text-gold-600' },
  ];

  const whyCards = [
    { icon: Repeat, t: c.why_1_t, d: c.why_1_d, tone: 'bg-success/10 text-success' },
    { icon: Zap, t: c.why_2_t, d: c.why_2_d, tone: 'bg-brand-50 text-brand-700' },
    { icon: MapPin, t: c.why_3_t, d: c.why_3_d, tone: 'bg-gold-50 text-gold-600' },
    { icon: Headphones, t: c.why_4_t, d: c.why_4_d, tone: 'bg-violet/10 text-violet' },
  ];

  const steps = [
    { n: 1, t: c.step_1_t, d: c.step_1_d },
    { n: 2, t: c.step_2_t, d: c.step_2_d },
    { n: 3, t: c.step_3_t, d: c.step_3_d },
    { n: 4, t: c.step_4_t, d: c.step_4_d },
  ];

  return (
    <div className={`min-h-screen bg-white text-slate-900 ${isRTL ? 'font-arabic' : ''}`} dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Nav */}
      <nav className="sticky top-0 z-40 bg-white/85 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 py-3.5 flex items-center justify-between">
          <button onClick={() => scrollTo('top')} className="flex items-center gap-3">
            <span className="w-9 h-9 rounded-[9px] bg-brand-500 text-white grid place-items-center">
              <Store className="w-5 h-5" />
            </span>
            <span className="text-start leading-none">
              <b className="text-[17px] font-bold tracking-tight block">Cloud POS</b>
              <small className="font-mono text-[9.5px] text-slate-400 tracking-wide">{c.partner_program}</small>
            </span>
          </button>
          <div className="flex items-center gap-2">
            <button onClick={() => scrollTo('how-it-works')} className="hidden md:inline-flex text-sm font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-3.5 py-2 rounded-lg transition-colors">{c.program}</button>
            <button onClick={() => scrollTo('packages')} className="hidden md:inline-flex text-sm font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-3.5 py-2 rounded-lg transition-colors">{c.packages}</button>
            <button onClick={() => scrollTo('stories')} className="hidden lg:inline-flex text-sm font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-3.5 py-2 rounded-lg transition-colors">{c.stories}</button>
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
            <Button onClick={() => navigate('/login')} className="bg-brand-500 hover:bg-brand-600 text-white font-semibold h-9 px-4">{c.nav_cta}</Button>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <header id="top" className="relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(780px 460px at 78% 8%, rgba(20,136,166,0.10), transparent 62%)' }} />
        <div className="relative max-w-[1180px] mx-auto px-6 lg:px-8 pt-16 pb-20 grid lg:grid-cols-[1.05fr_0.95fr] gap-14 items-center">
          <div className={isRTL ? 'lg:order-1' : ''}>
            <span className="inline-flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-full bg-gold-50 text-gold-600 border border-gold/40 mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-gold-600" /> {c.hero_badge}
            </span>
            <h1 className="text-[40px] md:text-[54px] font-bold leading-[1.03] tracking-tight text-slate-900">
              {c.hero_title_a}<br />{c.hero_title_b}
            </h1>
            <p className="text-lg md:text-[19px] text-slate-600 leading-relaxed mt-5 max-w-xl">
              {c.hero_sub_a}<b className="text-slate-900">{c.hero_sub_b}</b>{c.hero_sub_c}
            </p>
            <div className="flex flex-wrap gap-3 mt-8">
              <Button onClick={() => scrollTo('packages')} className="bg-brand-500 hover:bg-brand-600 text-white px-6 py-6 text-base font-semibold shadow-brand">
                {c.hero_cta}<ArrowRight className={`w-5 h-5 ms-2 ${isRTL ? 'rotate-180' : ''}`} />
              </Button>
              <Button variant="outline" onClick={() => navigate('/login')} className="px-6 py-6 text-base font-semibold border-slate-300 hover:border-brand-500 hover:text-brand-700 hover:bg-brand-50 !bg-white">
                <Headphones className="w-5 h-5 me-2" />{c.hero_sales}
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

          {/* Revenue mockup */}
          <div className={`relative ${isRTL ? 'lg:order-1' : ''}`}>
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xl">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[13px] font-medium text-slate-500">{c.rev_label}</span>
                <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-success" /> {c.rev_live}
                </span>
              </div>
              <div className="text-[34px] font-extrabold tracking-tight tabular-nums">
                {c.cur} 48,200<span className="text-sm font-bold text-success ms-2">↑ 38%</span>
              </div>
              <div className="h-[120px] my-3.5"><RevenueChart /></div>
              <div className="grid grid-cols-2 gap-px bg-slate-200 rounded-xl overflow-hidden mt-4">
                <div className="bg-white px-4 py-3">
                  <div className="text-[11.5px] text-slate-500">{c.rev_merchants}</div>
                  <div className="text-lg font-extrabold tabular-nums mt-0.5">214</div>
                </div>
                <div className="bg-white px-4 py-3">
                  <div className="text-[11.5px] text-slate-500">{c.rev_margin}</div>
                  <div className="text-lg font-extrabold tabular-nums mt-0.5 text-success">71%</div>
                </div>
              </div>
            </div>
            {/* floating stat */}
            <div className="hidden lg:flex absolute top-9 -start-6 items-center gap-3 bg-white border border-slate-200 rounded-xl px-4 py-3 shadow-lg">
              <span className="w-9 h-9 rounded-[9px] bg-success/10 text-success grid place-items-center"><Users className="w-[18px] h-[18px]" /></span>
              <div>
                <b className="text-base leading-none block tabular-nums">+9</b>
                <span className="text-[11px] text-slate-500">{c.rev_newclients}</span>
              </div>
            </div>
            {/* handshake chip */}
            <div className="hidden lg:grid absolute -bottom-4 -end-3.5 w-16 h-16 rounded-[18px] bg-gold text-gold-900 place-items-center shadow-lg -rotate-6">
              <Handshake className="w-8 h-8" />
            </div>
          </div>
        </div>
      </header>

      {/* Partnership model */}
      <section className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px]">
        <div className="grid lg:grid-cols-2 gap-14 items-center">
          <div className={isRTL ? 'lg:order-2' : ''}>
            <span className="font-mono text-xs font-semibold tracking-[0.1em] uppercase text-brand-700">{c.model_eyebrow}</span>
            <h2 className="text-[32px] md:text-[38px] font-bold leading-[1.08] mt-3.5 mb-4">{c.model_title_a}<br />{c.model_title_b}</h2>
            <p className="text-[17px] text-slate-600 leading-relaxed mb-7">{c.model_desc}</p>
            <div className="flex flex-col gap-4">
              {modelRows.map(({ icon: Icon, t, d, tone }) => (
                <div key={t} className="flex items-center gap-3">
                  <span className={`w-[42px] h-[42px] rounded-[11px] grid place-items-center flex-none ${tone}`}><Icon className="w-5 h-5" /></span>
                  <div>
                    <b className="font-semibold">{t}</b>
                    <div className="text-slate-500 text-[13.5px]">{d}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className={`relative ${isRTL ? 'lg:order-1' : ''}`}>
            <div className="rounded-2xl overflow-hidden border border-slate-200 shadow-md">
              <div className="h-[46px] flex items-center gap-2 px-4 bg-gradient-to-br from-brand-700 to-brand-500">
                <span className="w-6 h-6 rounded-[7px] bg-white/25" />
                <b className="text-white text-[13px]">{c.mock_1}</b>
                <span className="ms-auto flex gap-3.5">{[0, 1, 2].map((i) => <i key={i} className="w-[34px] h-[7px] rounded bg-white/30" />)}</span>
              </div>
              <div className="p-6 bg-white flex flex-col gap-3">
                <div className="h-4 w-3/5 bg-slate-100 rounded-md" />
                <div className="h-[11px] w-4/5 bg-slate-100 rounded-md" />
                <div className="h-[11px] w-[65%] bg-slate-100 rounded-md" />
                <div className="h-9 w-36 rounded-lg bg-brand-500 mt-1.5" />
              </div>
            </div>
            {/* The "Another Agent" mock is deliberately a *different* (green)
                brand to illustrate that each partner runs their own identity —
                so these greens are intentional literals, not the product palette. */}
            <div className={`rounded-2xl overflow-hidden border border-slate-200 shadow-md mt-4 ${isRTL ? 'me-12' : 'ms-12'}`}>
              <div className="h-[46px] flex items-center gap-2 px-4 bg-gradient-to-br from-[#2e7d54] to-[#3f9d6a]">
                <span className="w-6 h-6 rounded-[7px] bg-white/25" />
                <b className="text-white text-[13px]">{c.mock_2}</b>
                <span className="ms-auto flex gap-3.5">{[0, 1].map((i) => <i key={i} className="w-[34px] h-[7px] rounded bg-white/30" />)}</span>
              </div>
              <div className="px-6 py-4 bg-white flex flex-col gap-3">
                <div className="h-4 w-3/5 bg-slate-100 rounded-md" />
                <div className="h-[30px] w-32 rounded-lg bg-[#3f9d6a]" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Why partner */}
      <section className="bg-slate-50">
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px]">
          <div className="text-center max-w-[720px] mx-auto mb-12">
            <span className="font-mono text-xs font-semibold tracking-[0.1em] uppercase text-brand-700 mb-3.5 inline-block">{c.why_eyebrow}</span>
            <h2 className="text-[32px] md:text-[38px] font-bold leading-[1.08]">{c.why_title}</h2>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-[18px] mt-12">
            {whyCards.map(({ icon: Icon, t, d, tone }) => (
              <div key={t} className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all">
                <span className={`w-[46px] h-[46px] rounded-xl grid place-items-center mb-4 ${tone}`}><Icon className="w-[23px] h-[23px]" /></span>
                <h3 className="text-[18px] font-bold mb-2">{t}</h3>
                <p className="text-[14.5px] text-slate-500 leading-relaxed">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px]">
        <div className="text-center max-w-[720px] mx-auto mb-12">
          <span className="font-mono text-xs font-semibold tracking-[0.1em] uppercase text-brand-700 mb-3.5 inline-block">{c.how_eyebrow}</span>
          <h2 className="text-[32px] md:text-[38px] font-bold leading-[1.08]">{c.how_title}</h2>
        </div>
        <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-y-10 mt-12">
          {steps.map((s, idx) => (
            <div key={s.n} className="text-center px-4 relative">
              {idx < steps.length - 1 && (
                <div className={`hidden md:block absolute top-7 ${isRTL ? 'right-1/2 me-9' : 'left-1/2 ms-9'} w-[calc(100%-72px)] border-t-2 border-dashed border-brand-100`} />
              )}
              <div className="w-14 h-14 rounded-full bg-brand-500 text-white grid place-items-center text-[22px] font-extrabold mx-auto mb-4 relative z-[2] ring-[6px] ring-brand-50">{s.n}</div>
              <h3 className="text-[17px] font-bold mb-2">{s.t}</h3>
              <p className="text-sm text-slate-500 leading-snug">{s.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Packages */}
      <section id="packages" className="bg-slate-50">
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px]">
          <div className="text-center max-w-[720px] mx-auto mb-12">
            <span className="font-mono text-xs font-semibold tracking-[0.1em] uppercase text-brand-700 mb-3.5 inline-block">{c.pkg_eyebrow}</span>
            <h2 className="text-[32px] md:text-[38px] font-bold leading-[1.08]">{c.pkg_title}</h2>
            <p className="text-[17px] text-slate-500 mt-4">{c.pkg_sub}</p>
          </div>
          <div className="grid md:grid-cols-3 gap-[22px] items-stretch mt-12 max-w-5xl mx-auto">
            {c.plans.map((plan) => (
              <div
                key={plan.name}
                className={`relative bg-white rounded-2xl p-7 flex flex-col shadow-sm border ${plan.feat ? 'border-brand-500 shadow-md md:scale-[1.03]' : 'border-slate-200'}`}
              >
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
                <Button
                  onClick={() => navigate('/login')}
                  className={`w-full py-6 font-semibold text-base ${plan.feat ? 'bg-brand-500 hover:bg-brand-600 text-white' : 'bg-white hover:bg-brand-50 text-slate-900 border border-slate-300 hover:border-brand-500 hover:text-brand-700'}`}
                >
                  {plan.cta}
                </Button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section id="stories" className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px]">
        <div className="text-center max-w-[720px] mx-auto mb-12">
          <span className="font-mono text-xs font-semibold tracking-[0.1em] uppercase text-brand-700 mb-3.5 inline-block">{c.stories_eyebrow}</span>
          <h2 className="text-[32px] md:text-[38px] font-bold leading-[1.08]">{c.stories_title}</h2>
        </div>
        <div className="grid md:grid-cols-3 gap-[22px] mt-12">
          {c.storyItems.map((s) => (
            <div key={s.name} className="bg-white border border-slate-200 rounded-2xl p-7 shadow-sm flex flex-col gap-[18px]">
              <div className="flex gap-0.5 text-gold">
                {[...Array(5)].map((_, i) => <Star key={i} className="w-4 h-4 fill-gold text-gold" />)}
              </div>
              <p className="text-base leading-relaxed text-slate-800 font-medium">{s.quote}</p>
              <div className="flex items-center gap-3">
                <span className="w-[42px] h-[42px] rounded-full grid place-items-center font-bold text-[13px] text-white flex-none bg-gradient-to-br from-brand-500 to-brand-700">{s.initials}</span>
                <div>
                  <b className="text-sm block">{s.name}</b>
                  <span className="text-[12.5px] text-slate-500">{s.org}</span>
                </div>
                <div className="ms-auto text-end">
                  <b className="text-[18px] text-success block tabular-nums">{s.growth}</b>
                  <span className="text-[11px] text-slate-500">{s.growthLabel}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Dark CTA band */}
      <section className="bg-brand-800 text-brand-100">
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 py-20 lg:py-[88px] text-center">
          <h2 className="text-[32px] md:text-[40px] font-bold text-white">{c.cta_title}</h2>
          <p className="text-lg text-brand-100/80 mt-4 mb-7 max-w-[560px] mx-auto">{c.cta_sub}</p>
          <div className="flex flex-wrap justify-center gap-3">
            <Button onClick={() => navigate('/login')} className="bg-gold hover:bg-gold-600 text-gold-900 px-7 py-6 text-base font-semibold">{c.cta_primary}</Button>
            <Button onClick={() => navigate('/login')} className="bg-white/10 hover:bg-white/20 text-white border border-white/20 px-7 py-6 text-base font-semibold">{c.cta_secondary}</Button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-brand-800 text-brand-100/80 border-t border-white/10">
        <div className="max-w-[1180px] mx-auto px-6 lg:px-8 pt-14 pb-9">
          <div className="grid md:grid-cols-[1.6fr_1fr_1fr_1fr] gap-9 pb-9 border-b border-white/10">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <span className="w-[34px] h-[34px] rounded-lg bg-white/15 grid place-items-center text-white"><Store className="w-5 h-5" /></span>
                <b className="text-white text-[17px]">Cloud POS</b>
              </div>
              <p className="text-[13.5px] leading-relaxed mt-3 max-w-[280px] text-brand-100/70">{c.foot_desc}</p>
            </div>
            <div>
              <h4 className="text-white text-[13px] font-bold mb-3.5">{c.foot_program}</h4>
              {c.foot_program_links.map((l) => <a key={l} href="#" className="block text-[13.5px] py-1.5 text-brand-100/80 hover:text-white">{l}</a>)}
            </div>
            <div>
              <h4 className="text-white text-[13px] font-bold mb-3.5">{c.foot_company}</h4>
              {c.foot_company_links.map((l) => <a key={l} href="#" className="block text-[13.5px] py-1.5 text-brand-100/80 hover:text-white">{l}</a>)}
            </div>
            <div>
              <h4 className="text-white text-[13px] font-bold mb-3.5">{c.foot_legal}</h4>
              {c.foot_legal_links.map((l) => <a key={l} href="#" className="block text-[13.5px] py-1.5 text-brand-100/80 hover:text-white">{l}</a>)}
            </div>
          </div>
          <div className="flex flex-wrap justify-between items-center gap-3 pt-6 text-[12.5px] text-brand-100/70">
            <span>{c.foot_bottom}</span>
            <span className="flex items-center gap-4">
              <a href="#" className="hover:text-white">LinkedIn</a>
              <a href="#" className="hover:text-white">X</a>
              <a href="#" className="hover:text-white">WhatsApp</a>
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
