from django.contrib import admin
from .models import Receipt

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('vendor_name', 'total_amount', 'date', 'created_at')
    search_fields = ('vendor_name',)
