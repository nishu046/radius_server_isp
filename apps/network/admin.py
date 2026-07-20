from django.contrib import admin

from .models import ServiceEvent


@admin.register(ServiceEvent)
class ServiceEventAdmin(admin.ModelAdmin):
    """Read-only: the log records what happened, it is not a place to edit."""

    list_display = ['created_at', 'action', 'subject_type', 'subject_label',
                    'actor', 'is_automatic', 'succeeded']
    list_filter = ['action', 'subject_type', 'is_automatic', 'succeeded']
    search_fields = ['subject_label', 'reason']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
