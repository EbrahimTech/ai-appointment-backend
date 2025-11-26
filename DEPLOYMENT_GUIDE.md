# دليل النشر الكامل - AI Appointment Backend

## 📋 نظرة عامة

هذا الدليل يشرح خطوة بخطوة كيفية نشر المشروع في بيئة الإنتاج.

## ✅ المتطلبات الأساسية

- Docker & Docker Compose
- PostgreSQL 12+ (مع pgvector extension)
- Redis 6+
- Domain name مع SSL certificate
- Server مع 2GB+ RAM

## 🚀 خطوات النشر

### الخطوة 1: إعداد البيئة

#### 1.1 نسخ المشروع
```bash
git clone <repository-url>
cd ai-appointment-backend
```

#### 1.2 إعداد Environment Variables
```bash
# نسخ ملف env.example
cp env.example .env

# تعديل .env وإدخال القيم الصحيحة
nano .env  # أو استخدام محرر آخر
```

**المتغيرات المطلوبة:**
- `DJANGO_SECRET_KEY` - مفتاح سري قوي (استخدم: `python -c "import secrets; print(secrets.token_urlsafe(50))"`)
- `DJANGO_DEBUG=false` - **يجب أن يكون false**
- `DJANGO_ALLOWED_HOSTS` - domains الإنتاج (مثال: `yourdomain.com,api.yourdomain.com`)
- `ENCRYPTION_KEY` - مفتاح تشفير (32+ حرف)
- `POSTGRES_*` - إعدادات قاعدة البيانات
- `CELERY_BROKER_URL` - Redis URL
- `DEEPSEEK_API_KEY` - مفتاح DeepSeek API
- `GOOGLE_CLIENT_ID` و `GOOGLE_CLIENT_SECRET` - Google OAuth
- `LEAD_WEBHOOK_SECRET` - سر webhook

#### 1.3 تشغيل Setup Script
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### الخطوة 2: إعداد قاعدة البيانات

#### 2.1 إنشاء قاعدة البيانات
```bash
# الاتصال بـ PostgreSQL
psql -U postgres

# إنشاء قاعدة البيانات
CREATE DATABASE ai_appointment;
CREATE USER ai_user WITH PASSWORD 'your-strong-password';
GRANT ALL PRIVILEGES ON DATABASE ai_appointment TO ai_user;

# تفعيل pgvector extension
\c ai_appointment
CREATE EXTENSION IF NOT EXISTS vector;
\q
```

#### 2.2 تشغيل Migrations
```bash
# باستخدام Docker
docker-compose exec web python manage.py migrate

# أو محلياً
python manage.py migrate
```

#### 2.3 تحميل البيانات الأولية
```bash
python manage.py seed_data
```

### الخطوة 3: إعداد WhatsApp

راجع `WHATSAPP_SETUP.md` لإعداد WhatsApp Provider.

**ملخص سريع:**
```python
from apps.channels.models import ChannelAccount
from apps.clinics.models import Clinic

clinic = Clinic.objects.get(slug="your-clinic")

# للميتا
ChannelAccount.objects.create(
    clinic=clinic,
    channel="whatsapp",
    provider_name="meta",
    access_token="YOUR_META_TOKEN",
    metadata={"phone_number_id": "YOUR_PHONE_ID"}
)
```

### الخطوة 4: بناء Docker Images

```bash
# بناء image للإنتاج
docker build -f Dockerfile.prod -t ai-appointment-backend:latest .

# أو استخدام docker-compose
docker-compose -f docker-compose.prod.yml build
```

### الخطوة 5: النشر

#### 5.1 استخدام Docker Compose (موصى به)
```bash
# تشغيل جميع الخدمات
docker-compose -f docker-compose.prod.yml up -d

# التحقق من الحالة
docker-compose -f docker-compose.prod.yml ps

# عرض الـ logs
docker-compose -f docker-compose.prod.yml logs -f
```

#### 5.2 أو استخدام Deploy Script
```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

### الخطوة 6: التحقق من النشر

#### 6.1 Health Check
```bash
# استخدام script
chmod +x scripts/health_check.sh
./scripts/health_check.sh

