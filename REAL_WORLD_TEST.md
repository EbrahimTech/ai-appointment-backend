# 🌍 دليل التجربة الحقيقية المتكاملة

هذا الدليل يوضح كيفية إعداد تجربة حقيقية متكاملة مع:
- ✅ عيادة حقيقية
- ✅ WhatsApp (إرسال واستقبال رسائل)
- ✅ Google Calendar (مزامنة المواعيد)
- ✅ DeepSeek AI (الذكاء الاصطناعي للمحادثات)

---

## 📋 ما يتبقى لإعداد التجربة الحقيقية

### 1️⃣ إعداد DeepSeek AI (الذكاء الاصطناعي)

#### الخطوة 1: الحصول على API Key
1. اذهب إلى: https://platform.deepseek.com/
2. سجل حساب جديد (أو سجل دخول)
3. اذهب إلى API Keys section
4. أنشئ API Key جديد
5. انسخ الـ API Key

#### الخطوة 2: إضافة إلى .env
```env
# في ملف .env
DEEPSEEK_API_KEY=sk-your-api-key-here
DEEPSEEK_API_BASE=https://api.deepseek.com
```

#### الخطوة 3: إعادة تشغيل Backend
```bash
docker-compose restart web worker
```

**✅ الآن AI جاهز!** سيستخدم DeepSeek للرد على رسائل WhatsApp تلقائياً.

---

### 2️⃣ إعداد Google Calendar

#### الخطوة 1: إنشاء Google Cloud Project
1. اذهب إلى: https://console.cloud.google.com/
2. أنشئ مشروع جديد (أو استخدم موجود)
3. فعّل Google Calendar API:
   - اذهب إلى "APIs & Services" > "Library"
   - ابحث عن "Google Calendar API"
   - اضغط "Enable"

#### الخطوة 2: إنشاء OAuth Credentials
1. اذهب إلى "APIs & Services" > "Credentials"
2. اضغط "Create Credentials" > "OAuth client ID"
3. اختر "Web application"
4. أضف Authorized redirect URIs:
   - للتطوير: `http://localhost:8000/calendars/google/callback`
   - للإنتاج: `https://yourdomain.com/calendars/google/callback`
5. انسخ Client ID و Client Secret

#### الخطوة 3: إضافة إلى .env
```env
# في ملف .env
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/calendars/google/callback
```

#### الخطوة 4: ربط Calendar بالعيادة
1. سجل دخول إلى Clinic Portal
2. اذهب إلى `/c/[slug]/integrations`
3. اضغط "Connect Google Calendar"
4. سجل دخول بحساب Google
5. وافق على الصلاحيات

**✅ الآن Google Calendar جاهز!** سيتم مزامنة المواعيد تلقائياً.

---

### 3️⃣ إعداد WhatsApp

#### الخيار الأول: WhatsApp Test Mode (للاختبار)

**الخطوة 1: إعداد Test Mode**
```env
# في ملف .env
WHATSAPP_TEST_ALLOWLIST={"*":["+1234567890","+0987654321"]}
WHATSAPP_TEST_RPM=3
WHATSAPP_DEFAULT_SENDER=+1234567890
```

**ملاحظة:** في Test Mode:
- يمكنك إرسال رسائل إلى أرقام محددة فقط (في ALLOWLIST)
- لا تحتاج إلى WhatsApp Business API
- مناسب للاختبار فقط

#### الخيار الثاني: WhatsApp Business API (للإنتاج)

**الخطوة 1: اختيار Provider**

**أ) Meta WhatsApp Business API:**
1. اذهب إلى: https://business.facebook.com/
2. أنشئ WhatsApp Business Account
3. احصل على:
   - Phone Number ID
   - Access Token
   - App Secret (اختياري)

**ب) Twilio WhatsApp:**
1. اذهب إلى: https://www.twilio.com/
2. أنشئ حساب
3. احصل على:
   - Account SID
   - Auth Token
   - WhatsApp-enabled phone number

**الخطوة 2: إضافة Channel Account في النظام**

1. سجل دخول إلى Clinic Portal
2. اذهب إلى `/c/[slug]/integrations`
3. اضغط "Add WhatsApp Channel"
4. اختر Provider (Meta أو Twilio)
5. أدخل Credentials:
   - **Meta**: Phone Number ID, Access Token
   - **Twilio**: Account SID, Auth Token, From Number

**الخطوة 3: إعداد في .env (اختياري)**
```env
# في ملف .env (للإعدادات الافتراضية)
WHATSAPP_DEFAULT_SENDER=+1234567890
WHATSAPP_SESSION_FALLBACK_HSM_NAME=session_clarify
```

**✅ الآن WhatsApp جاهز!** يمكنك إرسال واستقبال رسائل.

---

### 4️⃣ إنشاء عيادة حقيقية

#### الخطوة 1: إنشاء العيادة من HQ Portal
1. سجل دخول كـ HQ Admin
2. اذهب إلى `/hq`
3. اضغط "New Tenant"
4. املأ البيانات:
   - **Name**: اسم العيادة (مثال: "Dental Clinic")
   - **Slug**: معرف فريد (مثال: "dental-clinic")
   - **Phone**: رقم الهاتف
   - **Email**: البريد الإلكتروني
   - **Address**: العنوان
   - **Timezone**: المنطقة الزمنية
   - **Language**: اللغة الافتراضية

