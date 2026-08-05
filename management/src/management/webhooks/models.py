"""Модели вебхуков."""

from django.core.validators import URLValidator
from django.db import models


class Event(models.Model):
    """Принятое событие вебхука."""

    source = models.CharField(max_length=50, verbose_name='Источник')
    idempotency_key = models.CharField(
        max_length=255, verbose_name='Ключ идемпотентности'
    )
    payload = models.JSONField(verbose_name='Тело вебхука')
    received_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Получено'
    )

    class Meta:
        verbose_name = 'Событие'
        verbose_name_plural = 'События'
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'idempotency_key'],
                name='uniq_event_source_idempotency_key',
            )
        ]

    def __str__(self):
        """Источник и ключ."""
        return f'{self.source} - {self.idempotency_key}'


class OutboxStatus(models.TextChoices):
    """Статусы исходящего сообщения."""

    PENDING = 'pending', 'Ожидает отправки'
    # позже DISPATCHED, FAILED, DEAD


class OutboxMessage(models.Model):
    """Заявка на публикацию события."""

    status = models.CharField(
        max_length=20,
        choices=OutboxStatus.choices,
        default=OutboxStatus.PENDING,
        verbose_name='Статус',
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Создано'
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='outbox_messages',
        verbose_name='Событие',
    )

    class Meta:
        verbose_name = 'Исходящее сообщение'
        verbose_name_plural = 'Исходящие сообщения'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=OutboxStatus.values),
                name='outbox_status_valid',
            )
        ]

    def __str__(self):
        """Статус и время."""
        return f'{self.status} - {self.created_at}'


class Subscriber(models.Model):
    """Получатель доставленных событий."""

    name = models.CharField(max_length=50, verbose_name='Имя')
    target_url = models.URLField(
        verbose_name='URL',
        validators=[URLValidator(schemes=['https', 'http'])],
    )
    is_active = models.BooleanField(verbose_name='Активный', default=True)
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Создано'
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Подписчик'
        verbose_name_plural = 'Подписчики'
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                name='uniq_subscriber_name',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(target_url__startswith='https://')
                    | models.Q(target_url__startswith='http://')
                ),
                name='subscriber_target_url_scheme',
            ),
        ]

    def __str__(self):
        """Имя подписчика."""
        return self.name
