# دليل شامل - AI Appointment Backend

## 📋 نظرة عامة

نظام حجز مواعيد ذكي لـ العيادات (خاصة عيادات الأسنان) يعتمد على الذكاء الاصطناعي. يتفاعل مع المرضى عبر واتساب، ويدير المواعيد، ويتكامل مع Google Calendar.

## 🏗️ البنية المعمارية

### Backend (Django)
- **إدارة العيادات:** بيانات العيادة، الخدمات، ساعات العمل
- **إدارة المرضى:** ملفات المرضى، الملاحظات
- **إدارة المواعيد:** حجز، تأكيد، إلغاء، إعادة جدولة
- **المحادثات:** تتبع المحادثات مع المرضى عبر واتساب
- **القنوات:** تكامل واتساب مع HSM Templates
- **التقويم:** تكامل Google Calendar
- **الحوار:** FSM لإدارة تدفق المحادثة
- **LLM:** استخدام DeepSeek للإجابة على الأسئلة مع RAG
- **المعرفة:** قاعدة معرفة للعيادات (KB)
- **العمال:** مهام Celery للتذكيرات والمزامنة

### Frontend (Next.js)
- لوحة تحكم للعيادات: `/c/[slug]/dashboard`
- إدارة المحادثات: عرض والرد على المحادثات
- إدارة المواعيد: عرض وإدارة المواعيد
- إعدادات العيادة: الخدمات، ساعات العمل، القوالب
- لوحة HQ: إدارة متعددة المستأجرين
- جلسات الدعم: إمكانية انتحال هوية العيادة للدعم

## 🔄 التدفق الرئيسي

### 1. استقبال عميل جديد
- وصول رسالة واتساب أو webhook
- إنشاء/تحديث ملف المريض
- بدء محادثة جديدة

### 2. معالجة الرسالة
- تطبيع النص
- كشف النية (book, confirm, cancel, reschedule)
- إذا كانت النية واضحة → الانتقال في FSM
- إذا كانت غير واضحة → استخدام LLM مع RAG

### 3. حجز الموعد
- عند نية "book":
  - البحث عن مواعيد متاحة
  - التحقق من Google Calendar
  - عرض خيارات للمريض
- عند التأكيد:
  - إنشاء الموعد
  - مزامنة مع Google Calendar
  - إرسال رسالة تأكيد

### 4. المهام الخلفية (Celery)
- إرسال تذكيرات (24 ساعة و2 ساعة قبل الموعد)
- إعادة محاولة مزامنة Google Calendar
- إرسال رسائل Outbox
- تنظيف البيانات القديمة (Retention)

## 🚀 البدء السريع

### Development Setup

```bash
# 1. Environment
cp env.example .env
# Edit .env with required values

# 2. Database
createdb ai_appointment
psql -U postgres -c "CREATE EXTENSION vector;" -d ai_appointment

# 3. Backend
python -m venv bot_venv
source bot_venv/bin/activate  # Linux/Mac
# bot_venv\Scripts\activate  # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
python manage.py runserver

# 4. Frontend
cd frontend
npm install
npm run dev
```

### Docker Development

```bash
make dev-up
make dev-down
```

## 📦 النشر للإنتاج

### المتطلبات
- Docker & Docker Compose
- PostgreSQL 12+ (مع pgvector)
- Redis 6+
- Domain مع SSL certificate

### خطوات النشر

#### 1. إعداد Environment Variables
```bash
cp env.example .env
```

**المتغيرات الحرجة:**
- `DJANGO_SECRET_KEY` - مفتاح قوي (50+ حرف)
- `DJANGO_DEBUG=false` - **يجب false في الإنتاج**
- `DJANGO_ALLOWED_HOSTS` - domains الإنتاج
- `POSTGRES_*` - إعدادات قاعدة البيانات
- `CELERY_BROKER_URL` - Redis URL
- `DEEPSEEK_API_KEY` - مفتاح DeepSeek
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` - Google OAuth
- `LEAD_WEBHOOK_SECRET` - سر webhook

#### 2. إعداد قاعدة البيانات
```bash
psql -U postgres
CREATE DATABASE ai_appointment;
CREATE USER ai_user WITH PASSWORD 'strong-password';
GRANT ALL PRIVILEGES ON DATABASE ai_appointment TO ai_user;
\c ai_appointment
CREATE EXTENSION vector;
```

#### 3. إعداد WhatsApp Provider

**للميتا (Facebook):**
```python
from apps.channels.models import ChannelAccount
from apps.clinics.models import Clinic

