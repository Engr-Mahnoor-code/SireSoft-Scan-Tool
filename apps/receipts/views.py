from django.http import FileResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.clickjacking import xframe_options_sameorigin
from .models import Receipt
from .api_views import ALLOWED_MIME_TYPES, MAX_FILES_PER_UPLOAD, MAX_FILE_SIZE


@login_required
def index(request):
    """Upload page — entry point for receipt scanning."""
    return render(request, 'receipts/index.html', {
        'max_files': MAX_FILES_PER_UPLOAD,
        'max_file_size': MAX_FILE_SIZE,
    })


@login_required
def history(request):
    """History page — receipts the worker finished successfully."""
    receipts = (Receipt.objects.visible_to(request.user)
                .filter(status=Receipt.STATUS_SUCCESS)
                .select_related('user'))
    return render(request, 'receipts/history.html', {'receipts': receipts})


@login_required
def detail(request, pk):
    """Detail page — view a single receipt's extracted data."""
    receipt = get_object_or_404(
        Receipt.objects.visible_to(request.user), pk=pk)
    return render(request, 'receipts/detail.html', {'receipt': receipt})


@xframe_options_sameorigin
@login_required
def receipt_file(request, pk):
    """
    Stream a receipt's uploaded file to its owner.

    Served through this view rather than a /media/ URL so the same access
    check as the detail page applies: another user asking for this pk gets a
    404, never the file.
    """
    receipt = get_object_or_404(
        Receipt.objects.visible_to(request.user), pk=pk)
    if not receipt.file:
        raise Http404('This receipt has no file.')
    try:
        handle = receipt.file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('The receipt file is missing.')

    # The stored type was checked against the upload allowlist; anything else
    # is downloaded rather than rendered, so the browser never sniffs it.
    content_type = receipt.content_type
    inline = content_type in ALLOWED_MIME_TYPES
    response = FileResponse(
        handle,
        as_attachment=not inline,
        filename=receipt.filename,
        content_type=content_type if inline else 'application/octet-stream',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, max-age=3600'
    return response
