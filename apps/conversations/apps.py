from django.apps import AppConfig


class ConversationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.conversations'

    def ready(self) -> None:
        from apps.conversations import signals  # noqa: F401