#### الخطوة 2: إعداد العيادة
1. سجل دخول كـ Clinic Owner
2. اذهب إلى `/c/[slug]/onboarding`
3. اكمل Setup Checklist:
   - ✅ إضافة Services (الخدمات)
   - ✅ إعداد Operating Hours (ساعات العمل)
   - ✅ إضافة Templates (قوالب الرسائل)
   - ✅ ربط Google Calendar
   - ✅ إعداد WhatsApp Channel

#### الخطوة 3: إضافة Services
1. اذهب إلى `/c/[slug]/services`
2. اضغط "Add Service"
3. املأ:
   - **Name**: اسم الخدمة (مثال: "Cleaning", "Checkup")
   - **Duration**: المدة بالدقائق
   - **Price**: السعر (اختياري)

#### الخطوة 4: إعداد Operating Hours
1. في نفس صفحة `/c/[slug]/services`
2. اضغط "Edit Hours"
3. حدد ساعات العمل لكل يوم

#### الخطوة 5: إضافة Message Templates
1. اذهب إلى `/c/[slug]/templates`
2. اضغط "Add Template"
3. أنشئ قوالب مثل:
   - **greet**: رسالة الترحيب
   - **confirm**: تأكيد الموعد
   - **remind**: تذكير بالموعد
   - **cancel**: إلغاء الموعد

---

## 🧪 سيناريو التجربة الحقيقية

### السيناريو 1: محادثة WhatsApp مع AI

1. **إرسال رسالة WhatsApp:**
   - أرسل رسالة إلى رقم WhatsApp الخاص بالعيادة
   - مثال: "أريد حجز موعد"

2. **الرد التلقائي من AI:**
   - AI (DeepSeek) سيفهم الرسالة
   - سيسأل عن:
     - نوع الخدمة
     - التاريخ والوقت المفضل
     - معلومات المريض

3. **إنشاء الموعد:**
   - بعد تأكيد التفاصيل
   - سيتم إنشاء الموعد تلقائياً
   - سيتم إرسال رسالة تأكيد

### السيناريو 2: مزامنة Google Calendar

1. **إنشاء موعد من WhatsApp:**
   - محادثة WhatsApp → إنشاء موعد

2. **المزامنة التلقائية:**
   - الموعد يظهر في Google Calendar تلقائياً
   - يمكن رؤيته في Calendar App

3. **التحديثات:**
   - أي تغيير في الموعد يتم مزامنته تلقائياً

### السيناريو 3: تذكير بالموعد

1. **إعداد تذكير:**
   - النظام يرسل تذكير تلقائي قبل الموعد بـ 24 ساعة
   - عبر WhatsApp

2. **رسالة التذكير:**
   - "تذكير: لديك موعد غداً في [الوقت]"

---

## ✅ Checklist التجربة الحقيقية

### إعدادات أساسية
- [ ] DeepSeek API Key موجود في `.env`
- [ ] Google Calendar OAuth credentials موجودة
- [ ] WhatsApp Channel مُعد (Test Mode أو Production)
- [ ] عيادة تم إنشاؤها
- [ ] Services تم إضافتها
- [ ] Operating Hours تم إعدادها
- [ ] Message Templates تم إضافتها

### اختبار الوظائف
- [ ] إرسال رسالة WhatsApp → استقبالها
- [ ] AI يرد على الرسائل تلقائياً
- [ ] إنشاء موعد من محادثة WhatsApp
- [ ] الموعد يظهر في Google Calendar
- [ ] تذكير بالموعد يتم إرساله تلقائياً
- [ ] إلغاء/تعديل موعد يعمل

---

## 🔧 حل المشاكل

### AI لا يرد
```bash
# تحقق من API Key
docker-compose exec web python manage.py shell -c "
from django.conf import settings
print('DEEPSEEK_API_KEY:', 'SET' if settings.DEEPSEEK_API_KEY else 'NOT SET')
"

# تحقق من logs
docker-compose logs worker | grep -i llm
```

### Google Calendar لا يعمل
```bash
# تحقق من OAuth credentials
docker-compose exec web python manage.py shell -c "
from django.conf import settings
print('GOOGLE_CLIENT_ID:', settings.GOOGLE_CLIENT_ID[:20] + '...' if settings.GOOGLE_CLIENT_ID else 'NOT SET')
"
```

### WhatsApp لا يرسل
```bash
# تحقق من Channel Account
docker-compose exec web python manage.py shell -c "
from apps.channels.models import ChannelAccount
print('WhatsApp Channels:', ChannelAccount.objects.filter(channel='whatsapp').count())
"

# تحقق من logs
docker-compose logs worker | grep -i whatsapp
```

---

## 📚 روابط مفيدة

- **DeepSeek**: https://platform.deepseek.com/
- **Google Cloud Console**: https://console.cloud.google.com/
- **Meta WhatsApp Business**: https://business.facebook.com/
- **Twilio WhatsApp**: https://www.twilio.com/whatsapp

---

## 🎯 الخلاصة

**للتجربة الحقيقية المتكاملة، تحتاج:**

1. ✅ **DeepSeek API Key** (5 دقائق)
2. ✅ **Google Calendar OAuth** (10-15 دقيقة)
3. ✅ **WhatsApp Channel** (Test Mode: 2 دقيقة | Production: 30 دقيقة)
4. ✅ **إنشاء عيادة** (5 دقائق)
5. ✅ **إعداد Services & Hours** (5 دقائق)

**الوقت الإجمالي:** ~30-60 دقيقة

**جاهز للبدء! 🚀**

