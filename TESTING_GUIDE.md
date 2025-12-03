# 📘 دليل المشروع الشامل

## 📋 نظرة عامة

هذا الدليل الوحيد للمشروع يحتوي على:
- ✅ الإعدادات الحالية (ما تم إنجازه)
- ⚠️ ما يحتاج إلى إعداد
- 🚀 خطوات البدء في التجربة الحقيقية
- 🔧 أوامر مفيدة

---

## ✅ ما تم إعداده في `.env`

### 1. Environment Variables الأساسية
- ✅ `DJANGO_SECRET_KEY` - معرّف
- ✅ `POSTGRES_DB` - معرّف
- ✅ `POSTGRES_USER` - معرّف
- ✅ `POSTGRES_PASSWORD` - معرّف
- ✅ `REDIS_PASSWORD` - معرّف
- ✅ `ENCRYPTION_KEY` - معرّف

### 2. DeepSeek AI ✅
- ✅ `DEEPSEEK_API_KEY` - معرّف
- ✅ `DEEPSEEK_API_BASE` - https://api.deepseek.com
- **الحالة:** جاهز للرد التلقائي على رسائل WhatsApp

### 3. Google Calendar OAuth ✅
- ✅ `GOOGLE_CLIENT_ID` - معرّف
- ✅ `GOOGLE_CLIENT_SECRET` - معرّف
- ✅ `GOOGLE_REDIRECT_URI` - معرّف
- **الحالة:** جاهز لربط Google Calendar لكل عيادة

### 4. WhatsApp Cloud API (Meta) ✅
- ✅ WhatsApp Cloud API من Meta - جاهز
- ✅ `WHATSAPP_DEFAULT_SENDER` - معرّف (إن كان موجود)
- **الحالة:** جاهز لإضافة WhatsApp Channel لكل عيادة

---

## ⚠️ ما يحتاج إلى إعداد لكل عيادة

### 1️⃣ WhatsApp Channel (Meta Cloud API)

**التحقق:**
```bash
docker-compose exec web python manage.py shell -c "
from apps.channels.models import ChannelAccount, ChannelType
from apps.clinics.models import Clinic

clinics = Clinic.objects.all()
for clinic in clinics:
    account = ChannelAccount.objects.filter(
        clinic=clinic,
        channel=ChannelType.WHATSAPP
    ).first()
    if account:
        metadata = account.metadata or {}
        phone_id = metadata.get('phone_number_id', 'N/A')
        provider = account.provider_name
        print(f'✅ {clinic.name}: WhatsApp متصل ({provider}) - Phone ID: {phone_id}')
    else:
        print(f'❌ {clinic.name}: WhatsApp غير متصل')
"
```

**كيفية الإضافة:**
1. سجل دخول إلى Clinic Portal: `/c/[slug]/integrations`
2. اضغط "Add WhatsApp Channel"
3. اختر Provider: **Meta** أو **Facebook**
4. أدخل:
   - **Phone Number ID**: من Meta Business Manager
   - **Access Token**: من Meta Business Manager
5. احفظ

**ملاحظات:**
- كل عيادة تحتاج **Phone Number ID خاص** بها
- يمكن استخدام نفس Access Token لعدة عيادات إذا كانت من نفس Meta App
- Phone Number ID موجود في: Meta Business Manager → WhatsApp → Phone Numbers
- Access Token موجود في: Meta Business Manager → WhatsApp → API Setup

---

### 2️⃣ Google Calendar

**التحقق:**
```bash
docker-compose exec web python manage.py shell -c "
from apps.calendars.models import GoogleCredential
from apps.clinics.models import Clinic

clinics = Clinic.objects.all()
for clinic in clinics:
    cred = GoogleCredential.objects.filter(clinic=clinic).first()
    if cred:
        print(f'✅ {clinic.name}: Google Calendar متصل ({cred.account_email})')
    else:
        print(f'❌ {clinic.name}: Google Calendar غير متصل')
"
```

