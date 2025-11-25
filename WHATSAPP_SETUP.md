# إعداد تكامل WhatsApp

## نظرة عامة

تم إضافة WhatsApp Service Layer الذي يدعم عدة providers:
- **Meta (Facebook) WhatsApp Business API**
- **Twilio WhatsApp**
- **Generic Provider** (للتكاملات المخصصة)

## الإعداد

### 1. إعداد Channel Account

لكل عيادة، يجب إنشاء `ChannelAccount` في قاعدة البيانات:

```python
from apps.channels.models import ChannelAccount
from apps.clinics.models import Clinic

clinic = Clinic.objects.get(slug="your-clinic-slug")

# للميتا (Facebook)
ChannelAccount.objects.create(
    clinic=clinic,
    channel="whatsapp",
    provider_name="meta",
    access_token="YOUR_META_ACCESS_TOKEN",
    metadata={
        "phone_number_id": "YOUR_PHONE_NUMBER_ID",
        "api_version": "v18.0",  # اختياري
    }
)

# لتويليو
ChannelAccount.objects.create(
    clinic=clinic,
    channel="whatsapp",
    provider_name="twilio",
    access_token="YOUR_ACCOUNT_SID",
    refresh_token="YOUR_AUTH_TOKEN",
    metadata={
        "from_number": "YOUR_TWILIO_WHATSAPP_NUMBER",
    }
)

# لمزود عام
ChannelAccount.objects.create(
    clinic=clinic,
    channel="whatsapp",
    provider_name="generic",
    access_token="YOUR_API_KEY",
    metadata={
        "api_url": "https://your-api.com/whatsapp",
    }
)
```

### 2. المتغيرات البيئية

#### للميتا (Facebook)
```env
WHATSAPP_DEFAULT_SENDER=your_phone_number_id
```

#### لتويليو
```env
WHATSAPP_DEFAULT_SENDER=whatsapp:+14155238886
```

#### للوضع التجريبي (Development)
```env
WHATSAPP_TEST_MODE=true
DJANGO_DEBUG=true
```

### 3. إعداد Meta WhatsApp Business API

1. إنشاء Facebook App في [Facebook Developers](https://developers.facebook.com/)
2. إضافة WhatsApp Business Product
3. الحصول على:
   - Access Token
   - Phone Number ID
4. إنشاء ChannelAccount كما هو موضح أعلاه

### 4. إعداد Twilio WhatsApp

1. إنشاء حساب في [Twilio](https://www.twilio.com/)
2. تفعيل WhatsApp Sandbox أو الحصول على رقم WhatsApp معتمد
3. الحصول على:
   - Account SID
   - Auth Token
   - WhatsApp Number
4. إنشاء ChannelAccount كما هو موضح أعلاه

## الاستخدام

### إرسال رسالة تلقائياً

النظام يرسل الرسائل تلقائياً من خلال `dispatch_outbox_messages` task:

```python
from apps.channels.services import enqueue_whatsapp_message

# إرسال رسالة session
enqueue_whatsapp_message(
    clinic_id=clinic.id,
    conversation=conversation,
    language="ar",
    message_body="مرحباً! كيف يمكنني مساعدتك؟",
)

# إرسال HSM template
enqueue_whatsapp_hsm(
    clinic_id=clinic.id,
    conversation=conversation,
    template_name="welcome_ar",
    language="ar",
    variables={"name": "أحمد"},
)
```

### إرسال رسالة يدوياً

```python
from apps.channels.whatsapp_service import get_whatsapp_service
from apps.channels.models import OutboxMessage

service = get_whatsapp_service()
outbox = OutboxMessage.objects.get(id=123)
result = service.send_message(outbox)

if result.success:
    print(f"Message sent! ID: {result.provider_message_id}")
else:
    print(f"Error: {result.error}")
```

## معالجة الأخطاء

النظام يتعامل تلقائياً مع:
- **Retryable errors**: Timeout, Network, Rate limits (429, 503, 502)
- **Permanent errors**: Invalid credentials, Invalid phone number
- **Exponential backoff**: إعادة المحاولة مع زيادة الوقت تدريجياً

## الوضع التجريبي (Test Mode)

في development، إذا لم يكن هناك ChannelAccount، النظام يستخدم وضع محاكاة:

```env
WHATSAPP_TEST_MODE=true
```

أو

```env
DJANGO_DEBUG=true
```

في هذا الوضع، الرسائل لا تُرسل فعلياً ولكن يتم تسجيلها كـ simulated.

## Webhooks

للاستقبال، استخدم endpoint الموجود:
- `POST /channels/whatsapp/webhook` - لاستقبال الرسائل الواردة
- `POST /channels/whatsapp/delivery` - لتحديثات حالة التسليم

## Troubleshooting

### خطأ: "No WhatsApp channel account configured"
- تأكد من إنشاء ChannelAccount للعيادة
- تحقق من `provider_name` و `metadata`

### خطأ: "Invalid access token"
- تحقق من صحة Access Token
- للميتا: تأكد من صلاحية Token
- لتويليو: تحقق من Account SID و Auth Token

### الرسائل لا تُرسل
- تحقق من logs في `apps.channels.whatsapp_service`
- تأكد من تشغيل Celery worker
- تحقق من `dispatch_outbox_messages` task

## ملاحظات

- النظام يدعم عدة providers في نفس الوقت (لكل عيادة provider مختلف)
- Provider يتم cache لتحسين الأداء
- جميع الأخطاء يتم تسجيلها في logs
- النظام يدعم retry تلقائي للأخطاء القابلة للإعادة

