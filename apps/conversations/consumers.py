from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Dict

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import User
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import ClinicMembership, StaffAccount, SupportSession
from apps.accounts.support import hash_support_token
from apps.clinics.models import Clinic
from apps.conversations.models import Conversation


class ConversationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.slug = self.scope["url_route"]["kwargs"]["slug"]
        self.conversation_id = int(self.scope["url_route"]["kwargs"]["conversation_id"])
        cookies = self._get_cookies()
        allowed = await self._authorize(self.slug, self.conversation_id, cookies)
        if not allowed:
            await self.close(code=4401)
            return
        self.group_name = f"clinic_{self.slug}_conversation_{self.conversation_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected"})

    async def disconnect(self, close_code: int) -> None:
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def conversation_message(self, event: dict) -> None:
        await self.send_json(
            {
                "type": "message",
                "conversation_id": event.get("conversation_id"),
                "message_id": event.get("message_id"),
                "direction": event.get("direction"),
                "created_at": event.get("created_at"),
            }
        )

    def _get_cookies(self) -> Dict[str, str]:
        raw_cookie = ""
        for key, value in self.scope.get("headers", []):
            if key == b"cookie":
                raw_cookie = value.decode("utf-8")
                break
        cookie = SimpleCookie()
        cookie.load(raw_cookie)
        return {key: morsel.value for key, morsel in cookie.items()}

    @database_sync_to_async
    def _authorize(self, slug: str, conversation_id: int, cookies: Dict[str, str]) -> bool:
        support_token = cookies.get("supportToken")
        support_clinic = cookies.get("supportClinicSlug")
        if support_token and support_clinic == slug:
            session = (
                SupportSession.objects.select_related("clinic", "staff_user")
                .filter(token_hash=hash_support_token(support_token), active=True)
                .first()
            )
            if not session or not session.is_active():
                return False
            return Conversation.objects.filter(id=conversation_id, clinic=session.clinic).exists()

        access_token = cookies.get("accessToken")
        if not access_token:
            return False

        try:
            token = AccessToken(access_token)
        except TokenError:
            return False

        try:
            user_id = token["user_id"]
        except KeyError:
            return False

        user = User.objects.filter(id=user_id).first()
        if not user:
            return False

        clinic = Clinic.objects.filter(slug=slug).first()
        if not clinic:
            return False

        staff = StaffAccount.objects.filter(user=user).first()
        if staff and staff.role in (StaffAccount.Role.SUPERADMIN, StaffAccount.Role.OPS):
            return Conversation.objects.filter(id=conversation_id, clinic=clinic).exists()

        if not ClinicMembership.objects.filter(user=user, clinic=clinic).exists():
            return False

        return Conversation.objects.filter(id=conversation_id, clinic=clinic).exists()
