from django.db import models


class Event(models.Model):
    source = models.CharField(max_length=50)
    idempotency_key = models.CharField(max_length=255)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'idempotency_key'],
                name='uniq_event_source_idempotency_key',
            )
        ]

    def __str__(self):
        return f'{self.source} - {self.idempotency_key}'


class OutboxStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    # позже DISPATCHED, FAILED, DEAD


class OutboxMessage(models.Model):
    status = models.CharField(
        max_length=20,
        choices=OutboxStatus.choices,
        default=OutboxStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name='outbox_messages'
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=OutboxStatus.values),
                name='outbox_status_valid',
            )
        ]

    def __str__(self):
        """Статус и время."""
        return f'{self.status} - {self.created_at}'