**كيفية الإضافة:**
1. سجل دخول إلى Clinic Portal: `/c/[slug]/integrations`
2. اضغط "Connect Google Calendar"
3. سجل دخول بحساب Google
4. وافق على الصلاحيات

**ملاحظات:**
- يمكن استخدام نفس حساب Google لعدة عيادات
- أو حساب Google خاص لكل عيادة

---

### 3️⃣ Services و Operating Hours

**التحقق:**
```bash
docker-compose exec web python manage.py shell -c "
from apps.clinics.models import Clinic
from apps.services.models import ServiceHours

clinics = Clinic.objects.all()
for clinic in clinics:
    services_count = clinic.services.filter(is_active=True).count()
    hours_count = ServiceHours.objects.filter(service__clinic=clinic).count()
    print(f'{clinic.name}: Services={services_count}, Hours={hours_count}')
"
```

**كيفية الإضافة:**
1. سجل دخول إلى Clinic Portal: `/c/[slug]/services`
2. اضغط "Add Service"
3. أضف Services (مثال: Cleaning, Checkup, Consultation)
4. حدد Operating Hours لكل Service

---

### 4️⃣ Message Templates

**التحقق:**
```bash
docker-compose exec web python manage.py shell -c "
from apps.channels.models import HSMTemplate, HSMTemplateStatus
from apps.clinics.models import Clinic

clinics = Clinic.objects.all()
for clinic in clinics:
    templates_count = HSMTemplate.objects.filter(
        clinic=clinic,
        status=HSMTemplateStatus.APPROVED
    ).count()
    print(f'{clinic.name}: {templates_count} قوالب معتمدة')
"
```

**كيفية الإضافة:**
1. سجل دخول إلى Clinic Portal: `/c/[slug]/templates`
2. اضغط "Add Template"
3. أنشئ قوالب مثل:
   - `greet`: رسالة الترحيب
   - `confirm`: تأكيد الموعد
   - `remind`: تذكير بالموعد
   - `cancel`: إلغاء الموعد

---

## 🚀 خطوات البدء في التجربة الحقيقية

### الخطوة 1: التحقق من الإعدادات
```bash
docker-compose exec web python manage.py check_setup
```

### الخطوة 2: التحقق من العيادات
```bash
docker-compose exec web python manage.py shell -c "
from apps.clinics.models import Clinic
clinics = Clinic.objects.all()
print(f'عدد العيادات: {clinics.count()}')
for clinic in clinics:
    print(f'  - {clinic.name} ({clinic.slug})')
"
```

### الخطوة 3: إعداد عيادة (إن لم تكن موجودة)
1. سجل دخول كـ HQ Admin: `/hq`
2. اضغط "New Tenant"
3. املأ بيانات العيادة
4. احفظ

### الخطوة 4: إعداد العيادة الكامل
1. سجل دخول كـ Clinic Owner: `/c/[slug]`
2. اذهب إلى `/c/[slug]/onboarding`
3. اكمل Setup Checklist:
   - ✅ أضف Services
   - ✅ حدد Operating Hours
   - ✅ أضف WhatsApp Channel (Meta Cloud API)
   - ✅ اربط Google Calendar
   - ✅ أضف Message Templates

---

## 🧪 اختبار التجربة الحقيقية

### 1. اختبار WhatsApp
1. أرسل رسالة WhatsApp إلى رقم العيادة (Phone Number ID)
2. تحقق من استقبال الرسالة في النظام
3. تحقق من الرد التلقائي من AI (DeepSeek)
4. اختبر إنشاء موعد من المحادثة

### 2. اختبار Google Calendar
1. أنشئ موعد من WhatsApp
2. تحقق من ظهوره في Google Calendar
3. اختبر التعديل والإلغاء

### 3. اختبار AI (DeepSeek)
1. أرسل رسالة معقدة
2. تحقق من فهم AI للرسالة
3. تحقق من الرد المناسب

---

## 🔧 أوامر مفيدة

### التحقق الشامل من الإعدادات:
```bash
docker-compose exec web python manage.py check_setup
```

