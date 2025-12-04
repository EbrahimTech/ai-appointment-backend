# 📘 دليل المشروع الشامل

## 📋 نظرة عامة

هذا الدليل الوحيد للمشروع يحتوي على:
- ✅ الإعدادات الحالية (ما تم إنجازه)
- ⚠️ ما يحتاج إلى إعداد
- 🚀 خطوات البدء في التجربة الحقيقية
- 🔧 أوامر مفيدة

---

## 🎯 الخطوات المتبقية للانطلاق

### 📌 الوضع الحالي

**ما تم إنجازه:**
- ✅ Services: موجودة (2 خدمة)
- ✅ Operating Hours: معرّفة (15 ساعة عمل)
- ✅ Message Templates: موجودة (10 قوالب)
- ✅ DeepSeek AI: جاهز
- ✅ Google Calendar OAuth: معرّف في `.env`
- ✅ Google Calendar: متصل للعيادة (Status: OK)
- ✅ WhatsApp Channel: تم إضافته (Provider: meta, Phone Number ID موجود)

**ما تبقى للاختبار الكامل:**

#### ✅ الخطوة 1: إضافة رقم WhatsApp إلى Allowlist (مهم!)
**المشكلة:** عند النقر على "Send Test" يظهر خطأ: "This phone number is not in the sandbox allowlist"

**الحل:**
1. افتح ملف `.env`
2. ابحث عن `WHATSAPP_TEST_ALLOWLIST`
3. أضف رقمك بالتنسيق التالي:
   ```env
   WHATSAPP_TEST_ALLOWLIST={"prime-dental":["+905356027135"]}
   ```
   أو لجميع العيادات:
   ```env
   WHATSAPP_TEST_ALLOWLIST={"*":["+905356027135"]}
   ```
4. أعد تشغيل الـ backend:
   ```bash
   docker-compose restart web
   ```

#### ✅ الخطوة 2: تشغيل Migration (مهم!)
```bash
docker-compose exec web python manage.py migrate channels
```
**السبب:** زيادة طول `access_token` من 255 إلى 1000 حرف

#### ✅ الخطوة 3: إعداد WhatsApp Webhook في Meta
- للاختبار المحلي: استخدم **ngrok** لعرض webhook
- للإنتاج: استخدم domain حقيقي مع SSL
- Webhook URL: `https://your-domain.com/channels/whatsapp/webhook?clinic=prime-dental`

#### ✅ الخطوة 4: الاختبار الفعلي
- اختبار الإرسال: استخدم "Send Test" من صفحة Integrations (بعد إضافة الرقم)
- اختبار الاستقبال: أرسل رسالة WhatsApp إلى رقم العيادة
- اختبار حجز موعد: أرسل "أريد حجز موعد" من WhatsApp
- التحقق من Google Calendar: تأكد من ظهور الموعد بعد الحجز

---

### الخطوة 1: حل مشكلة Google Calendar OAuth

#### المشكلة:
عند محاولة ربط Google Calendar، تظهر رسالة:
> "access_denied: لم يكمل تطبيق AI Appointment Setter عملية التحقق"

#### الحل: إضافة Test Users في Google Cloud Console

1. اذهب إلى: https://console.cloud.google.com/
2. اختر المشروع الخاص بك
3. اذهب إلى: **APIs & Services** → **OAuth consent screen**
4. تأكد من أن **Publishing status** = **Testing**
5. اذهب إلى قسم **Test users** (في نفس الصفحة)
6. اضغط **+ ADD USERS**
7. أضف البريد الإلكتروني: `ebrahimtech1@gmail.com`
8. أضف أي حسابات Google أخرى ستستخدمها للعيادات
9. اضغط **ADD** ثم **SAVE**

**⚠️ مهم:** يجب إضافة جميع الحسابات التي ستستخدمها قبل محاولة الربط.

#### بعد إضافة Test Users:

1. اذهب إلى: `/c/prime-dental/integrations`
2. اضغط **"Connect Google Calendar"**
3. سجل دخول بحساب Google (يجب أن يكون في قائمة Test Users)
4. وافق على الصلاحيات المطلوبة
5. سيتم إرجاعك تلقائياً إلى النظام

