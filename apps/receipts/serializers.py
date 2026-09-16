from rest_framework import serializers
from .models import Receipt


class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = [
            'id', 'vendor_name', 'date', 'total_amount',
            'file', 'extracted_data', 'created_at',
            'status', 'error_message', 'processed_at',
        ]
        read_only_fields = fields
