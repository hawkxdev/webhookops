"""Outbox batch publication."""

from django.db import transaction
from django.utils import timezone

from management.webhooks.models import OutboxMessage, OutboxStatus


def publish_pending(batch_size, submit):
    """Publishes one pending batch."""
    if batch_size < 1:
        raise ValueError('batch_size must be positive')
    with transaction.atomic():
        messages = list(
            OutboxMessage.objects.filter(
                status=OutboxStatus.PENDING,
            )
            .select_for_update(skip_locked=True)
            .order_by('created_at')[:batch_size]
        )
        for message in messages:
            submit(message.event_id)
        OutboxMessage.objects.filter(
            pk__in=[message.pk for message in messages]
        ).update(
            status=OutboxStatus.PUBLISHED,
            published_at=timezone.now(),
        )
    return len(messages)