**التحقق:**
```bash
docker-compose exec web python manage.py shell -c "
from apps.calendars.models import GoogleCredential
from apps.clinics.models import Clinic

clinic = Clinic.objects.get(slug='prime-dental')
cred = GoogleCredential.objects.filter(clinic=clinic).first()
if cred:
    print(f'✅ Google Calendar متصل')
    print(f'   Account: {cred.account_email}')
else:
    print('❌ Google Calendar غير متصل')
"
```

---

### الخطوة 2: إضافة WhatsApp Channel (Meta Cloud API)

#### 2.1 الحصول على بيانات WhatsApp من Meta

**من Meta Business Manager:**
1. اذهب إلى: https://business.facebook.com/
2. اختر **WhatsApp** → **API Setup**
3. انسخ:
   - **Phone Number ID** (مثال: `123456789012345`)
   - **Access Token** (مثال: `EAAxxxxxxxxxxxxx`)

**ملاحظة:** إذا لم يكن لديك WhatsApp Business Account:
- سجل في Meta Business Manager
- أنشئ WhatsApp Business App
- احصل على Phone Number ID و Access Token

#### 2.2 إضافة WhatsApp Channel في النظام

1. من Clinic Portal: `/c/prime-dental/integrations`
2. في قسم **WhatsApp Integration**، اضغط **"Add WhatsApp Channel"** (أو **"Update WhatsApp Channel"** إذا كان موجود)
3. املأ البيانات التالية:
   - **Provider**: اختر **Meta** (أو Facebook)
   - **Phone Number ID**: أدخل Phone Number ID من Meta Business Manager (مثال: `123456789012345`)
   - **Access Token**: أدخل Access Token من Meta Business Manager (مثال: `EAAxxxxxxxxxxxxx`)
   - **Business Account ID**: (اختياري) إذا كان لديك Business Account ID
   - **API Version**: اتركه `v18.0` (أو غيره حسب إعداداتك)
4. اضغط **"حفظ"**

**⚠️ ملاحظة:** Access Token سيتم إخفاؤه بعد الحفظ لأسباب أمنية.

**التحقق:**
```bash
docker-compose exec web python manage.py shell -c "
from apps.channels.models import ChannelAccount, ChannelType
from apps.clinics.models import Clinic

clinic = Clinic.objects.get(slug='prime-dental')
account = ChannelAccount.objects.filter(
    clinic=clinic,
    channel=ChannelType.WHATSAPP
).first()
if account:
    metadata = account.metadata or {}
    print(f'✅ WhatsApp متصل')
    print(f'   Provider: {account.provider_name}')
    print(f'   Phone ID: {metadata.get(\"phone_number_id\", \"N/A\")}')
else:
    print('❌ WhatsApp غير متصل')
"
```

**النتيجة:**
- ✅ WhatsApp Channel متصل
- ✅ يمكن استقبال وإرسال رسائل WhatsApp

---

### الخطوة 3: تشغيل Migration (مهم!)

**قبل الاختبار، يجب تشغيل migration لزيادة طول `access_token`:**

```bash
docker-compose exec web python manage.py migrate channels
```

**النتيجة المتوقعة:**
```
Running migrations:
  Applying channels.0003_increase_access_token_length... OK
```

**⚠️ مهم:** إذا لم يتم تشغيل هذه Migration، قد تواجه خطأ عند حفظ Access Token الطويل.

---

### الخطوة 4: إعداد WhatsApp Webhook في Meta (للاستقبال)

**للاستقبال رسائل WhatsApp، يجب إعداد Webhook في Meta:**

#### 4.1 للاختبار المحلي (باستخدام ngrok):

1. **قم بتثبيت ngrok:**
   ```bash
   # Windows: قم بتحميل ngrok من https://ngrok.com/
   # أو استخدم Chocolatey: choco install ngrok
   ```

2. **شغّل ngrok:**
   ```bash
   ngrok http 8000
   ```
   ستحصل على URL مثل: `https://abc123.ngrok.io`

