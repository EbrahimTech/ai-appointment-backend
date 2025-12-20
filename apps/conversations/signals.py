from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.conversations.models import ConversationMessage


@receiver(post_save, sender=ConversationMessage)
def broadcast_conversation_message(sender, instance: ConversationMessage, created: bool, **kwargs) -> None:
    if not created:
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    conversation = instance.conversation
    group_name = f"clinic_{conversation.clinic.slug}_conversation_{conversation.id}"
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "conversation.message",
            "conversation_id": conversation.id,
            "message_id": instance.id,
            "direction": instance.direction,
            "created_at": instance.created_at.isoformat(),
        },
    )
