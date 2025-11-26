# دليل تشغيل المشروع للاختبار

## 📋 نظرة عامة

هذا الدليل يوضح كيفية تشغيل المشروع بشكل كامل للاختبار، بما في ذلك:
- Backend (Django)
- Frontend (Next.js)
- Database (PostgreSQL)
- Redis
- Celery Worker & Beat

---

## 🚀 الطريقة الأولى: Docker Compose (الأسهل)

### المتطلبات
- Docker Desktop مثبت ومشغل
- Git Bash (لأوامر make على Windows)

### الخطوات

#### 1. إعداد ملف البيئة

```bash
# إنشاء ملف .env من القيم الافتراضية
# يمكنك نسخ هذا الملف وتعديله حسب الحاجة
```

**ملف `.env` أساسي للاختبار:**

```env
# Django
DJANGO_SECRET_KEY=test-secret-key-change-in-production
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
POSTGRES_DB=ai_appointment
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=change-me

# Redis
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# DeepSeek LLM (اختياري للاختبار)
DEEPSEEK_API_KEY=your-api-key-here

# Google Calendar (اختياري للاختبار)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret

# WhatsApp (اختياري - يمكن استخدام test mode)
WHATSAPP_TEST_MODE=true

# Frontend (يجب أن يكون نفس URL الذي يعمل عليه Backend)
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

#### 2. تشغيل Backend Services

```bash
# تشغيل جميع الخدمات (DB, Redis, Web, Worker, Beat)
make dev-up

# أو مباشرة:
docker-compose up -d
```

**التحقق من الحالة:**
```bash
docker-compose ps
```

يجب أن ترى:
- `db` - PostgreSQL
- `redis` - Redis
- `web` - Django server
- `worker` - Celery worker
- `beat` - Celery beat

#### 3. إعداد قاعدة البيانات

```bash
# تشغيل migrations
make migrate

# أو مباشرة:
docker-compose exec web python manage.py migrate

# إضافة بيانات تجريبية
make seed

# أو مباشرة:
docker-compose exec web python manage.py seed_data
```

#### 4. إنشاء مستخدم HQ للاختبار (اختياري)

**✅ ملاحظة مهمة**: `seed_data` command ينشئ تلقائياً مستخدم HQ:
- **Email**: `admin@example.com`
- **Password**: `Admin!234`
- **Role**: `SUPERADMIN`

يمكنك استخدام هذا المستخدم مباشرة بعد `make seed`!

**إذا أردت إنشاء مستخدم إضافي:**

```bash
# الدخول إلى shell
make dev-shell

# أو مباشرة:
docker-compose exec web bash

# داخل shell:
python manage.py shell
```

```python
from django.contrib.auth.models import User
from apps.accounts.models import StaffAccount

# إنشاء مستخدم HQ
user = User.objects.create_user(
    username="hq_admin",
    email="hq@example.com",
    password="test123456",
    is_active=True
)

# إضافة StaffAccount
StaffAccount.objects.create(
    user=user,
    role=StaffAccount.Role.SUPERADMIN
)

print("✅ HQ user created: hq@example.com / test123456")
```

**أو سطر واحد:**

```bash
docker-compose exec web python manage.py shell -c "
from django.contrib.auth.models import User
from apps.accounts.models import StaffAccount
user, created = User.objects.get_or_create(email='hq@example.com', defaults={'username': 'hq_admin', 'is_active': True})
if created:
    user.set_password('test123456')
    user.save()
    StaffAccount.objects.get_or_create(user=user, defaults={'role': StaffAccount.Role.SUPERADMIN})
    print('✅ HQ user created: hq@example.com / test123456')
else:
    print('⚠️  User already exists')
"
```

#### 5. تشغيل Frontend

**في terminal جديد:**

```bash
cd frontend

# تثبيت dependencies (أول مرة فقط)
npm install

# تشغيل development server
npm run dev
```

Frontend سيعمل على: `http://localhost:3000`

---

## 🖥️ الطريقة الثانية: تشغيل محلي بدون Docker

### المتطلبات
- Python 3.11+
- PostgreSQL مع pgvector extension
- Redis
- Node.js 18+

### الخطوات

#### 1. إعداد Backend

```bash
# إنشاء virtual environment
python -m venv bot_venv

# تفعيل virtual environment
# على Windows PowerShell:
bot_venv\Scripts\Activate.ps1
# أو على Git Bash:
source bot_venv/Scripts/activate

# تثبيت dependencies
pip install -r requirements.txt

# إنشاء ملف .env (انظر أعلاه)
```

#### 2. إعداد قاعدة البيانات

```bash
# تأكد أن PostgreSQL يعمل
# أنشئ database:
# psql -U postgres
# CREATE DATABASE ai_appointment;
# \q

# تشغيل migrations
python manage.py migrate

# إضافة بيانات تجريبية
python manage.py seed_data
```

#### 3. تشغيل Backend

**Terminal 1 - Django Server:**
```bash
python manage.py runserver
```
يعمل على: `http://localhost:8000`

**Terminal 2 - Celery Worker:**
```bash
celery -A backend worker -l info
```

**Terminal 3 - Celery Beat:**
```bash
celery -A backend beat -l info
```

#### 4. تشغيل Frontend

**Terminal 4:**
```bash
cd frontend
npm install
npm run dev
```

