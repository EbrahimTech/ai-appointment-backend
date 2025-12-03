"""
Django management command to check real-world setup status
Usage: python manage.py check_setup
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from apps.clinics.models import Clinic
from apps.accounts.models import StaffAccount
from apps.channels.models import ChannelAccount, ChannelType
from apps.calendars.models import GoogleCredential
from apps.services.models import ServiceHours
from apps.channels.models import HSMTemplate, HSMTemplateStatus
from apps.channels.models import OutboxMessage
from datetime import timedelta
from django.utils import timezone
import os

class Command(BaseCommand):
    help = 'Check real-world setup status for all clinics'

    def handle(self, *args, **options):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  🔍 مراجعة شاملة لإعدادات المشروع للتجربة الحقيقية")
        self.stdout.write("=" * 60 + "\n")
        
        # 1. Check Environment Variables
        self.check_env_variables()
        
        # 2. Check Clinics
        clinic_statuses = self.check_clinics()
        
        # 3. Check HQ Users
        hq_ok = self.check_hq_users()
        
        # 4. Check DeepSeek
        deepseek_ok = self.check_deepseek()
        
        # 5. Check WhatsApp
        whatsapp_ok = self.check_whatsapp()
        
        # 6. Check Google Calendar
        calendar_ok = self.check_google_calendar()
        
        # 7. Recent Activity
        self.check_recent_activity()
        
        # 8. Summary
        self.generate_summary(clinic_statuses, hq_ok, deepseek_ok, whatsapp_ok, calendar_ok)
    
    def check_env_variables(self):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  1. التحقق من Environment Variables")
        self.stdout.write("=" * 60 + "\n")
        
        required = {
            "DJANGO_SECRET_KEY": "Django Secret Key",
            "POSTGRES_DB": "Database Name",
            "POSTGRES_USER": "Database User",
            "POSTGRES_PASSWORD": "Database Password",
            "REDIS_PASSWORD": "Redis Password",
            "ENCRYPTION_KEY": "Encryption Key",
        }
        
        optional = {
            "DEEPSEEK_API_KEY": "DeepSeek AI API Key",
            "GOOGLE_CLIENT_ID": "Google Calendar OAuth Client ID",
            "GOOGLE_CLIENT_SECRET": "Google Calendar OAuth Client Secret",
            "GOOGLE_REDIRECT_URI": "Google Calendar OAuth Redirect URI",
            "WHATSAPP_DEFAULT_SENDER": "WhatsApp Default Sender",
            "WHATSAPP_TEST_ALLOWLIST": "WhatsApp Test Mode Allowlist",
        }
        
        self.stdout.write("📋 المتغيرات المطلوبة:")
        for var, desc in required.items():
            value = getattr(settings, var, None) or os.getenv(var)
            if value and value not in ["", "your-", "change-in-production"]:
                self.stdout.write(self.style.SUCCESS(f"   ✅ {var}: معرّف ({desc})"))
            else:
                self.stdout.write(self.style.ERROR(f"   ❌ {var}: غير معرّف ({desc})"))
        
        self.stdout.write("\n📋 المتغيرات الاختيارية (للتجربة الحقيقية):")
        optional_count = 0
        for var, desc in optional.items():
            value = getattr(settings, var, None) or os.getenv(var)
            if value and value not in ["", "your-"]:
                self.stdout.write(self.style.SUCCESS(f"   ✅ {var}: معرّف ({desc})"))
                optional_count += 1
            else:
                self.stdout.write(self.style.WARNING(f"   ⚠️  {var}: غير معرّف ({desc})"))
        
        return optional_count
    
    def check_clinics(self):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  2. التحقق من العيادات")
        self.stdout.write("=" * 60 + "\n")
        
        clinics = Clinic.objects.all()
        total = clinics.count()
        
        if total == 0:
            self.stdout.write(self.style.WARNING("   ⚠️  لا توجد عيادات في النظام"))
            self.stdout.write("   ℹ️  قم بإنشاء عيادة من HQ Portal: /hq")
            return []
        
        self.stdout.write(self.style.SUCCESS(f"   ✅ عدد العيادات: {total}\n"))
        
        clinic_statuses = []
        
        for clinic in clinics:
            self.stdout.write(f"\n🏥 العيادة: {clinic.name} ({clinic.slug})")
            self.stdout.write(f"   ID: {clinic.id}")
            self.stdout.write(f"   Email: {clinic.owner.email if clinic.owner else 'N/A'}")
            self.stdout.write(f"   Phone: {clinic.phone_number or 'N/A'}")
            self.stdout.write(f"   WhatsApp: {clinic.whatsapp_number or 'N/A'}")
            
            status = {
                "clinic": clinic,
                "services": False,
                "hours": False,
                "whatsapp": False,
                "google": False,
                "templates": False,
            }
            
            # Check Services
            services_count = clinic.services.filter(is_active=True).count()
            if services_count > 0:
                self.stdout.write(self.style.SUCCESS(f"   ✅ Services: {services_count} خدمة"))
                status["services"] = True
            else:
                self.stdout.write(self.style.WARNING("   ⚠️  Services: لا توجد خدمات"))
            
            # Check Service Hours
            hours_count = ServiceHours.objects.filter(service__clinic=clinic).count()
            if hours_count > 0:
                self.stdout.write(self.style.SUCCESS(f"   ✅ Operating Hours: {hours_count} ساعة عمل"))
                status["hours"] = True
            else:
                self.stdout.write(self.style.WARNING("   ⚠️  Operating Hours: غير معرّفة"))
            
            # Check WhatsApp Channel
            whatsapp_account = ChannelAccount.objects.filter(
                clinic=clinic,
                channel=ChannelType.WHATSAPP
            ).first()
            
            if whatsapp_account:
                provider = whatsapp_account.provider_name
                metadata = whatsapp_account.metadata or {}
                phone = metadata.get("phone_number_id") or metadata.get("from_number") or "N/A"
                self.stdout.write(self.style.SUCCESS(f"   ✅ WhatsApp: متصل ({provider}) - {phone}"))
                status["whatsapp"] = True
            else:
                self.stdout.write(self.style.WARNING("   ⚠️  WhatsApp: غير متصل"))
                self.stdout.write(f"   ℹ️  قم بإضافة WhatsApp Channel من: /c/{clinic.slug}/integrations")
            
            # Check Google Calendar
            google_cred = GoogleCredential.objects.filter(clinic=clinic).first()
            if google_cred:
                self.stdout.write(self.style.SUCCESS(f"   ✅ Google Calendar: متصل ({google_cred.account_email})"))
                status["google"] = True
            else:
                self.stdout.write(self.style.WARNING("   ⚠️  Google Calendar: غير متصل"))
                self.stdout.write(f"   ℹ️  قم بربط Google Calendar من: /c/{clinic.slug}/integrations")
            
            # Check Templates
            templates_count = HSMTemplate.objects.filter(
                clinic=clinic,
                status=HSMTemplateStatus.APPROVED
            ).count()
            if templates_count > 0:
                self.stdout.write(self.style.SUCCESS(f"   ✅ Message Templates: {templates_count} قالب"))
                status["templates"] = True
            else:
                self.stdout.write(self.style.WARNING("   ⚠️  Message Templates: لا توجد قوالب"))
            
            clinic_statuses.append(status)
        
        return clinic_statuses
    
    def check_hq_users(self):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  3. التحقق من HQ Staff")
        self.stdout.write("=" * 60 + "\n")
        
        hq_staff = StaffAccount.objects.all()
        count = hq_staff.count()
        
        if count == 0:
            self.stdout.write(self.style.WARNING("   ⚠️  لا يوجد HQ Staff في النظام"))
            self.stdout.write("   ℹ️  قم بإنشاء HQ User: make local-create-user")
            return False
        
        self.stdout.write(self.style.SUCCESS(f"   ✅ عدد HQ Staff: {count}\n"))
        
        for staff in hq_staff:
            role = staff.role
            user = staff.user
            self.stdout.write(f"   👤 {user.email} ({role})")
        
        return True
    
    def check_deepseek(self):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  4. التحقق من DeepSeek AI")
        self.stdout.write("=" * 60 + "\n")
        
        api_key = getattr(settings, "DEEPSEEK_API_KEY", None) or os.getenv("DEEPSEEK_API_KEY")
        api_base = getattr(settings, "DEEPSEEK_API_BASE", "https://api.deepseek.com")
        
        if api_key and api_key not in ["", "your-"]:
            self.stdout.write(self.style.SUCCESS("   ✅ DeepSeek API Key: معرّف"))
            self.stdout.write(f"   ℹ️  API Base: {api_base}")
            self.stdout.write("   ℹ️  AI جاهز للرد على رسائل WhatsApp تلقائياً")
            return True
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  DeepSeek API Key: غير معرّف"))
            self.stdout.write("   ℹ️  احصل على API Key من: https://platform.deepseek.com/")
            self.stdout.write("   ℹ️  أضف إلى .env: DEEPSEEK_API_KEY=sk-your-key")
            return False
    
    def check_whatsapp(self):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  5. التحقق من إعدادات WhatsApp")
        self.stdout.write("=" * 60 + "\n")
        
        # Check test mode
        test_allowlist = os.getenv("WHATSAPP_TEST_ALLOWLIST")
        if test_allowlist:
            self.stdout.write(self.style.SUCCESS("   ✅ WhatsApp Test Mode: مفعّل"))
            self.stdout.write(f"   ℹ️  Allowlist: {test_allowlist}")
        else:
            self.stdout.write("   ℹ️  WhatsApp Test Mode: غير مفعّل (Production Mode)")
        
        # Check default sender
        default_sender = getattr(settings, "WHATSAPP_DEFAULT_SENDER", None) or os.getenv("WHATSAPP_DEFAULT_SENDER")
        if default_sender:
            self.stdout.write(self.style.SUCCESS(f"   ✅ WhatsApp Default Sender: {default_sender}"))
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  WhatsApp Default Sender: غير معرّف"))
        
        # Check clinic channels
        clinics_with_whatsapp = ChannelAccount.objects.filter(
            channel=ChannelType.WHATSAPP
        ).values_list("clinic_id", flat=True).distinct()
        
        total_clinics = Clinic.objects.count()
        clinics_with_whatsapp_count = len(clinics_with_whatsapp)
        
        self.stdout.write(f"\n   📊 العيادات مع WhatsApp: {clinics_with_whatsapp_count} / {total_clinics}")
        
        if clinics_with_whatsapp_count < total_clinics:
            self.stdout.write(self.style.WARNING(
                f"   ⚠️  {total_clinics - clinics_with_whatsapp_count} عيادة بدون WhatsApp Channel"
            ))
            self.stdout.write("   ℹ️  كل عيادة تحتاج WhatsApp Channel خاص بها")
        
        return clinics_with_whatsapp_count == total_clinics if total_clinics > 0 else False
    
    def check_google_calendar(self):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  6. التحقق من Google Calendar")
        self.stdout.write("=" * 60 + "\n")
        
        client_id = getattr(settings, "GOOGLE_CLIENT_ID", None) or os.getenv("GOOGLE_CLIENT_ID")
        client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", None) or os.getenv("GOOGLE_CLIENT_SECRET")
        redirect_uri = getattr(settings, "GOOGLE_REDIRECT_URI", None) or os.getenv("GOOGLE_REDIRECT_URI")
        
        if client_id and client_secret and redirect_uri:
            self.stdout.write(self.style.SUCCESS("   ✅ Google OAuth Credentials: معرّفة"))
            self.stdout.write(f"   ℹ️  Redirect URI: {redirect_uri}")
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  Google OAuth Credentials: غير معرّفة"))
            self.stdout.write("   ℹ️  احصل على Credentials من: https://console.cloud.google.com/")
        
        # Check connected clinics
        clinics_with_calendar = GoogleCredential.objects.values_list("clinic_id", flat=True).distinct()
        total_clinics = Clinic.objects.count()
        clinics_with_calendar_count = len(clinics_with_calendar)
        
        self.stdout.write(f"\n   📊 العيادات مع Google Calendar: {clinics_with_calendar_count} / {total_clinics}")
        
        if clinics_with_calendar_count < total_clinics:
            self.stdout.write(self.style.WARNING(
                f"   ⚠️  {total_clinics - clinics_with_calendar_count} عيادة بدون Google Calendar"
            ))
        
        return clinics_with_calendar_count == total_clinics if total_clinics > 0 else False
    
    def check_recent_activity(self):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  7. التحقق من النشاط الأخير")
        self.stdout.write("=" * 60 + "\n")
        
        from apps.appointments.models import Appointment
        from apps.leads.models import Conversation
        
        # Recent appointments
        recent_appointments = Appointment.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()
        self.stdout.write(f"   📅 المواعيد (آخر 7 أيام): {recent_appointments}")
        
        # Recent conversations
        recent_conversations = Conversation.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()
        self.stdout.write(f"   💬 المحادثات (آخر 7 أيام): {recent_conversations}")
        
        # Recent WhatsApp messages
        recent_messages = OutboxMessage.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7),
            channel=ChannelType.WHATSAPP
        ).count()
        self.stdout.write(f"   📱 رسائل WhatsApp (آخر 7 أيام): {recent_messages}")
        
        # Failed messages
        from apps.channels.models import OutboxStatus
        failed_messages = OutboxMessage.objects.filter(
            status=OutboxStatus.FAILED,
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()
        if failed_messages > 0:
            self.stdout.write(self.style.WARNING(f"   ❌ رسائل فاشلة (آخر 7 أيام): {failed_messages}"))
    
    def generate_summary(self, clinic_statuses, hq_ok, deepseek_ok, whatsapp_ok, calendar_ok):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  📊 ملخص المراجعة")
        self.stdout.write("=" * 60 + "\n")
        
        total_clinics = len(clinic_statuses)
        
        if total_clinics == 0:
            self.stdout.write(self.style.ERROR("   ❌ لا توجد عيادات في النظام!"))
            self.stdout.write("   ℹ️  الخطوة الأولى: أنشئ عيادة من HQ Portal")
            return
        
        # Calculate completion for each clinic
        fully_ready = 0
        partially_ready = 0
        not_ready = 0
        
        for status in clinic_statuses:
            completed = sum([
                status["services"],
                status["hours"],
                status["whatsapp"],
                status["google"],
                status["templates"],
            ])
            
            if completed == 5:
                fully_ready += 1
            elif completed >= 3:
                partially_ready += 1
            else:
                not_ready += 1
        
        self.stdout.write(f"\n🏥 حالة العيادات:")
        self.stdout.write(f"   ✅ جاهزة بالكامل: {fully_ready} / {total_clinics}")
        self.stdout.write(f"   ⚠️  جاهزة جزئياً: {partially_ready} / {total_clinics}")
        self.stdout.write(f"   ❌ غير جاهزة: {not_ready} / {total_clinics}")
        
        self.stdout.write(f"\n🔧 الإعدادات:")
        self.stdout.write(f"   {'✅' if hq_ok else '❌'} HQ Staff Users")
        self.stdout.write(f"   {'✅' if deepseek_ok else '⚠️ '} DeepSeek AI")
        self.stdout.write(f"   {'✅' if whatsapp_ok else '⚠️ '} WhatsApp Channels")
        self.stdout.write(f"   {'✅' if calendar_ok else '⚠️ '} Google Calendar")
        
        self.stdout.write("\n" + "=" * 60)
        
        if fully_ready == total_clinics and hq_ok and deepseek_ok and whatsapp_ok and calendar_ok:
            self.stdout.write(self.style.SUCCESS("🎉 كل شيء جاهز للتجربة الحقيقية!"))
        elif fully_ready > 0 or partially_ready > 0:
            self.stdout.write(self.style.SUCCESS("✅ بعض العيادات جاهزة، لكن تحتاج إلى إكمال الإعدادات"))
            self.stdout.write("\n⚠️  ما تبقى:")
            if not deepseek_ok:
                self.stdout.write("   - إعداد DeepSeek API Key")
            if not whatsapp_ok:
                self.stdout.write("   - إضافة WhatsApp Channel لكل عيادة")
            if not calendar_ok:
                self.stdout.write("   - ربط Google Calendar لكل عيادة")
        else:
            self.stdout.write(self.style.WARNING("⚠️  المشروع يحتاج إلى إعدادات إضافية"))
            self.stdout.write("\n📝 الخطوات التالية:")
            self.stdout.write("   1. أنشئ عيادة من HQ Portal")
            self.stdout.write("   2. أضف Services و Operating Hours")
            self.stdout.write("   3. أضف WhatsApp Channel")
            self.stdout.write("   4. اربط Google Calendar")
            self.stdout.write("   5. أضف Message Templates")
        
        self.stdout.write("\n" + "=" * 60 + "\n")

