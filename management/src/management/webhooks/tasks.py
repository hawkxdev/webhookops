"""Delivery task definitions."""

from celery import shared_task
from celery.utils.log import get_task_logger

from management.webhooks.models import Event

logger = get_task_logger(__name__)


@shared_task(name='webhooks.deliver_event')
def deliver_event(event_id: int) -> None:
    """Delivers one event."""
    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        logger.warning('event %s is missing, delivery skipped', event_id)
        return
    raise NotImplementedError(f'delivery of event {event.pk} is not wired yet')