# أو يدوياً
curl http://localhost/health/
curl http://localhost/ready/
```

#### 6.2 اختبار API
```bash
# اختبار metrics endpoint
curl http://localhost/metrics/summary

# اختبار authentication
curl -X POST http://localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin!234"}'
```

### الخطوة 7: إعداد Nginx (إذا لم يكن في docker-compose)

إذا كنت تستخدم Nginx خارج Docker:

```bash
# نسخ nginx.conf
sudo cp nginx.conf /etc/nginx/sites-available/ai-appointment
sudo ln -s /etc/nginx/sites-available/ai-appointment /etc/nginx/sites-enabled/

# اختبار configuration
sudo nginx -t

# إعادة تحميل Nginx
sudo systemctl reload nginx
```

### الخطوة 8: إعداد SSL

#### باستخدام Let's Encrypt:
```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d api.yourdomain.com
```

### الخطوة 9: إعداد Monitoring

#### 9.1 Health Check Monitoring
```bash
# إضافة cron job للـ health check
crontab -e

# إضافة السطر التالي (كل 5 دقائق)
*/5 * * * * /path/to/scripts/health_check.sh >> /var/log/health_check.log 2>&1
```

#### 9.2 Database Backups
```bash
# إضافة cron job للـ backups
crontab -e

# إضافة السطر التالي (يومياً في 2 صباحاً)
0 2 * * * /path/to/scripts/backup_db.sh >> /var/log/backup.log 2>&1
```

## 🔧 الصيانة

### تحديث المشروع
```bash
# سحب آخر التحديثات
git pull

# إعادة بناء images
docker-compose -f docker-compose.prod.yml build

# إعادة تشغيل الخدمات
docker-compose -f docker-compose.prod.yml up -d

# تشغيل migrations
docker-compose -f docker-compose.prod.yml exec web python manage.py migrate
```

### عرض Logs
```bash
# جميع الخدمات
docker-compose -f docker-compose.prod.yml logs -f

# خدمة محددة
docker-compose -f docker-compose.prod.yml logs -f web
docker-compose -f docker-compose.prod.yml logs -f worker
```

### Backup قاعدة البيانات
```bash
chmod +x scripts/backup_db.sh
./scripts/backup_db.sh
```

### Restore قاعدة البيانات
```bash
# من backup file
psql -U ai_user -d ai_appointment < backups/backup_file.sql
```

## 🐛 Troubleshooting

### المشكلة: Health check fails
```bash
# تحقق من logs
docker-compose -f docker-compose.prod.yml logs web

# تحقق من database connection
docker-compose -f docker-compose.prod.yml exec web python manage.py dbshell
```

### المشكلة: WhatsApp messages not sending
```bash
# تحقق من ChannelAccount
docker-compose -f docker-compose.prod.yml exec web python manage.py shell
>>> from apps.channels.models import ChannelAccount
>>> ChannelAccount.objects.all()

# تحقق من worker logs
docker-compose -f docker-compose.prod.yml logs worker
```

### المشكلة: Static files not loading
```bash
# إعادة جمع static files
docker-compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput

# تحقق من Nginx configuration
sudo nginx -t
```

## 📊 Monitoring Checklist

- [ ] Health checks تعمل
- [ ] Database backups تعمل
- [ ] Logs يتم جمعها
- [ ] SSL certificates صالحة
- [ ] WhatsApp integration يعمل
- [ ] Celery workers تعمل
- [ ] Google Calendar sync يعمل

## 🔐 Security Checklist

- [ ] `DJANGO_DEBUG=false`
- [ ] `SECURE_SSL_REDIRECT=true`
- [ ] SSL certificates مثبتة
- [ ] Secrets محمية (لا في git)
- [ ] Database passwords قوية
- [ ] Firewall configured
- [ ] Regular backups

## 📞 الدعم

إذا واجهت مشاكل:
1. راجع logs: `docker-compose logs`
2. راجع `DEPLOYMENT_CHECKLIST.md`
3. راجع `WHATSAPP_SETUP.md` لـ WhatsApp issues
4. راجع `CHANGES_SUMMARY.md` للتغييرات الأخيرة

