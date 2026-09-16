"""
REST API views for the receipts app.
All views require authentication (enforced by DRF IsAuthenticated default).

Uploading only queues work. A local vision model can spend minutes on one
image — far longer than a tunnel or browser will hold a request open — so the
upload returns as soon as the files are saved and the page polls
/api/receipts/status/ while the worker gets through them.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http

from django.shortcuts import get_object_or_404

from .models import Receipt
from .serializers import ReceiptSerializer

ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/jpg', 'image/png',
    'image/webp', 'image/gif', 'application/pdf',
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILES_PER_UPLOAD = 5
# Upper bound on one status poll, so a crafted query cannot ask for everything.
MAX_STATUS_IDS = 50


def receipt_state(receipt):
    """The shape the upload page polls for. Kept in one place by design."""
    state = {
        'receipt_id': receipt.id,
        'filename': receipt.filename,
        'status': receipt.status,
    }
    if receipt.status == Receipt.STATUS_SUCCESS:
        state['data'] = receipt.extracted_data
    elif receipt.status == Receipt.STATUS_FAILED:
        state['error'] = receipt.error_message or 'Extraction failed.'
    return state


class UploadReceiptView(APIView):
    """
    POST /api/upload/

    Accepts up to MAX_FILES_PER_UPLOAD files (field name 'files', or 'file' for
    a single upload), saves each one as a pending receipt and returns straight
    away. A file rejected by validation never blocks the others.
    """

    def post(self, request):
        uploaded_files = (request.FILES.getlist('files')
                          or request.FILES.getlist('file'))

        if not uploaded_files:
            return Response({'error': 'No file provided.'},
                            status=http.HTTP_400_BAD_REQUEST)

        if len(uploaded_files) > MAX_FILES_PER_UPLOAD:
            return Response(
                {'error': 'Too many files. Up to %d receipts can be uploaded '
                          'at a time.' % MAX_FILES_PER_UPLOAD},
                status=http.HTTP_400_BAD_REQUEST,
            )

        results = [
            self._queue_file(request.user, uploaded_file, index)
            for index, uploaded_file in enumerate(uploaded_files)
        ]

        queued = [r for r in results if r['status'] == Receipt.STATUS_PENDING]
        payload = {
            'results': results,
            'queued_count': len(queued),
            'error_count': len(results) - len(queued),
        }

        if not queued:
            # Everything was rejected before it reached the queue.
            if len(results) == 1:
                payload['error'] = results[0]['error']
            return Response(payload, status=http.HTTP_400_BAD_REQUEST)

        # A single upload also returns the flat receipt_id older callers expect.
        if len(results) == 1:
            payload['receipt_id'] = queued[0]['receipt_id']

        return Response(payload, status=http.HTTP_202_ACCEPTED)

    def _queue_file(self, user, uploaded_file, index):
        """Validate one file and save it as a pending receipt."""
        def failure(message, code):
            return {
                'index': index,
                'filename': uploaded_file.name,
                'status': Receipt.STATUS_FAILED,
                'code': code,
                'error': message,
            }

        if uploaded_file.content_type not in ALLOWED_MIME_TYPES:
            return failure(
                'Invalid file type. Only images and PDFs are accepted.',
                'invalid_type')

        if uploaded_file.size > MAX_FILE_SIZE:
            return failure('File too large. Maximum size is 10 MB.',
                           'too_large')

        receipt = Receipt.objects.create(
            user=user,
            file=uploaded_file,
            content_type=uploaded_file.content_type,
            status=Receipt.STATUS_PENDING,
        )

        return {
            'index': index,
            'filename': uploaded_file.name,
            'status': Receipt.STATUS_PENDING,
            'receipt_id': receipt.id,
        }


class ReceiptStatusView(APIView):
    """
    GET /api/receipts/status/?ids=1,2,3

    Reports where the worker has got to with each receipt. Unknown ids are left
    out rather than erroring, so a stale page does not break on a deleted row.
    """

    def get(self, request):
        raw_ids = request.query_params.get('ids', '')
        ids = []
        for chunk in raw_ids.split(','):
            chunk = chunk.strip()
            if chunk.isdigit():
                ids.append(int(chunk))

        if not ids:
            return Response({'error': 'No receipt ids given.'},
                            status=http.HTTP_400_BAD_REQUEST)

        receipts = Receipt.objects.filter(
            user=request.user, pk__in=ids[:MAX_STATUS_IDS])
        states = [receipt_state(r) for r in receipts]

        return Response({
            'results': states,
            'pending_count': sum(
                1 for s in states
                if s['status'] in (Receipt.STATUS_PENDING,
                                   Receipt.STATUS_PROCESSING)),
        })


class ReceiptListView(APIView):
    """
    GET /api/receipts/
    Returns the authenticated user's successfully processed receipts.
    """

    def get(self, request):
        receipts = Receipt.objects.filter(
            user=request.user, status=Receipt.STATUS_SUCCESS)
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
