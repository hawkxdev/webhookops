"""Точка входа ASGI."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'management.config.settings')

application = get_asgi_application()
