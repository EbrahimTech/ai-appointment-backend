#!/usr/bin/env python
"""
Script to verify complete real-world setup for clinics
Checks: Environment variables, Clinics, WhatsApp channels, Google Calendar, DeepSeek AI
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from django.conf import settings
from apps.clinics.models import Clinic
from apps.accounts.models import User, ClinicMembership, StaffAccount
from apps.channels.models import ChannelAccount, ChannelType
from apps.calendars.models import GoogleCredential
from apps.services.models import Service, ServiceHours
from apps.channels.models import HSMTemplate, HSMTemplateStatus
from apps.appointments.models import Appointment
from apps.leads.models import Lead, Conversation
from apps.channels.models import OutboxMessage, OutboxStatus
from datetime import timedelta
from django.utils import timezone

def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_success(text):
    print(f"✅ {text}")

def print_warning(text):
    print(f"⚠️  {text}")

def print_error(text):
    print(f"❌ {text}")

def print_info(text):
    print(f"ℹ️  {text}")

def check_env_variables():
    """Check required and optional environment variables"""
    print_header("1. التحقق من Environment Variables")
    
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
    
    all_ok = True
    
    print("\n📋 المتغيرات المطلوبة:")
    for var, desc in required.items():
        value = getattr(settings, var, None) or os.getenv(var)
        if value and value not in ["", "your-", "change-in-production"]:
            print_success(f"{var}: معرّف ({desc})")
        else:
            print_error(f"{var}: غير معرّف ({desc})")
            all_ok = False
    
    print("\n📋 المتغيرات الاختيارية (للتجربة الحقيقية):")
    optional_count = 0
    for var, desc in optional.items():
        value = getattr(settings, var, None) or os.getenv(var)
        if value and value not in ["", "your-"]:
            print_success(f"{var}: معرّف ({desc})")
            optional_count += 1
        else:
            print_warning(f"{var}: غير معرّف ({desc})")
    
    return all_ok, optional_count

def check_clinics():
    """Check all clinics and their setup status"""
    print_header("2. التحقق من العيادات")
    
    clinics = Clinic.objects.all()
    total = clinics.count()
    
    if total == 0:
        print_warning("لا توجد عيادات في النظام")
        print_info("قم بإنشاء عيادة من HQ Portal: /hq")
        return []
    
    print_success(f"عدد العيادات: {total}")
    print()
    
    clinic_statuses = []
    
    for clinic in clinics:
        print(f"\n🏥 العيادة: {clinic.name} ({clinic.slug})")
        print(f"   ID: {clinic.id}")
        print(f"   Email: {clinic.owner.email if clinic.owner else 'N/A'}")
        print(f"   Phone: {clinic.phone_number or 'N/A'}")
        print(f"   WhatsApp: {clinic.whatsapp_number or 'N/A'}")
        
        status = {
            "clinic": clinic,
            "services": False,
            "hours": False,
            "whatsapp": False,
            "google": False,
            "templates": False,
            "users": False,
        }
        
        # Check Services
        services_count = clinic.services.filter(is_active=True).count()
        if services_count > 0:
            print_success(f"   Services: {services_count} خدمة")
            status["services"] = True
        else:
            print_warning("   Services: لا توجد خدمات")
        
        # Check Service Hours
        hours_count = ServiceHours.objects.filter(service__clinic=clinic).count()
        if hours_count > 0:
            print_success(f"   Operating Hours: {hours_count} ساعة عمل")
            status["hours"] = True
        else:
            print_warning("   Operating Hours: غير معرّفة")
        
        # Check WhatsApp Channel
        whatsapp_account = ChannelAccount.objects.filter(
            clinic=clinic,
            channel=ChannelType.WHATSAPP
        ).first()
        
        if whatsapp_account:
            provider = whatsapp_account.provider_name
            metadata = whatsapp_account.metadata or {}
            phone = metadata.get("phone_number_id") or metadata.get("from_number") or "N/A"
            print_success(f"   WhatsApp: متصل ({provider}) - {phone}")
            status["whatsapp"] = True
            
            # Check recent messages
            recent = OutboxMessage.objects.filter(
                clinic=clinic,
                channel=ChannelType.WHATSAPP,
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count()
            if recent > 0:
                print_info(f"   WhatsApp Messages (آخر 7 أيام): {recent}")
        else:
            print_warning("   WhatsApp: غير متصل")
            print_info("   قم بإضافة WhatsApp Channel من: /c/{}/integrations".format(clinic.slug))
        
        # Check Google Calendar
        google_cred = GoogleCredential.objects.filter(clinic=clinic).first()
        if google_cred:
            print_success(f"   Google Calendar: متصل ({google_cred.account_email})")
            status["google"] = True
        else:
            print_warning("   Google Calendar: غير متصل")
            print_info("   قم بربط Google Calendar من: /c/{}/integrations".format(clinic.slug))
        
        # Check Templates
        templates_count = HSMTemplate.objects.filter(
            clinic=clinic,
            status=HSMTemplateStatus.APPROVED
        ).count()
        if templates_count > 0:
            print_success(f"   Message Templates: {templates_count} قالب")
            status["templates"] = True
        else:
            print_warning("   Message Templates: لا توجد قوالب")
        
        # Check Users
        users_count = ClinicMembership.objects.filter(clinic=clinic).count()
        if users_count > 1:
            print_success(f"   Users: {users_count} مستخدم")
            status["users"] = True
        else:
            print_warning(f"   Users: {users_count} مستخدم فقط (Owner فقط)")
        
        clinic_statuses.append(status)
    
    return clinic_statuses

def check_hq_users():
    """Check HQ staff users"""
    print_header("3. التحقق من HQ Staff")
    
    hq_staff = StaffAccount.objects.all()
    count = hq_staff.count()
    
    if count == 0:
        print_warning("لا يوجد HQ Staff في النظام")
        print_info("قم بإنشاء HQ User: make local-create-user")
        return False
    
    print_success(f"عدد HQ Staff: {count}")
    print()
    
    for staff in hq_staff:
        role = staff.role
        user = staff.user
        print(f"   👤 {user.email} ({role})")
    
    return True

def check_deepseek():
    """Check DeepSeek AI configuration"""
    print_header("4. التحقق من DeepSeek AI")
    
    api_key = getattr(settings, "DEEPSEEK_API_KEY", None) or os.getenv("DEEPSEEK_API_KEY")
    api_base = getattr(settings, "DEEPSEEK_API_BASE", "https://api.deepseek.com")
    
    if api_key and api_key not in ["", "your-"]:
        print_success(f"DeepSeek API Key: معرّف")
        print_info(f"API Base: {api_base}")
        print_info("AI جاهز للرد على رسائل WhatsApp تلقائياً")
        return True
    else:
        print_warning("DeepSeek API Key: غير معرّف")
        print_info("احصل على API Key من: https://platform.deepseek.com/")
        print_info("أضف إلى .env: DEEPSEEK_API_KEY=sk-your-key")
        return False

def check_whatsapp_setup():
    """Check WhatsApp setup for all clinics"""
    print_header("5. التحقق من إعدادات WhatsApp")
    
    # Check test mode
    test_allowlist = os.getenv("WHATSAPP_TEST_ALLOWLIST")
    if test_allowlist:
        print_success("WhatsApp Test Mode: مفعّل")
        print_info(f"Allowlist: {test_allowlist}")
    else:
        print_info("WhatsApp Test Mode: غير مفعّل (Production Mode)")
    
    # Check default sender
    default_sender = getattr(settings, "WHATSAPP_DEFAULT_SENDER", None) or os.getenv("WHATSAPP_DEFAULT_SENDER")
    if default_sender:
        print_success(f"WhatsApp Default Sender: {default_sender}")
    else:
        print_warning("WhatsApp Default Sender: غير معرّف")
    
    # Check clinic channels
    clinics_with_whatsapp = ChannelAccount.objects.filter(
        channel=ChannelType.WHATSAPP
    ).values_list("clinic_id", flat=True).distinct()
    
    total_clinics = Clinic.objects.count()
    clinics_with_whatsapp_count = len(clinics_with_whatsapp)
    
    print()
    print(f"📊 العيادات مع WhatsApp: {clinics_with_whatsapp_count} / {total_clinics}")
    
    if clinics_with_whatsapp_count < total_clinics:
        print_warning(f"⚠️  {total_clinics - clinics_with_whatsapp_count} عيادة بدون WhatsApp Channel")
        print_info("كل عيادة تحتاج WhatsApp Channel خاص بها")
    
    return clinics_with_whatsapp_count == total_clinics if total_clinics > 0 else False

def check_google_calendar():
    """Check Google Calendar setup"""
    print_header("6. التحقق من Google Calendar")
    
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", None) or os.getenv("GOOGLE_CLIENT_ID")
    client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", None) or os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = getattr(settings, "GOOGLE_REDIRECT_URI", None) or os.getenv("GOOGLE_REDIRECT_URI")
    
    if client_id and client_secret and redirect_uri:
        print_success("Google OAuth Credentials: معرّفة")
        print_info(f"Redirect URI: {redirect_uri}")
    else:
        print_warning("Google OAuth Credentials: غير معرّفة")
        print_info("احصل على Credentials من: https://console.cloud.google.com/")
    
    # Check connected clinics
    clinics_with_calendar = GoogleCredential.objects.values_list("clinic_id", flat=True).distinct()
    total_clinics = Clinic.objects.count()
    clinics_with_calendar_count = len(clinics_with_calendar)
    
    print()
    print(f"📊 العيادات مع Google Calendar: {clinics_with_calendar_count} / {total_clinics}")
    
    if clinics_with_calendar_count < total_clinics:
        print_warning(f"⚠️  {total_clinics - clinics_with_calendar_count} عيادة بدون Google Calendar")
    
    return clinics_with_calendar_count == total_clinics if total_clinics > 0 else False

def check_recent_activity():
    """Check recent activity (appointments, conversations, messages)"""
    print_header("7. التحقق من النشاط الأخير")
    
    # Recent appointments
    recent_appointments = Appointment.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    ).count()
    print(f"📅 المواعيد (آخر 7 أيام): {recent_appointments}")
    
    # Recent conversations
    recent_conversations = Conversation.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    ).count()
    print(f"💬 المحادثات (آخر 7 أيام): {recent_conversations}")
    
    # Recent WhatsApp messages
    recent_messages = OutboxMessage.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7),
        channel=ChannelType.WHATSAPP
    ).count()
    print(f"📱 رسائل WhatsApp (آخر 7 أيام): {recent_messages}")
    
    # Failed messages
    failed_messages = OutboxMessage.objects.filter(
        status=OutboxStatus.FAILED,
        created_at__gte=timezone.now() - timedelta(days=7)
    ).count()
    if failed_messages > 0:
        print_warning(f"❌ رسائل فاشلة (آخر 7 أيام): {failed_messages}")

def generate_summary(clinic_statuses, env_ok, optional_count, hq_ok, deepseek_ok, whatsapp_ok, calendar_ok):
    """Generate final summary"""
    print_header("📊 ملخص المراجعة")
    
    total_clinics = len(clinic_statuses)
    
    if total_clinics == 0:
        print_error("لا توجد عيادات في النظام!")
        print_info("الخطوة الأولى: أنشئ عيادة من HQ Portal")
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
    
    print(f"\n🏥 حالة العيادات:")
    print(f"   ✅ جاهزة بالكامل: {fully_ready} / {total_clinics}")
    print(f"   ⚠️  جاهزة جزئياً: {partially_ready} / {total_clinics}")
    print(f"   ❌ غير جاهزة: {not_ready} / {total_clinics}")
    
    print(f"\n🔧 الإعدادات:")
    print(f"   {'✅' if env_ok else '❌'} Environment Variables الأساسية")
    print(f"   {'✅' if hq_ok else '❌'} HQ Staff Users")
    print(f"   {'✅' if deepseek_ok else '⚠️ '} DeepSeek AI")
    print(f"   {'✅' if whatsapp_ok else '⚠️ '} WhatsApp Channels")
    print(f"   {'✅' if calendar_ok else '⚠️ '} Google Calendar")
    
    print(f"\n📋 المتغيرات الاختيارية: {optional_count} / 6")
    
    print("\n" + "=" * 60)
    
    if fully_ready == total_clinics and env_ok and hq_ok and deepseek_ok and whatsapp_ok and calendar_ok:
        print("🎉 كل شيء جاهز للتجربة الحقيقية!")
    elif fully_ready > 0 or partially_ready > 0:
        print("✅ بعض العيادات جاهزة، لكن تحتاج إلى إكمال الإعدادات")
        print("\n⚠️  ما تبقى:")
        if not deepseek_ok:
            print("   - إعداد DeepSeek API Key")
        if not whatsapp_ok:
            print("   - إضافة WhatsApp Channel لكل عيادة")
        if not calendar_ok:
            print("   - ربط Google Calendar لكل عيادة")
    else:
        print("⚠️  المشروع يحتاج إلى إعدادات إضافية")
        print("\n📝 الخطوات التالية:")
        print("   1. أنشئ عيادة من HQ Portal")
        print("   2. أضف Services و Operating Hours")
        print("   3. أضف WhatsApp Channel")
        print("   4. اربط Google Calendar")
        print("   5. أضف Message Templates")
    
    print("\n" + "=" * 60)

def main():
    print("\n" + "=" * 60)
    print("  🔍 مراجعة شاملة لإعدادات المشروع للتجربة الحقيقية")
    print("=" * 60)
    
    # Run all checks
    env_ok, optional_count = check_env_variables()
    clinic_statuses = check_clinics()
    hq_ok = check_hq_users()
    deepseek_ok = check_deepseek()
    whatsapp_ok = check_whatsapp_setup()
    calendar_ok = check_google_calendar()
    check_recent_activity()
    
    # Generate summary
    generate_summary(
        clinic_statuses,
        env_ok,
        optional_count,
        hq_ok,
        deepseek_ok,
        whatsapp_ok,
        calendar_ok
    )
    
    print("\n")

if __name__ == "__main__":
    main()

