"""Точка входа WSGI."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'management.config.settings')

application = get_wsgi_application()
