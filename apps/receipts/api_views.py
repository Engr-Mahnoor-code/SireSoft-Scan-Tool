"""
REST API views for the receipts app.
All views require authentication (enforced by DRF IsAuthenticated default).
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import Receipt
from .serializers import ReceiptSerializer
from .services import extract_receipt_data, GeminiQuotaError, GeminiAPIError

import re as _re


def _safe_float(value, default=0.0):
    """Convert a value to float, stripping currency symbols/commas if needed."""
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        pass
    try:
        cleaned = _re.sub(r'[^\d.\-]', '', str(value).replace(',', ''))
        return float(cleaned) if cleaned else default
    except (ValueError, TypeError):
        return default


ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/jpg', 'image/png',
    'image/webp', 'image/gif', 'application/pdf',
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class UploadReceiptView(APIView):
    """
    POST /api/upload/
    Accepts a file, calls Gemini for extraction, saves to DB, returns JSON data.
    """

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        if uploaded_file.content_type not in ALLOWED_MIME_TYPES:
            return Response(
                {'error': 'Invalid file type. Only images and PDFs are accepted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uploaded_file.size > MAX_FILE_SIZE:
            return Response(
                {'error': 'File too large. Maximum size is 10 MB.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        receipt = Receipt.objects.create(user=request.user, file=uploaded_file)

        try:
            with open(receipt.file.path, 'rb') as f:
                file_data = f.read()

            data = extract_receipt_data(file_data, uploaded_file.content_type)

            receipt.vendor_name = data.get(
                'establishment', {}).get('name') or 'Unknown Vendor'
            receipt.date = data.get('establishment', {}).get('date') or 'N/A'
            total = data.get('bill_summary', {}).get('grand_total', 0)
            receipt.total_amount = _safe_float(total)
            receipt.extracted_data = data
            receipt.save()

            return Response({
                'receipt_id': receipt.id,
                'data': data,
            }, status=status.HTTP_201_CREATED)

        except GeminiQuotaError as e:
            receipt.delete()
            return Response(
                {'error': 'API quota exceeded. Please wait or upgrade your Gemini plan.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except (GeminiAPIError, Exception) as e:
            receipt.delete()
            return Response(
                {'error': f'Extraction failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ReceiptListView(APIView):
    """
    GET /api/receipts/
    Returns all receipts belonging to the authenticated user.
    """

    def get(self, request):
        receipts = Receipt.objects.filter(user=request.user)
        serializer = ReceiptSerializer(
            receipts, many=True, context={'request': request})
        return Response(serializer.data)


class ReceiptDetailView(APIView):
    """
    GET /api/receipts/<pk>/
    Returns a single receipt. Only the owner can access it.
    """

    def get(self, request, pk):
        receipt = get_object_or_404(Receipt, pk=pk, user=request.user)
        serializer = ReceiptSerializer(receipt, context={'request': request})
        return Response(serializer.data)
