from django.urls import path

from apps.appointments.views import appointments_today
from apps.calendars.views import google_oauth_callback, google_oauth_start
from apps.channels.views import whatsapp_delivery_receipt, whatsapp_webhook
from apps.webhooks.views import lead_webhook
from apps.http_api.views import metrics_summary

urlpatterns = [
    path('webhooks/lead', lead_webhook, name='lead-webhook'),
    path('channels/whatsapp/webhook', whatsapp_webhook, name='whatsapp-webhook'),
    path('channels/whatsapp/delivery', whatsapp_delivery_receipt, name='whatsapp-delivery'),
    path('calendars/google/start', google_oauth_start, name='google-oauth-start'),
    path('calendars/google/callback', google_oauth_callback, name='google-oauth-callback'),
    path('appointments/today', appointments_today, name='appointments-today'),
    path('metrics/summary', metrics_summary, name='metrics-summary'),
]

