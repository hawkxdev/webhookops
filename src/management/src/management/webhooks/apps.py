"""Конфигурация приложения вебхуков."""

from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    """Приложение приёма и доставки."""

    name = 'management.webhooks'
    verbose_name = 'Вебхуки'