3. **في Meta Business Manager:**
   - اذهب إلى: https://business.facebook.com/
   - اختر **WhatsApp** → **Configuration** → **Webhooks**
   - اضغط **Edit** أو **Add Webhook**
   - أدخل **Webhook URL**:
     ```
     https://abc123.ngrok.io/channels/whatsapp/webhook?clinic=prime-dental
     ```
   - أدخل **Verify Token** (يمكنك اختيار أي token، مثال: `my_verify_token`)
   - اختر **Events**:
     - ✅ `messages` (للاستقبال)
     - ✅ `message_deliveries` (للتأكيد)
   - اضغط **Save**

#### 4.2 للإنتاج (مع Domain حقيقي):

1. **تأكد من أن Domain يعمل مع SSL (HTTPS)**
2. **في Meta Business Manager:**
   - أدخل **Webhook URL**:
     ```
     https://your-domain.com/channels/whatsapp/webhook?clinic=prime-dental
     ```
   - باقي الخطوات نفس الاختبار المحلي

**⚠️ ملاحظات مهمة:**
- **Webhook URL يجب أن يكون HTTPS** (Meta يتطلب SSL)
- **Query Parameter `clinic=prime-dental`** ضروري لتحديد العيادة
- **Verify Token** يمكنك اختيار أي قيمة (Meta سيتحقق منه)
- **للاختبار المحلي:** استخدم ngrok أو Cloudflare Tunnel
- **للإنتاج:** استخدم domain حقيقي مع SSL certificate

---

### الخطوة 5: التحقق النهائي من إعداد العيادة

```bash
# تحقق شامل من العيادة
docker-compose exec web python manage.py check_setup
```

**النتيجة المتوقعة:**
```
🏥 العيادة: Prime Dental Clinic (prime-dental)

✅ Services: 2 خدمة
✅ Operating Hours: 15 ساعة عمل
✅ Message Templates: 10 قالب
✅ WhatsApp: متصل (meta)
✅ Google Calendar: متصل (ebrahimtech1@gmail.com)

🎉 العيادة جاهزة بالكامل!
```

---

### الخطوة 6: الاختبار النهائي والانطلاق

#### 6.1 اختبار WhatsApp (إرسال واستقبال)

**أ) اختبار الإرسال (Sandbox):**

**⚠️ مهم: قبل الاختبار، يجب إضافة رقمك إلى `WHATSAPP_TEST_ALLOWLIST` في `.env`:**

1. **افتح ملف `.env`**
2. **ابحث عن `WHATSAPP_TEST_ALLOWLIST`**
3. **أضف رقمك بالتنسيق التالي:**
   ```env
   WHATSAPP_TEST_ALLOWLIST={"prime-dental":["+905356027135"],"*":["+15555550123"]}
   ```
   أو لجميع العيادات:
   ```env
   WHATSAPP_TEST_ALLOWLIST={"*":["+905356027135","+15555550123"]}
   ```
4. **أعد تشغيل الـ backend:**
   ```bash
   docker-compose restart web
   ```

**بعد إضافة الرقم:**
1. من Clinic Portal: `/c/prime-dental/integrations`
2. في قسم **WhatsApp Integration**، استخدم **"Send Test"**
3. أدخل:
   - **Sandbox Phone**: `+905356027135` (أو أي رقم في القائمة)
   - **Template Key**: `greet`
   - **Variables**: `{"first_name":"Test"}`
     ⚠️ **مهم:** قالب `greet` يحتاج `first_name` وليس `name`
4. اضغط **"Send Test"**
5. **النتيجة المتوقعة:**
   - ✅ الرسالة تُرسل بنجاح
   - ✅ Status يصبح "SENT" أو "DELIVERED"

**⚠️ إذا ظهر "DOWN" و "FAILED":**

**التفسير:**
- **"DOWN"** = حالة WhatsApp Integration (القناة العامة)
  - يظهر عندما يكون آخر إرسال فاشلاً
  - سيصبح `OK` بعد نجاح إرسال جديد
- **"FAILED"** = حالة الرسالة الفردية
  - الرسالة القديمة فشلت قبل التعديلات
  - لن تُعالج تلقائياً

**⚠️ إذا ظهر خطأ "Session has expired" أو "Access Token expired":**

**المشكلة:** Access Token من Meta منتهي الصلاحية.

**الحل:**
1. **احصل على Access Token جديد من Meta Business Manager:**
   - اذهب إلى: https://business.facebook.com/
   - اختر **WhatsApp** → **API Setup**
   - انسخ **Access Token** الجديد

