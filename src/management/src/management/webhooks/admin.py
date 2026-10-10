"""Админка просмотра событий."""

from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """Просмотр принятых событий."""

    list_display = ('id', 'source', 'idempotency_key', 'received_at')
    search_fields = ('source', 'idempotency_key')
    list_filter = ('source',)

    def has_add_permission(self, request):
        """Запрет создания события."""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрет изменения события."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Запрет удаления события."""
        return False
