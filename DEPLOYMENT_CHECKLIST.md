# قائمة فحص النشر (Deployment Checklist)

## 🔴 مشاكل حرجة يجب إصلاحها قبل النشر

### 1. تكامل WhatsApp غير مكتمل
**المشكلة:** الكود الحالي يستخدم `simulated-{message.id}` في `apps/workers/tasks.py:215`
- **الموقع:** `apps/workers/tasks.py` - دالة `dispatch_outbox_messages()`
- **المطلوب:** 
  - إضافة تكامل فعلي مع WhatsApp API (Meta Business API أو Twilio أو provider آخر)
  - إنشاء service layer لإرسال الرسائل الفعلية
  - إضافة error handling للتكامل

### 2. Dockerfile غير جاهز للإنتاج
**المشكلة:** يستخدم `runserver` وهو لل development فقط
- **الموقع:** `Dockerfile:15`
- **المطلوب:**
  - استخدام Gunicorn أو uWSGI
  - إضافة collectstatic
  - تحسين layers لل caching
  - إضافة health checks

### 3. ملف .env.example مفقود
**المشكلة:** لا يوجد ملف توثيق للمتغيرات البيئية المطلوبة
- **المطلوب:** إنشاء `.env.example` يحتوي على جميع المتغيرات

### 4. إعدادات الأمان مفقودة
**المشكلة:** لا توجد إعدادات CORS, Security Headers, HTTPS
- **الموقع:** `backend/settings.py`
- **المطلوب:**
  - إضافة django-cors-headers
  - إضافة SecurityMiddleware settings
  - إعدادات HTTPS

## 🟡 تحسينات مهمة للنشر

### 5. docker-compose للإنتاج
**المشكلة:** `docker-compose.yml` الحالي لل development فقط
- **المطلوب:** إنشاء `docker-compose.prod.yml` مع:
  - Nginx reverse proxy
  - SSL certificates
  - Production database settings
  - Resource limits

### 6. جمع الملفات الثابتة
**المشكلة:** لا يوجد collectstatic في build process
- **المطلوب:** إضافة `python manage.py collectstatic --noinput` في Dockerfile

### 7. Health Check Endpoints
**المشكلة:** لا توجد endpoints لل health checks
- **المطلوب:** إضافة `/health/` و `/ready/` endpoints

### 8. Logging Configuration
**المشكلة:** لا توجد إعدادات logging للإنتاج
- **المطلوب:** إضافة structured logging مع rotation

### 9. Monitoring & Error Tracking
**المشكلة:** لا يوجد error tracking
- **المطلوب:** إضافة Sentry أو similar

### 10. CI/CD Pipeline
**المشكلة:** لا يوجد CI/CD
- **المطلوب:** إضافة GitHub Actions أو GitLab CI للـ:
  - Testing
  - Building Docker images
  - Deployment

## 📋 قائمة المتغيرات البيئية المطلوبة

### Django Core
- `DJANGO_SECRET_KEY` - **مطلوب** (يجب أن يكون قوي)
- `DJANGO_DEBUG` - **مطلوب** (يجب أن يكون `false` في الإنتاج)
- `DJANGO_ALLOWED_HOSTS` - **مطلوب** (domains الإنتاج)
- `ENCRYPTION_KEY` - **مطلوب** (لتشفير البيانات الحساسة)

### Database
- `POSTGRES_DB` - **مطلوب**
- `POSTGRES_USER` - **مطلوب**
- `POSTGRES_PASSWORD` - **مطلوب**
- `POSTGRES_HOST` - **مطلوب**
- `POSTGRES_PORT` - اختياري (default: 5432)

### Celery/Redis
- `CELERY_BROKER_URL` - **مطلوب** (Redis URL)
- `CELERY_RESULT_BACKEND` - **مطلوب** (Redis URL)
- `CELERY_SWEEP_TENTATIVE_SECONDS` - اختياري (default: 600)

### WhatsApp Integration
- `WHATSAPP_DEFAULT_SENDER` - **مطلوب** (رقم WhatsApp)
- `WHATSAPP_API_KEY` - **مطلوب** (API key من provider)
- `WHATSAPP_API_URL` - **مطلوب** (API endpoint)
- `WHATSAPP_TEST_ALLOWLIST` - اختياري (لل testing)
- `WHATSAPP_TEST_RPM` - اختياري (default: 3)

### Google Calendar
- `GOOGLE_CLIENT_ID` - **مطلوب**
- `GOOGLE_CLIENT_SECRET` - **مطلوب**
- `GOOGLE_REDIRECT_URI` - **مطلوب**
- `GOOGLE_CALENDAR_ID` - اختياري (default: "primary")

### DeepSeek LLM
- `DEEPSEEK_API_KEY` - **مطلوب**
- `DEEPSEEK_API_BASE` - اختياري (default: "https://api.deepseek.com")
- `LLM_DEFAULT_MODEL` - اختياري (default: "deepseek-chat")
- `LLM_TIMEOUT_SECONDS` - اختياري (default: 15)
- `LLM_COST_BUDGET_PER_DAY` - اختياري (default: 0)
- `LLM_COST_PER_REQUEST` - اختياري (default: 0.002)

### Webhooks
- `LEAD_WEBHOOK_SECRET` - **مطلوب** (لتوقيع webhooks)

### JWT
- `JWT_ACCESS_LIFETIME_MINUTES` - اختياري (default: 30)
- `JWT_REFRESH_LIFETIME_DAYS` - اختياري (default: 7)

### Support Sessions
- `SUPPORT_SESSION_MINUTES` - اختياري (default: 15)

### Frontend
- `NEXT_PUBLIC_BACKEND_URL` - **مطلوب** (URL الباك إند)

## 🔧 الملفات المطلوب إنشاؤها

1. `.env.example` - قالب المتغيرات البيئية
2. `Dockerfile.prod` - Dockerfile للإنتاج
3. `docker-compose.prod.yml` - Docker Compose للإنتاج
4. `.github/workflows/deploy.yml` - CI/CD pipeline
5. `nginx.conf` - Nginx configuration
6. `gunicorn.conf.py` - Gunicorn configuration
7. `scripts/deploy.sh` - Deployment script

## 📝 ملاحظات إضافية

### قاعدة البيانات
- تأكد من عمل migrations قبل النشر
- تأكد من وجود backups
- تأكد من إعدادات connection pooling

### Redis
- تأكد من إعدادات persistence
- تأكد من memory limits

### Static Files
- في الإنتاج، يجب استخدام CDN أو Nginx لخدمة static files
- لا تستخدم Django لخدمة static files في الإنتاج

### SSL/TLS
- يجب استخدام HTTPS في الإنتاج
- إعدادات Let's Encrypt أو certificates أخرى

### Monitoring
- إضافة application monitoring (New Relic, Datadog, etc.)
- إضافة database monitoring
- إضافة uptime monitoring

## ✅ خطوات النشر المقترحة

1. إصلاح المشاكل الحرجة (1-4)
2. إعداد البيئة (env variables, secrets)
3. بناء Docker images
4. تشغيل migrations
5. تشغيل seed_data (إذا لزم الأمر)
6. اختبار Health checks
7. إعداد Monitoring
8. Deploy إلى staging أولاً
9. اختبار شامل في staging
10. Deploy إلى production

