# 🚀 الخطوات التالية - خطة العمل

## ✅ ما تم إنجازه (جاهز 100%)

- ✅ جميع الملفات جاهزة
- ✅ الكود جاهز ومختبر
- ✅ الوثائق كاملة
- ✅ Scripts مساعدة جاهزة

---

## 📋 ما يجب عليك القيام به الآن

### المرحلة 1: التحضير المحلي (قبل النشر)

#### 1.1 مراجعة الملفات المهمة
```bash
# اقرأ هذه الملفات:
- README.md (الوثائق الرئيسية)
- TESTING_GUIDE.md (دليل كامل)
- env.example (جميع المتغيرات المطلوبة)
- SECURITY_REVIEW.md (تقرير الأمان)
```

#### 1.2 اختبار محلي (اختياري لكن موصى به)
```bash
# 1. تشغيل المشروع محلياً
make dev-up

# 2. التحقق من أن كل شيء يعمل
make health

# 3. اختبار الواجهة
# افتح: http://localhost:3000
```

---

### المرحلة 2: إعداد Server للإنتاج

#### 2.1 متطلبات Server
- ✅ Ubuntu 20.04+ أو Debian 11+
- ✅ Docker و Docker Compose مثبتين
- ✅ Domain name جاهز
- ✅ Server IP address

#### 2.2 تثبيت Docker (إذا لم يكن مثبت)
```bash
# على Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y docker.io docker-compose git
sudo systemctl start docker
sudo systemctl enable docker

# إضافة المستخدم إلى docker group
sudo usermod -aG docker $USER
# ثم logout و login مرة أخرى
```

---

### المرحلة 3: رفع الكود إلى Server

#### 3.1 رفع الكود
```bash
# على Server
git clone <your-repository-url>
cd ai-appointment-backend
```

أو إذا كان الكود موجود:
```bash
cd ai-appointment-backend
git pull  # للحصول على آخر التحديثات
```

---

### المرحلة 4: إعداد Environment Variables

#### 4.1 إنشاء ملف .env
```bash
# على Server
cp env.example .env
nano .env  # أو vi .env
```

#### 4.2 توليد Secrets
```bash
# على Server
make generate-secrets
# أو
bash scripts/generate_secrets.sh
```

**انسخ المخرجات وأضفها إلى ملف `.env`**

#### 4.3 تعديل .env بالقيم الصحيحة

**مطلوب تغييره:**
```env
# Django
DJANGO_SECRET_KEY=<من generate-secrets>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database
POSTGRES_PASSWORD=<من generate-secrets>
REDIS_PASSWORD=<من generate-secrets>

# Security
ENCRYPTION_KEY=<من generate-secrets>
LEAD_WEBHOOK_SECRET=<من generate-secrets>

# Frontend
NEXT_PUBLIC_BACKEND_URL=https://yourdomain.com

# CORS
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

**اختياري (يمكن إضافته لاحقاً):**
```env
# LLM
DEEPSEEK_API_KEY=your-key

# Google Calendar
GOOGLE_CLIENT_ID=your-id
GOOGLE_CLIENT_SECRET=your-secret
GOOGLE_REDIRECT_URI=https://yourdomain.com/calendars/google/callback

# WhatsApp
WHATSAPP_DEFAULT_SENDER=+1234567890
```

---

### المرحلة 5: إعداد SSL Certificates

#### 5.1 تثبيت Certbot
```bash
sudo apt-get update
sudo apt-get install -y certbot
```

#### 5.2 الحصول على شهادة SSL
```bash
# تأكد أن Domain يشير إلى Server IP أولاً
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com
```

#### 5.3 نسخ الشهادات
```bash
mkdir -p ssl
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/key.pem
sudo chmod 644 ssl/cert.pem
sudo chmod 600 ssl/key.pem
```

---

### المرحلة 6: النشر

#### 6.1 بناء الصور
```bash
make prod-build
# أو
docker-compose -f docker-compose.prod.yml build
```

#### 6.2 تشغيل الخدمات
```bash
make prod-up
# أو
docker-compose -f docker-compose.prod.yml up -d
```

#### 6.3 تشغيل Migrations
```bash
make prod-migrate
# أو
docker-compose -f docker-compose.prod.yml exec web python manage.py migrate --noinput
```

#### 6.4 التحقق من الصحة
```bash
make health
# أو
bash scripts/check_health.sh
```

---

### المرحلة 7: إنشاء HQ Admin User

#### 7.1 إنشاء المستخدم
```bash
make create-hq-user admin@yourdomain.com YourStrongPassword123! SUPERADMIN
# أو
bash scripts/create_hq_user.sh admin@yourdomain.com YourStrongPassword123! SUPERADMIN
```

#### 7.2 اختبار تسجيل الدخول
1. افتح: `https://yourdomain.com/login`
2. سجل دخول بـ email و password الذي أنشأته
3. يجب أن ترى HQ Portal

