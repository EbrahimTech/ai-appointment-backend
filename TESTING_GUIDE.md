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

---

# 🚀 دليل النشر (Deployment Guide)

## ✅ ما هو موجود وجاهز:

### 1. **Backend Infrastructure**
- ✅ `Dockerfile.prod` - جاهز للإنتاج
- ✅ `docker-compose.prod.yml` - إعدادات الإنتاج
- ✅ `gunicorn.conf.py` - إعدادات Gunicorn
- ✅ `nginx.conf` - إعدادات Nginx مع SSL
- ✅ PostgreSQL مع pgvector
- ✅ Redis للـ Celery
- ✅ Celery Worker & Beat

### 2. **Frontend**
- ✅ `Dockerfile.frontend` - جاهز للإنتاج
- ✅ Next.js 14.1.0 مع standalone output
- ✅ Production build scripts
- ✅ API routes جاهزة
- ✅ Middleware للـ authentication

### 3. **Security**
- ✅ HTTPS configuration في Nginx
- ✅ Security headers
- ✅ JWT authentication
- ✅ httpOnly cookies
- ✅ CORS settings

### 4. **Health Checks**
- ✅ `/health/` endpoint موجود
- ✅ Health checks في Dockerfiles

---

## ⚠️ ما يحتاج إلى إعداد قبل النشر:

### 1. **Environment Variables (.env)**

#### Backend Variables:
```env
# Django Core
DJANGO_SECRET_KEY=<generate-strong-secret-key>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database
POSTGRES_DB=ai_appointment
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=<strong-password>
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis
REDIS_PASSWORD=<strong-password>
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/0

# Security
ENCRYPTION_KEY=<generate-strong-encryption-key>
LEAD_WEBHOOK_SECRET=<generate-secret>

# LLM (DeepSeek)
DEEPSEEK_API_KEY=<your-deepseek-api-key>
DEEPSEEK_API_BASE=https://api.deepseek.com

# Google Calendar OAuth
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
GOOGLE_REDIRECT_URI=https://yourdomain.com/calendars/google/callback

# WhatsApp
WHATSAPP_DEFAULT_SENDER=<whatsapp-number>
WHATSAPP_SESSION_FALLBACK_HSM_NAME=session_clarify

# JWT
JWT_ACCESS_LIFETIME_MINUTES=30
JWT_REFRESH_LIFETIME_DAYS=7

# Support Sessions
SUPPORT_SESSION_MINUTES=60

# Celery
CELERY_SWEEP_TENTATIVE_SECONDS=600
```

#### Frontend Variables:
```env
NEXT_PUBLIC_BACKEND_URL=https://api.yourdomain.com
NEXT_PUBLIC_DEFAULT_TZ=UTC
```

### 2. **SSL Certificates**
- ⚠️ تحتاج إلى شهادات SSL في مجلد `ssl/`:
  - `ssl/cert.pem`
  - `ssl/key.pem`
- أو استخدام Let's Encrypt مع Certbot

### 3. **Domain & DNS**
- ⚠️ تحتاج إلى:
  - Domain name
  - DNS records (A record)
  - SSL certificate

### 4. **Initial Data**
- ⚠️ تحتاج إلى:
  - إنشاء HQ staff account (SUPERADMIN)
  - Seed data (اختياري)

---

## 🔧 خطوات النشر:

### الخطوة 1: إعداد ملف .env
```bash
# إنشاء ملف .env في root directory
# استخدم القائمة أعلاه لجميع المتغيرات المطلوبة
```

### الخطوة 2: إعداد SSL Certificates
```bash
# إنشاء مجلد ssl
mkdir ssl

# إضافة شهادات SSL
# cert.pem و key.pem
```

### الخطوة 3: بناء الصور
```bash
# بناء جميع الصور
docker-compose -f docker-compose.prod.yml build
```

### الخطوة 4: تشغيل الخدمات
```bash
# تشغيل جميع الخدمات
docker-compose -f docker-compose.prod.yml up -d

# التحقق من الحالة
docker-compose -f docker-compose.prod.yml ps
```

### الخطوة 5: إعداد قاعدة البيانات
```bash
# Migrations تعمل تلقائياً عند بدء web service
# للتحقق:
docker-compose -f docker-compose.prod.yml exec web python manage.py migrate

# إنشاء HQ staff account
docker-compose -f docker-compose.prod.yml exec web python manage.py shell
```

```python
from django.contrib.auth.models import User
from apps.accounts.models import StaffAccount

user = User.objects.create_user(
    username="hq_admin",
    email="admin@yourdomain.com",
    password="strong-password-here",
    is_active=True
)

StaffAccount.objects.create(
    user=user,
    role=StaffAccount.Role.SUPERADMIN
)
```

### الخطوة 6: التحقق من النشر
```bash
# Health check
curl https://yourdomain.com/health/

# Frontend
curl https://yourdomain.com/

# Backend API
curl https://yourdomain.com/api/health/
```

---

