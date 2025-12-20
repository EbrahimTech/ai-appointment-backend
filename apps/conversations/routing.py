from django.urls import path

from apps.conversations.consumers import ConversationConsumer

websocket_urlpatterns = [
    path(
        "ws/clinic/<slug:slug>/conversations/<int:conversation_id>/",
        ConversationConsumer.as_asgi(),
    ),
]
