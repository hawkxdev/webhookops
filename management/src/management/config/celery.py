"""Celery application setup."""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'management.config.settings')

app = Celery('management')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
