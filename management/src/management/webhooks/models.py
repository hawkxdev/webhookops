"""Доменные модели вебхуков."""

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
    # Статусы добавятся вместе с реализацией публикатора.


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


class DeliveryAttemptStatus(models.TextChoices):
    """Статусы попыток доставки."""

    STARTED = 'started', 'Начата'
    SUCCEEDED = 'succeeded', 'Завершена успешно'
    FAILED = 'failed', 'Завершена с ошибкой'


class DeliveryAttempt(models.Model):
    """Попытка доставки сообщения."""

    status = models.CharField(
        max_length=20,
        choices=DeliveryAttemptStatus.choices,
        default=DeliveryAttemptStatus.STARTED,
        verbose_name='Статус попытки',
    )

    attempt_no = models.PositiveSmallIntegerField(
        verbose_name='Номер попытки',
    )

    started_at = models.DateTimeField(auto_now_add=True, verbose_name='Начата')

    http_status = models.PositiveSmallIntegerField(
        null=True,
        verbose_name='Статус ответа',
    )

    error = models.CharField(max_length=100, verbose_name='Причина отказа')

    finished_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Завершено'
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        db_index=False,
        related_name='delivery_attempts',
        verbose_name='Событие',
    )

    subscriber = models.ForeignKey(
        Subscriber,
        on_delete=models.PROTECT,
        related_name='delivery_attempts',
        verbose_name='Подписчик',
    )

    class Meta:
        verbose_name = 'Попытка доставки сообщения'
        verbose_name_plural = 'Попытки доставки сообщений'
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'subscriber', 'attempt_no'],
                name='uniq_delivery_attempt_number',
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_no__gte=1),
                name='delivery_attempt_no_gte_1',
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=DeliveryAttemptStatus.values),
                name='delivery_attempt_status_valid',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=DeliveryAttemptStatus.STARTED,
                        finished_at__isnull=True,
                    )
                    | models.Q(
                        status__in=[
                            DeliveryAttemptStatus.SUCCEEDED,
                            DeliveryAttemptStatus.FAILED,
                        ],
                        finished_at__isnull=False,
                    )
                ),
                name='delivery_attempt_completion_consistent',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(http_status__isnull=True)
                    | models.Q(http_status__gte=100, http_status__lte=599)
                ),
                name='delivery_attempt_http_status_valid',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=DeliveryAttemptStatus.STARTED,
                        http_status__isnull=True,
                        error='',
                    )
                    | models.Q(
                        status=DeliveryAttemptStatus.SUCCEEDED,
                        http_status__isnull=False,
                        error='',
                    )
                    | (
                        models.Q(status=DeliveryAttemptStatus.FAILED)
                        & (
                            models.Q(http_status__isnull=False)
                            | ~models.Q(error='')
                        )
                    )
                ),
                name='delivery_attempt_result_consistent',
            ),
        ]

    def __str__(self):
        """Описание попытки доставки."""
        return f'{self.event} {self.subscriber} {self.attempt_no}'