clinic = Clinic.objects.get(slug="your-clinic")
ChannelAccount.objects.create(
    clinic=clinic,
    channel="whatsapp",
    provider_name="meta",
    access_token="YOUR_META_ACCESS_TOKEN",
    metadata={"phone_number_id": "YOUR_PHONE_NUMBER_ID"}
)
```

**لتويليو:**
```python
ChannelAccount.objects.create(
    clinic=clinic,
    channel="whatsapp",
    provider_name="twilio",
    access_token="YOUR_ACCOUNT_SID",
    refresh_token="YOUR_AUTH_TOKEN",
    metadata={"from_number": "whatsapp:+14155238886"}
)
```

**Test Mode:** في development، استخدم `WHATSAPP_TEST_MODE=true` في `.env`

#### 4. النشر
```bash
# بناء images
docker-compose -f docker-compose.prod.yml build

# تشغيل الخدمات
docker-compose -f docker-compose.prod.yml up -d

# التحقق
curl http://localhost/health/
curl http://localhost/ready/
```

#### 5. إعداد SSL (Let's Encrypt)
```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d api.yourdomain.com
```

## 🔧 الصيانة

### Health Checks
```bash
./scripts/health_check.sh
# أو
curl http://localhost/health/
curl http://localhost/ready/
```

### Database Backup
```bash
./scripts/backup_db.sh
# أو يدوياً
pg_dump -U ai_user ai_appointment > backup.sql
```

### Logs
```bash
# جميع الخدمات
docker-compose -f docker-compose.prod.yml logs -f

# خدمة محددة
docker-compose -f docker-compose.prod.yml logs -f web
docker-compose -f docker-compose.prod.yml logs -f worker
```

### Updates
```bash
git pull
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.prod.yml exec web python manage.py migrate
```

## 📊 حالة المتطلبات

### ✅ جاهز تماماً
- Healthz endpoints (`/health/`, `/ready/`)
- Docker production setup (Frontend + Backend + Nginx)
- WhatsApp Service Layer (Meta/Twilio/Generic)
- Database backup script
- Retention job (يعمل تلقائياً كل 24 ساعة)
- Security settings (HTTPS, HSTS, Security Headers)
- Logging configuration

### ⚠️ يحتاج إعداد يدوي
- **مفاتيح API:** DeepSeek, WhatsApp Provider, Google OAuth
- **SSL Certificates:** Let's Encrypt setup
- **ChannelAccount:** إنشاء في قاعدة البيانات

### 📋 تحسينات اختيارية (لاحقاً)
- AuditLog UI في HQ
- توحيد رسائل الأخطاء (AR/EN)
- تحسين Template Catalog
- Playwright tests
- Buffers & Holidays
- DST/Timezones edge cases

## 🐛 Troubleshooting

### Health check fails
```bash
# تحقق من logs
docker-compose -f docker-compose.prod.yml logs web

# تحقق من database
docker-compose -f docker-compose.prod.yml exec web python manage.py dbshell
```

### WhatsApp messages not sending
```bash
# تحقق من ChannelAccount
docker-compose -f docker-compose.prod.yml exec web python manage.py shell
>>> from apps.channels.models import ChannelAccount
>>> ChannelAccount.objects.all()

# تحقق من worker logs
docker-compose -f docker-compose.prod.yml logs worker
```

### Static files not loading
```bash
docker-compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

## 📝 ملاحظات مهمة

1. **WhatsApp Integration:**
   - يجب إنشاء `ChannelAccount` لكل عيادة
   - في development، استخدم `WHATSAPP_TEST_MODE=true`
   - النظام يدعم عدة providers في نفس الوقت

2. **Security:**
   - إعدادات الأمان تعمل فقط عندما `DEBUG=False`
   - تأكد من تعيين `SECURE_SSL_REDIRECT` حسب بيئتك
   - CORS غير مطلوب (Frontend يستخدم proxy)

3. **Logging:**
   - Logs تُكتب في `logs/django.log`
   - تأكد من إنشاء مجلد `logs/` قبل النشر
   - في Docker، استخدم volumes لل logs

4. **Retention:**
   - Retention job يعمل تلقائياً كل 24 ساعة
   - يحذف البيانات الأقدم من `DATA_RETENTION_DAYS` (default: 30)

5. **Backups:**
   - Backup script يحتفظ بـ 7 أيام من backups
   - أضف cron job للـ backups اليومية

## 🎯 Checklist النشر

### قبل النشر:
- [ ] `.env` file مع جميع المتغيرات
- [ ] `DJANGO_SECRET_KEY` قوي
- [ ] `DJANGO_DEBUG=false`
- [ ] قاعدة البيانات منشأة
- [ ] WhatsApp ChannelAccount منشأ
- [ ] DeepSeek API key محددة
- [ ] Google OAuth credentials محددة

### بعد النشر:
- [ ] Health checks تعمل
- [ ] SSL certificates مثبتة
- [ ] Backups تعمل
- [ ] Logs يتم جمعها
- [ ] Monitoring setup

## 📞 الدعم

- Health checks: `/health/`, `/ready/`
- Metrics: `/metrics/summary`
- HQ portal: `/hq` (requires SUPERADMIN)
- Scripts: `scripts/` directory