2. **حدّث WhatsApp Channel في النظام:**
   - اذهب إلى `/c/prime-dental/integrations`
   - اضغط **"Update WhatsApp Channel"**
   - أدخل **Access Token** الجديد
   - احفظ

3. **أرسل رسالة اختبار جديدة:**
   - اضغط "Send Test" مرة أخرى
   - انتظر 10-30 ثانية
   - اضغط "Refresh Status"
   - يجب أن تتغير الحالة من `FAILED` إلى `SENT` أو `DELIVERED`
   - يجب أن تتغير حالة Integration من `DOWN` إلى `OK`

**ملاحظة:** Access Token من Meta ينتهي بعد فترة (عادة 60 يوم). يجب تحديثه دورياً.

**إذا استمرت المشكلة:**
1. **تحقق من حالة Worker:**
   ```bash
   docker-compose ps worker beat
   ```

2. **مراقبة Logs:**
   ```bash
   # Logs للـ Worker
   docker-compose logs -f worker
   
   # Logs للـ Beat (Scheduler)
   docker-compose logs -f beat
   ```

3. **تحقق من الإعدادات:**
   - `Access Token` صحيح في WhatsApp Channel
   - `Phone Number ID` صحيح
   - الرقم في `WHATSAPP_TEST_ALLOWLIST`

**ملاحظة:** لكل قالب متغيرات مختلفة:
- `greet` → `{"first_name":"Test"}`
- `session_clarify` → `{"name":"Test"}`
- `slot_offer` → `{"slot1":"10:00","slot2":"14:00"}`
- `confirm_booking` → `{"dt":"2024-01-15 10:00"}`

**ب) اختبار الاستقبال (Webhook):**
1. أرسل رسالة WhatsApp إلى رقم العيادة (Phone Number ID) من هاتفك
2. **النتيجة المتوقعة:**
   - ✅ استقبال الرسالة في النظام (من `/c/prime-dental/conversations`)
   - ✅ رد تلقائي من AI (DeepSeek)
   - ✅ AI يفهم الرسالة ويقترح المواعيد

#### 6.2 اختبار حجز موعد كامل

1. من WhatsApp، أرسل: "أريد حجز موعد" أو "I want to book an appointment"
2. **النتيجة المتوقعة:**
   - ✅ AI يعرض الخدمات المتاحة
   - ✅ AI يعرض المواعيد المتاحة
   - ✅ يمكنك اختيار موعد
   - ✅ يتم تأكيد الموعد
   - ✅ رسالة تأكيد تُرسل عبر WhatsApp

#### 6.3 اختبار Google Calendar

1. بعد حجز الموعد، افتح Google Calendar
2. **النتيجة المتوقعة:**
   - ✅ الموعد ظاهر في Google Calendar
   - ✅ التاريخ والوقت صحيحان
   - ✅ اسم الخدمة موجود
   - ✅ اسم المريض موجود (إن كان متوفر)

#### 6.4 مراقبة النظام

**عرض Logs:**
```bash
# Logs للـ Backend
docker-compose logs -f web

# Logs للـ Worker (Celery)
docker-compose logs -f worker
```

**مراقبة المحادثات:**
- من Clinic Portal: `/c/prime-dental/conversations`
- يمكنك رؤية جميع المحادثات مع العملاء

**مراقبة المواعيد:**
- من Clinic Portal: `/c/prime-dental/appointments`
- يمكنك رؤية جميع المواعيد وإدارتها

---

## 🎉 الانطلاق! العيادة جاهزة

**الآن يمكنك:**
- ✅ استقبال رسائل WhatsApp من العملاء
- ✅ الرد التلقائي عبر AI (DeepSeek)
- ✅ حجز المواعيد تلقائياً
- ✅ المزامنة مع Google Calendar
- ✅ إدارة المواعيد من Clinic Portal

**الخطوة التالية:** 
- كرر الخطوات لإضافة عيادات أخرى
- راقب الأداء من `/c/prime-dental/conversations`
- راقب المواعيد من `/c/prime-dental/appointments`

**🚀 المشروع جاهز للاستخدام الحقيقي!**

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