### التحقق من عيادة معينة:
```bash
docker-compose exec web python manage.py shell -c "
from apps.clinics.models import Clinic
from apps.channels.models import ChannelAccount, ChannelType
from apps.calendars.models import GoogleCredential

clinic = Clinic.objects.get(slug='your-clinic-slug')
print(f'Clinic: {clinic.name}')

# WhatsApp
whatsapp = ChannelAccount.objects.filter(clinic=clinic, channel=ChannelType.WHATSAPP).first()
if whatsapp:
    metadata = whatsapp.metadata or {}
    print(f'WhatsApp: ✅ ({whatsapp.provider_name}) - Phone ID: {metadata.get(\"phone_number_id\", \"N/A\")}')
else:
    print('WhatsApp: ❌')

# Google Calendar
google = GoogleCredential.objects.filter(clinic=clinic).first()
if google:
    print(f'Google Calendar: ✅ ({google.account_email})')
else:
    print('Google Calendar: ❌')
"
```

### إعادة تشغيل الخدمات:
```bash
docker-compose restart web worker
```

### تشغيل المشروع:
```bash
docker-compose up -d
```

### إيقاف المشروع:
```bash
docker-compose down
```

### عرض Logs:
```bash
docker-compose logs -f web
docker-compose logs -f worker
```

---

## 📋 Checklist للتجربة الحقيقية

### على مستوى النظام (.env):
- [x] ✅ DeepSeek API Key
- [x] ✅ Google Calendar OAuth (Client ID, Secret, Redirect URI)
- [x] ✅ WhatsApp Cloud API (Meta) - جاهز

### لكل عيادة:
- [ ] ✅ Services موجودة
- [ ] ✅ Operating Hours معرّفة
- [ ] ✅ WhatsApp Channel متصل (Meta Cloud API)
  - [ ] Phone Number ID معرّف
  - [ ] Access Token معرّف
- [ ] ✅ Google Calendar مرتبط
- [ ] ✅ Message Templates موجودة

---

## 🎯 الهدف النهائي

**كل عيادة لها رقم WhatsApp خاص بها تتحدث مع عملائها**

- ✅ كل عيادة → WhatsApp Channel (Meta Cloud API)
- ✅ كل عيادة → رقم WhatsApp خاص (Phone Number ID)
- ✅ AI (DeepSeek) → يرد تلقائياً على الرسائل
- ✅ Google Calendar → مزامنة المواعيد تلقائياً
- ✅ كل عيادة مستقلة تماماً

---

## 📚 روابط مفيدة

- **DeepSeek**: https://platform.deepseek.com/
- **Google Cloud Console**: https://console.cloud.google.com/
- **Meta WhatsApp Business**: https://business.facebook.com/
- **Twilio WhatsApp**: https://www.twilio.com/whatsapp

---

## ⚠️ ملاحظات مهمة

### 1. WhatsApp Cloud API (Meta)
- **Phone Number ID**: كل عيادة تحتاج Phone Number ID خاص (أو نفس ID إذا كان نفس الرقم)
- **Access Token**: يمكن استخدام نفس Token لعدة عيادات إذا كانت من نفس Meta App
- **API Version**: افتراضي `v18.0` (يمكن تغييره في metadata)

### 2. DeepSeek AI
- **مشترك**: نفس API Key لجميع العيادات
- **لكل عيادة**: يمكن تخصيص الردود عبر Knowledge Base

### 3. Google Calendar
- **OAuth Credentials**: مشتركة لجميع العيادات (من `.env`)
- **حساب Google**: يمكن استخدام نفس الحساب أو حساب خاص لكل عيادة

---

## 🚀 جاهز للبدء!

**الخطوات التالية:**
1. تحقق من وجود عيادة: `docker-compose exec web python manage.py check_setup`
2. أضف WhatsApp Channel لكل عيادة من `/c/[slug]/integrations`
3. اربط Google Calendar من `/c/[slug]/integrations`
4. أضف Services و Hours من `/c/[slug]/services`
5. أضف Templates من `/c/[slug]/templates`
6. اختبر إرسال رسالة WhatsApp!

**كل شيء جاهز! 🎉**
