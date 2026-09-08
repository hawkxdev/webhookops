"""Webhook domain models."""

from django.core.validators import URLValidator
from django.db import models


class Event(models.Model):
    """Accepted webhook event."""

    source = models.CharField(max_length=50, verbose_name='Source')
    idempotency_key = models.CharField(
        max_length=255, verbose_name='Idempotency key'
    )
    payload = models.JSONField(verbose_name='Webhook body')
    received_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Received at'
    )

    class Meta:
        verbose_name = 'Event'
        verbose_name_plural = 'Events'
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'idempotency_key'],
                name='uniq_event_source_idempotency_key',
            )
        ]

    def __str__(self):
        """Source and key."""
        return f'{self.source} - {self.idempotency_key}'


class OutboxStatus(models.TextChoices):
    """Outbox message statuses."""

    PENDING = 'pending', 'Awaiting publication'
    PUBLISHED = 'published', 'Published'
    # A publish failure rolls the transaction back and leaves pending.
    # failed (terminal rejection) arrives with the attempt counter.


class OutboxMessage(models.Model):
    """Event publication request."""

    status = models.CharField(
        max_length=20,
        choices=OutboxStatus.choices,
        default=OutboxStatus.PENDING,
        verbose_name='Status',
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Created at'
    )
    published_at = models.DateTimeField(null=True, verbose_name='Published at')

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='outbox_messages',
        verbose_name='Event',
    )

    class Meta:
        verbose_name = 'Outbox message'
        verbose_name_plural = 'Outbox messages'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=OutboxStatus.values),
                name='outbox_status_valid',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=OutboxStatus.PENDING,
                        published_at__isnull=True,
                    )
                    | models.Q(
                        status=OutboxStatus.PUBLISHED,
                        published_at__isnull=False,
                    )
                ),
                name='outbox_publication_consistent',
            ),
        ]

    def __str__(self):
        """Status and time."""
        return f'{self.status} - {self.created_at}'


class Subscriber(models.Model):
    """Delivered event recipient."""

    name = models.CharField(max_length=50, verbose_name='Name')
    target_url = models.URLField(
        verbose_name='URL',
        validators=[URLValidator(schemes=['https', 'http'])],
    )
    is_active = models.BooleanField(verbose_name='Active', default=True)
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Created at'
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Subscriber'
        verbose_name_plural = 'Subscribers'
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
        """Subscriber name."""
        return self.name


class DeliveryAttemptStatus(models.TextChoices):
    """Delivery attempt statuses."""

    STARTED = 'started', 'Started'
    SUCCEEDED = 'succeeded', 'Succeeded'
    FAILED = 'failed', 'Failed'


class DeliveryAttempt(models.Model):
    """Single delivery attempt."""

    status = models.CharField(
        max_length=20,
        choices=DeliveryAttemptStatus.choices,
        default=DeliveryAttemptStatus.STARTED,
        verbose_name='Attempt status',
    )

    attempt_no = models.PositiveSmallIntegerField(
        verbose_name='Attempt number',
    )

    started_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Started at'
    )

    http_status = models.PositiveSmallIntegerField(
        null=True,
        verbose_name='Response status',
    )

    error = models.CharField(max_length=100, verbose_name='Failure reason')

    finished_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Finished at'
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        db_index=False,
        related_name='delivery_attempts',
        verbose_name='Event',
    )

    subscriber = models.ForeignKey(
        Subscriber,
        on_delete=models.PROTECT,
        related_name='delivery_attempts',
        verbose_name='Subscriber',
    )

    class Meta:
        verbose_name = 'Delivery attempt'
        verbose_name_plural = 'Delivery attempts'
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
        """Delivery attempt description."""
        return f'{self.event} {self.subscriber} {self.attempt_no}'
