import json

from django.contrib import admin
from django.utils.html import format_html

from apps.accounts.retention import expires_at

from .models import Receipt


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    """
    Read-only browser over the receipt table.

    Everything here is either uploaded by a user or written by the extraction
    worker, so nothing is editable: an edit would be silently overwritten on
    the next run, or would disagree with the stored file. This exists to answer
    "what is actually in the database", which the app's own History page cannot
    do - it only lists receipts that succeeded, and only the current user's.
    """

    list_display = (
        'id', 'vendor_name', 'date', 'total_amount', 'status',
        'user', 'created_at', 'deletes_at',
    )
    list_display_links = ('id', 'vendor_name')
    list_filter = ('status', 'created_at', 'user')
    search_fields = ('vendor_name', 'error_message')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 50

    readonly_fields = (
        'user', 'vendor_name', 'date', 'total_amount', 'file', 'stored_file',
        'content_type', 'status', 'error_message', 'attempts',
        'created_at', 'deletes_at', 'started_at', 'processed_at',
        'pretty_extracted_data',
    )

    fieldsets = (
        ('Receipt', {
            'fields': ('user', 'vendor_name', 'date', 'total_amount'),
        }),
        ('Uploaded file', {
            'fields': ('file', 'stored_file', 'content_type'),
        }),
        ('Processing', {
            'fields': ('status', 'error_message', 'attempts',
                       'created_at', 'deletes_at', 'started_at',
                       'processed_at'),
        }),
        ('Extracted data', {
            'fields': ('pretty_extracted_data',),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Deletes at')
    def deletes_at(self, obj):
        """When the 24-hour clean-up removes this receipt."""
        return expires_at(obj)

    @admin.display(description='Stored at')
    def stored_file(self, obj):
        """Where the file sits on disk, which is the question people ask."""
        if not obj.file:
            return '-'
        return format_html('<code>{}</code>', obj.file.path)

    @admin.display(description='Extracted data')
    def pretty_extracted_data(self, obj):
        if not obj.extracted_data:
            return '-'
        return format_html(
            '<pre style="white-space:pre-wrap;margin:0">{}</pre>',
            json.dumps(obj.extracted_data, indent=2, ensure_ascii=False),
        )