## 📝 ملاحظات مهمة:

1. **Security**: تأكد من تغيير جميع الـ secrets في production
2. **Database**: استخدم PostgreSQL في production (ليس SQLite)
3. **SSL**: HTTPS إلزامي في production
4. **Backup**: ضع خطة backup منتظمة للـ database
5. **Monitoring**: راقب الأداء والأخطاء
6. **Updates**: خطط لـ updates وmaintenance windows

---

## 🔄 تحديث التطبيق:

```bash
# 1. سحب التحديثات
git pull

# 2. إعادة بناء الصور
docker-compose -f docker-compose.prod.yml build

# 3. إعادة تشغيل الخدمات
docker-compose -f docker-compose.prod.yml up -d

# 4. تشغيل migrations (إذا لزم الأمر)
docker-compose -f docker-compose.prod.yml exec web python manage.py migrate
```

---

## 🛑 إيقاف التطبيق:

```bash
# إيقاف جميع الخدمات
docker-compose -f docker-compose.prod.yml down

# إيقاف مع حذف volumes (احذر!)
docker-compose -f docker-compose.prod.yml down -v
```

---

## 📊 Services في Production:

- `db` - PostgreSQL مع pgvector
- `redis` - Redis للـ Celery
- `web` - Django Backend (Gunicorn)
- `worker` - Celery Worker
- `beat` - Celery Beat
- `frontend` - Next.js Frontend
- `nginx` - Nginx Reverse Proxy

---

## ✅ Checklist قبل النشر:

- [ ] ملف `.env` موجود مع جميع المتغيرات
- [ ] SSL certificates موجودة في `ssl/`
- [ ] Domain & DNS مُعدة
- [ ] `DJANGO_DEBUG=false`
- [ ] جميع secrets قوية ومختلفة عن development
- [ ] `ALLOWED_HOSTS` يحتوي على domain الصحيح
- [ ] HQ staff account تم إنشاؤه
- [ ] Database migrations تمت
- [ ] جميع services تعمل
- [ ] Health checks تعمل
- [ ] Frontend و Backend يتصلان بشكل صحيح

---

# 📋 خلاصة ما تبقى قبل النشر - مع شرح الحلول

## ✅ ما تم إنجازه (جاهز 100%):

1. ✅ **Dockerfiles** - `Dockerfile.prod` و `Dockerfile.frontend`
2. ✅ **Docker Compose** - `docker-compose.prod.yml` جاهز
3. ✅ **Nginx Configuration** - `nginx.conf` مع SSL و routing
4. ✅ **Health Checks** - `/health/` endpoint موجود
5. ✅ **Code** - جميع الكود جاهز ومختبر

---

## ⚠️ ما تبقى (4 نقاط فقط):

### 1️⃣ إنشاء ملف `.env` مع جميع المتغيرات

**الخطوات:**

#### أ) إنشاء الملف:
```bash
# في root directory للمشروع
touch .env
# أو على Windows:
type nul > .env
```

#### ب) إضافة المحتوى:
افتح `.env` وأضف:

```env
# ============================================
# Django Core Settings
# ============================================
DJANGO_SECRET_KEY=<generate-strong-secret>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# ============================================
# Database (PostgreSQL)
# ============================================
POSTGRES_DB=ai_appointment
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=<strong-password>
POSTGRES_HOST=db
POSTGRES_PORT=5432

# ============================================
# Redis
# ============================================
REDIS_PASSWORD=<strong-password>
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/0

# ============================================
# Security
# ============================================
ENCRYPTION_KEY=<generate-strong-key>
LEAD_WEBHOOK_SECRET=<generate-secret>

# ============================================
# LLM (DeepSeek) - اختياري
# ============================================
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_API_BASE=https://api.deepseek.com

# ============================================
# Google Calendar OAuth - اختياري
# ============================================
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=https://yourdomain.com/calendars/google/callback

# ============================================
# WhatsApp - اختياري
# ============================================
WHATSAPP_DEFAULT_SENDER=+1234567890
WHATSAPP_SESSION_FALLBACK_HSM_NAME=session_clarify

# ============================================
# JWT Settings
# ============================================
JWT_ACCESS_LIFETIME_MINUTES=30
JWT_REFRESH_LIFETIME_DAYS=7

# ============================================
# Support Sessions
# ============================================
SUPPORT_SESSION_MINUTES=60

# ============================================
# Celery Settings
# ============================================
CELERY_SWEEP_TENTATIVE_SECONDS=600

# ============================================
# Frontend (Next.js)
# ============================================
NEXT_PUBLIC_BACKEND_URL=https://yourdomain.com
NEXT_PUBLIC_DEFAULT_TZ=UTC

# ============================================
# CORS (if needed)
# ============================================
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

#### ج) توليد Secrets القوية:

**لـ DJANGO_SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

**لـ ENCRYPTION_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**لـ LEAD_WEBHOOK_SECRET:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**لـ POSTGRES_PASSWORD و REDIS_PASSWORD:**
استخدم كلمات مرور قوية (16+ حرف، أرقام، رموز)

---

### 2️⃣ إعداد SSL Certificates

**الخيار الأول: Let's Encrypt (مجاني - موصى به)**

```bash
# 1. تثبيت Certbot
sudo apt-get update
sudo apt-get install certbot

