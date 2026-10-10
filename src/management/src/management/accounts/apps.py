"""Конфигурация приложения учётных записей."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Приложение учётных записей."""

    name = 'management.accounts'
    verbose_name = 'Учётные записи'
