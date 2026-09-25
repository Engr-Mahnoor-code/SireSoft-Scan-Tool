from django.urls import reverse
from rest_framework import serializers
from .models import Receipt


class ReceiptSerializer(serializers.ModelSerializer):
    # Points at the access-checked file view, not the /media/ path, so the
    # link is useless to anyone who could not see the receipt anyway.
    file = serializers.SerializerMethodField()
    owner = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Receipt
        fields = [
            'id', 'owner', 'vendor_name', 'date', 'total_amount',
            'file', 'extracted_data', 'created_at',
            'status', 'error_message', 'processed_at',
        ]
        read_only_fields = fields

    def get_file(self, obj):
        if not obj.file:
            return None
        url = reverse('receipts:file', args=[obj.pk])
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url
