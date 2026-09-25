from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.clickjacking import xframe_options_sameorigin
from .models import Receipt
from .services import render_pdf_preview
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


@login_required
def receipt_preview(request, pk):
    """
    A receipt's picture as an image the detail page can show directly.

    Images are served as they are. A PDF is rendered to PNG, because shown
    as-is the browser wraps it in its PDF viewer (toolbar, page strip and
    scrollbars) instead of just showing the receipt.
    """
    receipt = get_object_or_404(
        Receipt.objects.visible_to(request.user), pk=pk)
    if receipt.content_type != 'application/pdf':
        return receipt_file(request, pk)
    if not receipt.file:
        raise Http404('This receipt has no file.')
    try:
        with receipt.file.open('rb') as handle:
            png = render_pdf_preview(handle.read())
    except (FileNotFoundError, OSError):
        raise Http404('The receipt file is missing.')
    except Exception:
        # A PDF the worker could not read either; the page falls back to
        # its "open the file" link.
        raise Http404('The PDF could not be rendered.')

    response = HttpResponse(png, content_type='image/png')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, max-age=3600'
    return response