---

## ✅ التحقق من التشغيل

### 1. Backend Health Check

```bash
# في المتصفح أو curl:
http://localhost:8000/health/

# يجب أن ترى:
{"status": "ok", "service": "ai-appointment-backend"}
```

### 2. Frontend

افتح المتصفح:
```
http://localhost:3000
```

### 3. تسجيل الدخول

**ملاحظة مهمة**: `seed_data` command ينشئ تلقائياً مستخدم HQ:
- Email: `admin@example.com`
- Password: `Admin!234`

1. افتح `http://localhost:3000/login`
2. استخدم:
   - Email: `admin@example.com`
   - Password: `Admin!234`
3. بعد تسجيل الدخول، اختر عيادة أو انتقل إلى `/hq`

**أو** إذا أنشأت مستخدم HQ يدوياً (انظر الخطوة 4):
- Email: `hq@example.com`
- Password: `test123456`

---

## 🧪 سيناريوهات الاختبار

### 1. اختبار HQ Control Panel

1. سجل دخول كمستخدم HQ
2. انتقل إلى `/hq`
3. أنشئ tenant جديد:
   - اضغط "New Tenant"
   - املأ البيانات
   - انسخ invite token
4. افتح `/hq/tenants/[slug]` لرؤية تفاصيل العيادة

### 2. اختبار Onboarding

1. افتح رابط الدعوة: `/accept-invite?token=...`
2. أنشئ كلمة مرور
3. بعد تسجيل الدخول، انتقل إلى `/c/[slug]/onboarding`
4. اتبع Setup Checklist

### 3. اختبار Clinic Portal

1. سجل دخول كـ clinic owner
2. انتقل إلى `/c/[slug]/dashboard`
3. جرب:
   - Conversations
   - Appointments
   - Services
   - Templates
   - Integrations

---

## 🔧 إصلاح المشاكل الشائعة

### Backend لا يعمل

```bash
# تحقق من logs
docker-compose logs web

# إعادة بناء
docker-compose build web
docker-compose up -d web
```

### Frontend لا يتصل بالBackend

1. تحقق من `NEXT_PUBLIC_BACKEND_URL` في `.env`
2. تأكد أن Backend يعمل على `http://localhost:8000`
3. تحقق من CORS settings في `backend/settings.py`

### Database Connection Error

```bash
# تحقق من PostgreSQL
docker-compose logs db

# إعادة تشغيل
docker-compose restart db
```

### Celery لا يعمل

```bash
# تحقق من Redis
docker-compose logs redis

# إعادة تشغيل worker
docker-compose restart worker beat
```

---

## 📝 ملاحظات مهمة

1. **للاختبار فقط**: استخدم `DJANGO_DEBUG=true` و `WHATSAPP_TEST_MODE=true`
2. **بيانات تجريبية**: `seed_data` command يضيف عيادات وخدمات تجريبية
3. **HQ User**: يجب إنشاؤه يدوياً (انظر أعلاه)
4. **WhatsApp**: في test mode، لا يحتاج إعداد حقيقي
5. **Google Calendar**: اختياري للاختبار الأساسي

---

## 🛑 إيقاف المشروع

### Docker Compose:
```bash
make dev-down
# أو
docker-compose down
```

### محلي:
- اضغط `Ctrl+C` في كل terminal
- أو أوقف PostgreSQL و Redis يدوياً

---

## 📊 URLs للاختبار

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **Health Check**: http://localhost:8000/health/
- **Readiness**: http://localhost:8000/ready/
- **Admin Panel**: http://localhost:8000/admin/ (إذا كان مفعّل)

---

## 🎯 الخطوات السريعة (Quick Start)

```bash
# 1. إنشاء .env (إذا لم يكن موجود)
# 2. تشغيل Docker
make dev-up

# 3. إعداد DB
make migrate
make seed

# 4. (اختياري) إنشاء HQ user إضافي
# ملاحظة: seed_data ينشئ تلقائياً admin@example.com / Admin!234
# إذا أردت مستخدم إضافي، انظر الخطوة 4 في الدليل

# 5. Frontend (في terminal جديد)
cd frontend && npm install && npm run dev

# 6. افتح http://localhost:3000
```

---

## ✅ Checklist قبل الاختبار

- [ ] Docker Desktop مثبت ومشغل
- [ ] ملف `.env` موجود في root directory
- [ ] جميع services تعمل (`docker-compose ps` يجب أن يظهر 5 services)
- [ ] Migrations تمت (`make migrate`)
- [ ] Seed data تمت (`make seed`)
- [ ] HQ user موجود (seed_data ينشئه تلقائياً: admin@example.com / Admin!234)
  - للتحقق: `docker-compose exec web python manage.py shell -c "from apps.accounts.models import StaffAccount; print(StaffAccount.objects.count())"`
- [ ] Frontend dependencies مثبتة (`cd frontend && npm install`)
- [ ] Frontend يعمل على port 3000
- [ ] Backend يعمل على port 8000
- [ ] Health check يعمل: `curl http://localhost:8000/health/`

---

**ملاحظة**: للاختبار الكامل، قد تحتاج إلى:
- DeepSeek API key (للـ LLM)
- Google OAuth credentials (لـ Calendar)
- WhatsApp credentials (أو استخدام test mode)