---

### المرحلة 8: التحقق النهائي

#### 8.1 فحص جميع الخدمات
```bash
make health
```

يجب أن ترى:
- ✅ Backend is healthy
- ✅ Database connection OK
- ✅ Redis connection OK
- ✅ Celery worker is running

#### 8.2 اختبار الواجهة
- ✅ Frontend يعمل: `https://yourdomain.com`
- ✅ Backend API يعمل: `https://yourdomain.com/health/`
- ✅ تسجيل الدخول يعمل
- ✅ HQ Portal يعمل

#### 8.3 إعداد Backup
```bash
# اختبار Backup
make backup

# إعداد Backup تلقائي (cron job)
# أضف إلى crontab:
# 0 2 * * * cd /path/to/ai-appointment-backend && make backup
```

---

## 📝 Checklist النهائي

قبل أن تعتبر المشروع جاهزاً، تأكد من:

- [ ] ملف `.env` موجود مع جميع المتغيرات المطلوبة
- [ ] جميع secrets قوية ومختلفة عن development
- [ ] SSL certificates موجودة في `ssl/`
- [ ] Domain & DNS مُعدة وتشير إلى Server
- [ ] `DJANGO_DEBUG=false` في `.env`
- [ ] `ALLOWED_HOSTS` يحتوي على domain الصحيح
- [ ] `NEXT_PUBLIC_BACKEND_URL` يحتوي على domain الصحيح
- [ ] HQ staff account تم إنشاؤه
- [ ] Database migrations تمت
- [ ] جميع services تعمل (`make health`)
- [ ] تسجيل الدخول يعمل
- [ ] HQ Portal يعمل
- [ ] Backup script تم اختباره

---

## 🔧 أوامر مفيدة بعد النشر

### عرض Logs
```bash
make prod-logs
# أو لخدمة محددة:
docker-compose -f docker-compose.prod.yml logs -f web
docker-compose -f docker-compose.prod.yml logs -f worker
```

### إعادة تشغيل Service
```bash
docker-compose -f docker-compose.prod.yml restart web
docker-compose -f docker-compose.prod.yml restart worker
```

### Backup Database
```bash
make backup
```

### تحديث المشروع
```bash
git pull
make prod-build
make prod-down
make prod-up
make prod-migrate
```

### تجديد SSL Certificate
```bash
sudo certbot renew
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/key.pem
docker-compose -f docker-compose.prod.yml restart nginx
```

---

## ⚠️ ملاحظات مهمة

1. **Security**: 
   - لا تشارك ملف `.env` أبداً
   - استخدم كلمات مرور قوية
   - راقب logs بانتظام

2. **Backup**:
   - قم بـ backup يومي للـ database
   - احتفظ بنسخ احتياطية في مكان آمن

3. **Monitoring**:
   - راقب `make health` بانتظام
   - راقب logs للأخطاء

4. **Updates**:
   - خطط لـ updates منتظمة
   - اختبر updates في بيئة development أولاً

5. **SSL Renewal**:
   - Let's Encrypt يحتاج تجديد كل 90 يوم
   - أضف cron job لتجديد تلقائي

---

## 🆘 حل المشاكل

### المشكلة: Services لا تبدأ
```bash
# تحقق من logs
make prod-logs

# تحقق من .env
cat .env | grep -v "^#" | grep -v "^$"

# تحقق من SSL certificates
ls -la ssl/
```

### المشكلة: Database connection error
```bash
# تحقق من PostgreSQL
docker-compose -f docker-compose.prod.yml logs db

# تحقق من .env - POSTGRES_PASSWORD
```

### المشكلة: Frontend لا يتصل بالBackend
```bash
# تحقق من NEXT_PUBLIC_BACKEND_URL في .env
# يجب أن يكون: https://yourdomain.com
```

---

## ✅ الخلاصة

**الخطوات الأساسية:**
1. إعداد Server و Docker
2. رفع الكود
3. إعداد `.env` مع secrets
4. إعداد SSL
5. النشر (`make prod-build && make prod-up`)
6. إنشاء HQ user
7. التحقق من الصحة

**الوقت المتوقع:** 30-60 دقيقة (باستثناء DNS propagation)

**جاهز للانطلاق! 🚀**