# 2. الحصول على شهادة
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# 3. نسخ الشهادات إلى مجلد ssl
mkdir -p ssl
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/key.pem
sudo chmod 644 ssl/cert.pem
sudo chmod 600 ssl/key.pem
```

**الخيار الثاني: Self-Signed (للاختبار فقط - لا تستخدم في production)**

```bash
mkdir -p ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/key.pem \
  -out ssl/cert.pem \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=yourdomain.com"
```

---

### 3️⃣ إعداد Domain & DNS

**الخطوات:**

1. **شراء Domain** من أي مزود (Namecheap, GoDaddy, Cloudflare, etc.)

2. **إعداد DNS Records:**
   - **A Record:**
     ```
     Type: A
     Name: @ (أو yourdomain.com)
     Value: <IP-address-of-your-server>
     TTL: 3600
     ```
   - **A Record للـ www:**
     ```
     Type: A
     Name: www
     Value: <IP-address-of-your-server>
     TTL: 3600
     ```

3. **الحصول على IP Server:**
   ```bash
   curl ifconfig.me
   ```

4. **الانتظار:** DNS propagation قد يستغرق 24-48 ساعة

---

### 4️⃣ إنشاء HQ Staff Account (بعد النشر)

**الخطوات:**

#### أ) بعد تشغيل الخدمات:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

#### ب) إنشاء المستخدم (سطر واحد):
```bash
docker-compose -f docker-compose.prod.yml exec web python manage.py shell -c "
from django.contrib.auth.models import User
from apps.accounts.models import StaffAccount
user = User.objects.create_user(
    username='hq_admin',
    email='admin@yourdomain.com',
    password='YourStrongPassword123!',
    is_active=True
)
StaffAccount.objects.create(user=user, role=StaffAccount.Role.SUPERADMIN)
print('✅ HQ user created: admin@yourdomain.com')
"
```

---

## 🚀 خطوات النشر الكاملة (بترتيب):

1. **إعداد Server:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y docker.io docker-compose git
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

2. **رفع الكود:**
   ```bash
   git clone <your-repo-url>
   cd ai-appointment-backend
   ```

3. **إنشاء ملف .env** (انظر الخطوة 1 أعلاه)

4. **إعداد SSL** (انظر الخطوة 2 أعلاه)

5. **بناء الصور:**
   ```bash
   docker-compose -f docker-compose.prod.yml build
   ```

6. **تشغيل الخدمات:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

7. **التحقق من الحالة:**
   ```bash
   docker-compose -f docker-compose.prod.yml ps
   ```

8. **إنشاء HQ Account** (انظر الخطوة 4 أعلاه)

9. **اختبار النشر:**
   ```bash
   curl https://yourdomain.com/health/
   ```

---

## 🔧 حل المشاكل الشائعة:

### المشكلة: Nginx لا يبدأ
**الحل:**
```bash
# تحقق من SSL certificates
ls -la ssl/
# يجب أن ترى cert.pem و key.pem

# تحقق من nginx.conf
docker-compose -f docker-compose.prod.yml exec nginx nginx -t
```

### المشكلة: Database connection error
**الحل:**
```bash
# تحقق من PostgreSQL
docker-compose -f docker-compose.prod.yml logs db

# تحقق من .env - POSTGRES_PASSWORD يجب أن يكون صحيح
```

### المشكلة: Frontend لا يتصل بالBackend
**الحل:**
```bash
# تحقق من NEXT_PUBLIC_BACKEND_URL في .env
# يجب أن يكون: https://yourdomain.com
```

### المشكلة: SSL certificate expired
**الحل:**
```bash
# تجديد Let's Encrypt
sudo certbot renew
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/key.pem
docker-compose -f docker-compose.prod.yml restart nginx
```

---

## 🎯 الخلاصة النهائية:

**ما تبقى (4 نقاط فقط):**
1. ✅ إنشاء `.env` (5 دقائق)
2. ✅ إعداد SSL (10-15 دقيقة)
3. ✅ إعداد Domain & DNS (يعتمد على المزود)
4. ✅ إنشاء HQ account (2 دقيقة بعد النشر)

**الوقت الإجمالي:** ~30 دقيقة (باستثناء DNS propagation)

**كل شيء آخر جاهز! 🚀**

---

## 📝 ملاحظات مهمة:

1. **Security**: لا تشارك ملف `.env` أبداً
2. **Backup**: ضع خطة backup للـ database
3. **Monitoring**: راقب logs بانتظام
4. **Updates**: خطط لـ updates منتظمة
5. **SSL Renewal**: Let's Encrypt يحتاج تجديد كل 90 يوم

