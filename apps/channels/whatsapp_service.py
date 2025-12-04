"""WhatsApp service layer for sending messages."""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings

from apps.channels.models import ChannelAccount, HSMTemplate, MessageType, OutboxMessage
from apps.channels.whatsapp_providers import (
    GenericWhatsAppProvider,
    MetaWhatsAppProvider,
    TwilioWhatsAppProvider,
    WhatsAppProvider,
    WhatsAppMessageResult,
)
from apps.clinics.models import Clinic
from apps.patients.models import Patient

logger = logging.getLogger(__name__)


class WhatsAppServiceError(Exception):
    """Raised when WhatsApp service operations fail."""
    pass


class WhatsAppService:
    """Service for sending WhatsApp messages via configured providers."""
    
    def __init__(self):
        self.provider_cache: dict[str, WhatsAppProvider] = {}
    
    def _get_provider(self, clinic: Clinic) -> tuple[WhatsAppProvider, ChannelAccount]:
        """Get WhatsApp provider for a clinic."""
        cache_key = f"{clinic.id}-whatsapp"
        
        if cache_key in self.provider_cache:
            account = ChannelAccount.objects.filter(
                clinic=clinic,
                channel="whatsapp",
            ).first()
            if account:
                return self.provider_cache[cache_key], account
        
        # Get or create channel account
        account = ChannelAccount.objects.filter(
            clinic=clinic,
            channel="whatsapp",
        ).first()
        
        if not account:
            raise WhatsAppServiceError(
                f"No WhatsApp channel account configured for clinic {clinic.slug}"
            )
        
        # Create provider based on provider_name
        provider_name = account.provider_name.lower()
        metadata = account.metadata or {}
        
        if provider_name == "meta" or provider_name == "facebook":
            phone_number_id = metadata.get("phone_number_id") or settings.WHATSAPP_DEFAULT_SENDER
            api_version = metadata.get("api_version", "v18.0")
            provider = MetaWhatsAppProvider(phone_number_id=phone_number_id, api_version=api_version)
        elif provider_name == "twilio":
            account_sid = metadata.get("account_sid") or account.access_token
            auth_token = account.refresh_token or account.access_token
            from_number = metadata.get("from_number") or settings.WHATSAPP_DEFAULT_SENDER
            provider = TwilioWhatsAppProvider(
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number,
            )
        elif provider_name == "generic":
            api_url = metadata.get("api_url") or getattr(settings, "WHATSAPP_API_URL", "")
            api_key = account.access_token
            provider = GenericWhatsAppProvider(api_url=api_url, api_key=api_key)
        else:
            # Default to generic
            logger.warning(
                f"Unknown provider '{provider_name}', using generic provider",
                extra={"clinic_id": clinic.id, "provider_name": provider_name},
            )
            api_url = metadata.get("api_url") or getattr(settings, "WHATSAPP_API_URL", "")
            api_key = account.access_token
            provider = GenericWhatsAppProvider(api_url=api_url, api_key=api_key)
        
        # Cache provider
        self.provider_cache[cache_key] = provider
        return provider, account
    
    def send_message(self, outbox: OutboxMessage) -> WhatsAppMessageResult:
        """Send a message from outbox via WhatsApp provider."""
        clinic = outbox.clinic
        
        # Get recipient phone number
        to_phone = None
        if outbox.conversation and outbox.conversation.patient:
            to_phone = outbox.conversation.patient.phone_number
        elif outbox.payload.get("to"):
            to_phone = outbox.payload.get("to")
        elif outbox.metadata and outbox.metadata.get("sandbox_to"):
            # For test messages, check metadata
            to_phone = outbox.metadata.get("sandbox_to")
        
        if not to_phone:
            return WhatsAppMessageResult(
                success=False,
                error="No recipient phone number found",
            )
        
        # Normalize phone number (remove whatsapp: prefix if present)
        to_phone = to_phone.replace("whatsapp:", "").strip()
        # Ensure phone starts with +
        if not to_phone.startswith("+"):
            # Remove leading zeros and add +
            to_phone = to_phone.lstrip("0")
            if not to_phone.startswith("+"):
                to_phone = f"+{to_phone}"
        
        try:
            provider, account = self._get_provider(clinic)
        except WhatsAppServiceError as exc:
            return WhatsAppMessageResult(
                success=False,
                error=str(exc),
            )
        
        access_token = account.access_token
        
        # Send based on message type
        if outbox.message_type == MessageType.SESSION:
            message_body = outbox.payload.get("body", "")
            if not message_body:
                return WhatsAppMessageResult(
                    success=False,
                    error="Session message body is empty",
                )
            
            result = provider.send_session_message(
                to=to_phone,
                message_body=message_body,
                access_token=access_token,
            )
        
        elif outbox.message_type == MessageType.HSM:
            if not outbox.hsm_template:
                return WhatsAppMessageResult(
                    success=False,
                    error="HSM template is missing",
                )
            
            template_id = (
                outbox.hsm_template.provider_template_id
                or outbox.payload.get("template_id")
                or outbox.hsm_template.name
            )
            
            template_body = outbox.hsm_template.body
            variables = outbox.metadata.get("variables", {}) or outbox.payload.get("variables", {})
            
            result = provider.send_hsm_template(
                to=to_phone,
                template_id=template_id,
                template_body=template_body,
                variables=variables,
                access_token=access_token,
            )
        
        else:
            return WhatsAppMessageResult(
                success=False,
                error=f"Unknown message type: {outbox.message_type}",
            )
        
        # Log result
        if result.success:
            logger.info(
                "WhatsApp message sent successfully",
                extra={
                    "outbox_id": outbox.id,
                    "clinic_id": clinic.id,
                    "provider_message_id": result.provider_message_id,
                    "message_type": outbox.message_type,
                },
            )
        else:
            logger.warning(
                "WhatsApp message send failed",
                extra={
                    "outbox_id": outbox.id,
                    "clinic_id": clinic.id,
                    "error": result.error,
                    "status_code": result.status_code,
                    "message_type": outbox.message_type,
                },
            )
        
        return result


# Global service instance
_whatsapp_service: Optional[WhatsAppService] = None


def get_whatsapp_service() -> WhatsAppService:
    """Get or create global WhatsApp service instance."""
    global _whatsapp_service
    if _whatsapp_service is None:
        _whatsapp_service = WhatsAppService()
    return _whatsapp_service

