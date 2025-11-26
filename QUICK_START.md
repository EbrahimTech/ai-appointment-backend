# دليل البدء السريع - AI Appointment Backend

## 🚀 البدء السريع (5 دقائق)

### 1. إعداد Environment Variables
```bash
# نسخ ملف env.example
cp env.example .env

# تعديل .env وإدخال القيم المطلوبة
# على الأقل: DJANGO_SECRET_KEY, POSTGRES_*, CELERY_BROKER_URL
```

### 2. إعداد قاعدة البيانات
```bash
# إنشاء قاعدة البيانات
createdb ai_appointment

# أو باستخدام psql
psql -U postgres -c "CREATE DATABASE ai_appointment;"
```

### 3. تشغيل Setup
```bash
# على Linux/Mac
chmod +x scripts/setup.sh
./scripts/setup.sh

# على Windows (استخدم Git Bash)
bash scripts/setup.sh
```

### 4. تشغيل Migrations
```bash
python manage.py migrate
python manage.py seed_data
```

### 5. تشغيل الخادم
```bash
# Development
python manage.py runserver

# أو باستخدام Docker
docker-compose up
```

## 📋 Checklist قبل النشر

### متطلبات أساسية
- [ ] `.env` file مع جميع المتغيرات المطلوبة
- [ ] `DJANGO_SECRET_KEY` قوي (50+ حرف)
- [ ] `DJANGO_DEBUG=false` في الإنتاج
- [ ] `DJANGO_ALLOWED_HOSTS` يحتوي على domains الإنتاج
- [ ] قاعدة البيانات منشأة ومحدثة
- [ ] Redis يعمل

### تكاملات
- [ ] WhatsApp ChannelAccount منشأ (راجع `WHATSAPP_SETUP.md`)
- [ ] Google OAuth credentials محددة
- [ ] DeepSeek API key محددة

### اختبارات
- [ ] Health checks تعمل (`/health/`, `/ready/`)
- [ ] Migrations تم تشغيلها
- [ ] Static files تم جمعها
- [ ] Celery workers تعمل

## 🎯 الخطوات التالية

1. **للـ Development:**
   - اقرأ `README.md`
   - استخدم `WHATSAPP_TEST_MODE=true` للاختبار

2. **للـ Production:**
   - اقرأ `DEPLOYMENT_GUIDE.md` بالكامل
   - اتبع الخطوات خطوة بخطوة
   - استخدم `scripts/deploy.sh` للمساعدة

3. **للـ Troubleshooting:**
   - راجع `DEPLOYMENT_CHECKLIST.md`
   - راجع `CHANGES_SUMMARY.md`
   - راجع logs في `docker-compose logs`

## 📚 الملفات المهمة

- `DEPLOYMENT_GUIDE.md` - دليل النشر الكامل
- `WHATSAPP_SETUP.md` - إعداد WhatsApp
- `DEPLOYMENT_CHECKLIST.md` - قائمة فحص
- `CHANGES_SUMMARY.md` - ملخص التغييرات
- `env.example` - قالب المتغيرات البيئية

## ⚡ أوامر سريعة

```bash
# Health check
curl http://localhost:8000/health/

# Migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Shell
python manage.py shell

# Tests
pytest

# Collect static
python manage.py collectstatic --noinput
```

## 🔗 روابط مفيدة

- [Django Deployment Checklist](https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

