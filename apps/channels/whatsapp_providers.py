"""WhatsApp provider interfaces and implementations."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppMessageResult:
    """Result of sending a WhatsApp message."""
    
    success: bool
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    status_code: Optional[int] = None


class WhatsAppProvider(ABC):
    """Base class for WhatsApp providers."""
    
    @abstractmethod
    def send_session_message(
        self,
        *,
        to: str,
        message_body: str,
        access_token: str,
    ) -> WhatsAppMessageResult:
        """Send a session message (within 24h window)."""
        pass
    
    @abstractmethod
    def send_hsm_template(
        self,
        *,
        to: str,
        template_id: str,
        template_body: str,
        variables: dict[str, str],
        access_token: str,
    ) -> WhatsAppMessageResult:
        """Send an HSM template message."""
        pass


class MetaWhatsAppProvider(WhatsAppProvider):
    """Meta (Facebook) WhatsApp Business API provider."""
    
    def __init__(self, phone_number_id: str, api_version: str = "v18.0"):
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{api_version}"
    
    def send_session_message(
        self,
        *,
        to: str,
        message_body: str,
        access_token: str,
    ) -> WhatsAppMessageResult:
        """Send a session message via Meta API."""
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message_body},
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            message_id = data.get("messages", [{}])[0].get("id")
            
            return WhatsAppMessageResult(
                success=True,
                provider_message_id=message_id,
                status_code=response.status_code,
            )
        except requests.exceptions.RequestException as exc:
            error_msg = str(exc)
            status_code = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
            
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_data = exc.response.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except Exception:
                    pass
            
            logger.error(
                "Meta WhatsApp API error",
                extra={
                    "to": to,
                    "error": error_msg,
                    "status_code": status_code,
                },
            )
            
            return WhatsAppMessageResult(
                success=False,
                error=error_msg,
                status_code=status_code,
            )
    
    def send_hsm_template(
        self,
        *,
        to: str,
        template_id: str,
        template_body: str,
        variables: dict[str, str],
        access_token: str,
    ) -> WhatsAppMessageResult:
        """Send an HSM template via Meta API."""
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        # Convert variables dict to Meta format
        components = []
        if variables:
            params = [{"type": "text", "text": str(value)} for value in variables.values()]
            components.append({"type": "body", "parameters": params})
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_id,
                "language": {"code": "en"},  # Default, should be configurable
                "components": components if components else None,
            },
        }
        
        # Remove None values
        if payload["template"]["components"] is None:
            del payload["template"]["components"]
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            message_id = data.get("messages", [{}])[0].get("id")
            
            return WhatsAppMessageResult(
                success=True,
                provider_message_id=message_id,
                status_code=response.status_code,
            )
        except requests.exceptions.RequestException as exc:
            error_msg = str(exc)
            status_code = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
            
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_data = exc.response.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except Exception:
                    pass
            
            logger.error(
                "Meta WhatsApp HSM API error",
                extra={
                    "to": to,
                    "template_id": template_id,
                    "error": error_msg,
                    "status_code": status_code,
                },
            )
            
            return WhatsAppMessageResult(
                success=False,
                error=error_msg,
                status_code=status_code,
            )


class TwilioWhatsAppProvider(WhatsAppProvider):
    """Twilio WhatsApp provider."""
    
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"
    
    def send_session_message(
        self,
        *,
        to: str,
        message_body: str,
        access_token: str,  # Not used for Twilio, but required by interface
    ) -> WhatsAppMessageResult:
        """Send a session message via Twilio API."""
        url = f"{self.base_url}/Messages.json"
        auth = (self.account_sid, self.auth_token)
        data = {
            "From": f"whatsapp:{self.from_number}",
            "To": f"whatsapp:{to}",
            "Body": message_body,
        }
        
        try:
            response = requests.post(url, data=data, auth=auth, timeout=15)
            response.raise_for_status()
            data = response.json()
            message_id = data.get("sid")
            
            return WhatsAppMessageResult(
                success=True,
                provider_message_id=message_id,
                status_code=response.status_code,
            )
        except requests.exceptions.RequestException as exc:
            error_msg = str(exc)
            status_code = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
            
            logger.error(
                "Twilio WhatsApp API error",
                extra={
                    "to": to,
                    "error": error_msg,
                    "status_code": status_code,
                },
            )
            
            return WhatsAppMessageResult(
                success=False,
                error=error_msg,
                status_code=status_code,
            )
    
    def send_hsm_template(
        self,
        *,
        to: str,
        template_id: str,
        template_body: str,
        variables: dict[str, str],
        access_token: str,  # Not used for Twilio, but required by interface
    ) -> WhatsAppMessageResult:
        """Send an HSM template via Twilio API."""
        # Twilio uses ContentSid for templates
        url = f"{self.base_url}/Messages.json"
        auth = (self.account_sid, self.auth_token)
        
        # Render template with variables
        rendered_body = template_body
        for key, value in variables.items():
            rendered_body = rendered_body.replace(f"{{{{{key}}}}}", str(value))
        
        data = {
            "From": f"whatsapp:{self.from_number}",
            "To": f"whatsapp:{to}",
            "ContentSid": template_id,  # Twilio Content Template SID
        }
        
        # Add variables if needed
        if variables:
            for idx, (key, value) in enumerate(variables.items(), 1):
                data[f"ContentVariables{idx}"] = value
        
        try:
            response = requests.post(url, data=data, auth=auth, timeout=15)
            response.raise_for_status()
            data = response.json()
            message_id = data.get("sid")
            
            return WhatsAppMessageResult(
                success=True,
                provider_message_id=message_id,
                status_code=response.status_code,
            )
        except requests.exceptions.RequestException as exc:
            error_msg = str(exc)
            status_code = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
            
            logger.error(
                "Twilio WhatsApp HSM API error",
                extra={
                    "to": to,
                    "template_id": template_id,
                    "error": error_msg,
                    "status_code": status_code,
                },
            )
            
            return WhatsAppMessageResult(
                success=False,
                error=error_msg,
                status_code=status_code,
            )


class GenericWhatsAppProvider(WhatsAppProvider):
    """Generic provider for testing or custom implementations."""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
    
    def send_session_message(
        self,
        *,
        to: str,
        message_body: str,
        access_token: str,
    ) -> WhatsAppMessageResult:
        """Send a session message via generic API."""
        url = f"{self.api_url}/messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "to": to,
            "message": message_body,
            "type": "session",
        }
        
        try:
            # Check if this is a test/simulated endpoint
            if "localhost" in self.api_url or "test" in self.api_url.lower():
                # Simulate successful send for testing
                import uuid
                simulated_id = f"sim-{uuid.uuid4().hex[:12]}"
                logger.info(
                    "Simulated WhatsApp session send (test mode)",
                    extra={
                        "to": to,
                        "simulated_id": simulated_id,
                    },
                )
                return WhatsAppMessageResult(
                    success=True,
                    provider_message_id=simulated_id,
                    status_code=200,
                )
            
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            message_id = data.get("message_id") or data.get("id")
            
            return WhatsAppMessageResult(
                success=True,
                provider_message_id=message_id,
                status_code=response.status_code,
            )
        except requests.exceptions.RequestException as exc:
            error_msg = str(exc)
            status_code = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
            
            logger.error(
                "Generic WhatsApp API error",
                extra={
                    "to": to,
                    "error": error_msg,
                    "status_code": status_code,
                },
            )
            
            return WhatsAppMessageResult(
                success=False,
                error=error_msg,
                status_code=status_code,
            )
    
    def send_hsm_template(
        self,
        *,
        to: str,
        template_id: str,
        template_body: str,
        variables: dict[str, str],
        access_token: str,
    ) -> WhatsAppMessageResult:
        """Send an HSM template via generic API."""
        url = f"{self.api_url}/templates"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "to": to,
            "template_id": template_id,
            "template_body": template_body,
            "variables": variables,
        }
        
        try:
            # Check if this is a test/simulated endpoint
            if "localhost" in self.api_url or "test" in self.api_url.lower():
                # Simulate successful send for testing
                import uuid
                simulated_id = f"sim-{uuid.uuid4().hex[:12]}"
                logger.info(
                    "Simulated WhatsApp HSM send (test mode)",
                    extra={
                        "to": to,
                        "template_id": template_id,
                        "simulated_id": simulated_id,
                    },
                )
                return WhatsAppMessageResult(
                    success=True,
                    provider_message_id=simulated_id,
                    status_code=200,
                )
            
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            message_id = data.get("message_id") or data.get("id")
            
            return WhatsAppMessageResult(
                success=True,
                provider_message_id=message_id,
                status_code=response.status_code,
            )
        except requests.exceptions.RequestException as exc:
            error_msg = str(exc)
            status_code = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
            
            logger.error(
                "Generic WhatsApp HSM API error",
                extra={
                    "to": to,
                    "template_id": template_id,
                    "error": error_msg,
                    "status_code": status_code,
                },
            )
            
            return WhatsAppMessageResult(
                success=False,
                error=error_msg,
                status_code=status_code,
            )

