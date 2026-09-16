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
MAX_FILES_PER_UPLOAD = 5


class UploadReceiptView(APIView):
    """
    POST /api/upload/
    Accepts up to MAX_FILES_PER_UPLOAD files (field name 'files', or 'file' for
    a single upload), calls Gemini for each, saves them, and returns one result
    entry per file. A failure on one file never aborts the rest of the batch.
    """

    def post(self, request):
        uploaded_files = request.FILES.getlist('files') or request.FILES.getlist('file')

        if not uploaded_files:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(uploaded_files) > MAX_FILES_PER_UPLOAD:
            return Response(
                {'error': f'Too many files. Up to {MAX_FILES_PER_UPLOAD} receipts can be uploaded at a time.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = [
            self._process_file(request.user, uploaded_file, index)
            for index, uploaded_file in enumerate(uploaded_files)
        ]

        succeeded = [r for r in results if r['status'] == 'success']
        payload = {
            'results': results,
            'success_count': len(succeeded),
            'error_count': len(results) - len(succeeded),
        }

        # Backwards compatibility: a single successful upload also returns the
        # flat {receipt_id, data} shape older clients expect.
        if len(results) == 1 and succeeded:
            payload['receipt_id'] = succeeded[0]['receipt_id']
            payload['data'] = succeeded[0]['data']

        if succeeded:
            return Response(payload, status=status.HTTP_201_CREATED)

        codes = {r.get('code') for r in results}
        if codes == {'quota'}:
            http_status = status.HTTP_429_TOO_MANY_REQUESTS
        elif codes <= {'invalid_type', 'too_large'}:
            http_status = status.HTTP_400_BAD_REQUEST
        else:
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

        # Single-file failures keep the flat {error} shape too.
        if len(results) == 1:
            payload['error'] = results[0]['error']

        return Response(payload, status=http_status)

    def _process_file(self, user, uploaded_file, index):
        """Validate, extract and save one file. Returns a result dict."""
        def failure(message, code):
            return {
                'index': index,
                'filename': uploaded_file.name,
                'status': 'error',
                'code': code,
                'error': message,
            }

        if uploaded_file.content_type not in ALLOWED_MIME_TYPES:
            return failure('Invalid file type. Only images and PDFs are accepted.', 'invalid_type')

        if uploaded_file.size > MAX_FILE_SIZE:
            return failure('File too large. Maximum size is 10 MB.', 'too_large')

        receipt = Receipt.objects.create(user=user, file=uploaded_file)

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

            return {
                'index': index,
                'filename': uploaded_file.name,
                'status': 'success',
                'receipt_id': receipt.id,
                'data': data,
            }

        except GeminiQuotaError:
            receipt.delete()
            return failure(
                'API quota exceeded. Please wait or upgrade your Gemini plan.', 'quota')
        except (GeminiAPIError, Exception) as e:
            receipt.delete()
            return failure(f'Extraction failed: {str(e)}', 'extraction')


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
