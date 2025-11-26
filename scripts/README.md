# Scripts Directory

هذا المجلد يحتوي على scripts مساعدة للنشر والصيانة.

## الملفات المتوفرة

### 1. setup.sh
**الوصف:** يساعد في إعداد المشروع للمرة الأولى

**الاستخدام:**
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

**ما يفعله:**
- يتحقق من وجود .env وينشئه من env.example
- ينشئ virtual environment
- يثبت dependencies
- يتحقق من المتغيرات المطلوبة
- ينشئ logs directory

### 2. deploy.sh
**الوصف:** يستعد للنشر (بناء images، migrations، إلخ)

**الاستخدام:**
```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

**ما يفعله:**
- يتحقق من .env
- يتحقق من أن DEBUG=false
- يبني Docker image
- يشغل health checks
- يشغل migrations
- يجمع static files

### 3. health_check.sh
**الوصف:** يتحقق من صحة النظام

**الاستخدام:**
```bash
chmod +x scripts/health_check.sh
BACKEND_URL=http://localhost:8000 ./scripts/health_check.sh
```

**ما يفعله:**
- يتحقق من /health/ endpoint
- يتحقق من /ready/ endpoint
- يتحقق من database connection
- يتحقق من Redis connection

### 4. backup_db.sh
**الوصف:** ينشئ backup لقاعدة البيانات

**الاستخدام:**
```bash
chmod +x scripts/backup_db.sh
./scripts/backup_db.sh
```

**ما يفعله:**
- ينشئ backup للـ PostgreSQL database
- يضغط الملف
- يحذف backups القديمة (أكثر من 7 أيام)

**ملاحظة:** يحتاج pg_dump أو Docker

## على Windows

إذا كنت على Windows، يمكنك:
1. استخدام Git Bash لتشغيل هذه scripts
2. أو استخدام Docker للـ deployment
3. أو تحويل الأوامر يدوياً إلى PowerShell

## إضافة إلى Cron (Linux/Mac)

```bash
# Health check كل 5 دقائق
*/5 * * * * /path/to/scripts/health_check.sh >> /var/log/health_check.log 2>&1

# Backup يومياً في 2 صباحاً
0 2 * * * /path/to/scripts/backup_db.sh >> /var/log/backup.log 2>&1
```

