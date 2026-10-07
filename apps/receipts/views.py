import logging

from django.http import FileResponse, Http404, HttpResponse
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.accounts.retention import expires_at

from .corrected import save_corrected_copy
from .forms import ReceiptEditForms
from .models import Receipt
from .services import render_pdf_preview
from .api_views import ALLOWED_MIME_TYPES, MAX_FILES_PER_UPLOAD, MAX_FILE_SIZE

logger = logging.getLogger(__name__)


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
    # Receipts being re-scanned keep their earlier data, so they stay listed.
    receipts = (Receipt.objects.visible_to(request.user)
                .filter(Q(status=Receipt.STATUS_SUCCESS)
                        | Q(extracted_data__isnull=False))
                .exclude(status=Receipt.STATUS_FAILED)
                .select_related('user'))
    return render(request, 'receipts/history.html', {
        'receipts': receipts,
        'expires_at': expires_at(request.user),
    })


@login_required
def detail(request, pk):
    """Detail page — view a single receipt's extracted data."""
    receipt = get_object_or_404(
        Receipt.objects.visible_to(request.user).select_related('edited_by'),
        pk=pk)
    return render(request, 'receipts/detail.html', {
        'receipt': receipt,
        'can_edit': receipt.status == Receipt.STATUS_SUCCESS,
    })


@login_required
def edit(request, pk):
    """
    Correct what the scan read: establishment, items, totals and insights.

    Open to whoever may view the receipt - its owner, or staff. Only finished
    scans can be edited; a receipt still queued would have the worker write
    over the correction.
    """
    receipt = get_object_or_404(
        Receipt.objects.visible_to(request.user),
        pk=pk, status=Receipt.STATUS_SUCCESS)

    if request.method == 'POST':
        forms = ReceiptEditForms(receipt, request.POST)
        if forms.is_valid():
            if receipt.scanned_data is None:
                # Receipts scanned before `scanned_data` existed: the data as
                # it stands now is the best record of the scan there is.
                receipt.scanned_data = receipt.extracted_data
            receipt.set_extracted_data(forms.cleaned_data())
            receipt.edited_at = timezone.now()
            receipt.edited_by = request.user
            try:
                save_corrected_copy(receipt)
            except Exception:
                # The corrections matter more than their picture: keep them,
                # and say the picture is out of date.
                logger.exception('Corrected copy of receipt %s failed', pk)
                messages.warning(
                    request, 'Receipt updated, but its corrected picture '
                             'could not be drawn.')
            else:
                messages.success(request, 'Receipt updated.')
            receipt.save()
            return redirect('receipts:detail', pk=receipt.pk)
    else:
        forms = ReceiptEditForms(receipt)
    return render(request, 'receipts/edit.html',
                  {'receipt': receipt, 'forms': forms})


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
    # The stored type was checked against the upload allowlist; anything else
    # is downloaded rather than rendered, so the browser never sniffs it.
    return _serve(receipt.file, receipt.content_type, receipt.filename)


@login_required
def receipt_corrected(request, pk):
    """The corrected copy drawn after an edit, under the same access check."""
    receipt = get_object_or_404(
        Receipt.objects.visible_to(request.user), pk=pk)
    response = _serve(receipt.corrected_file, 'image/png',
                      'receipt-%d-corrected.png' % receipt.pk)
    # Redrawn on every edit under the same URL; the page adds a version to
    # the URL, but never let a stale copy be kept for long.
    response['Cache-Control'] = 'private, no-cache'
    return response


def _serve(field, content_type, filename):
    if not field:
        raise Http404('This receipt has no such file.')
    try:
        handle = field.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('The receipt file is missing.')
    inline = content_type in ALLOWED_MIME_TYPES
    response = FileResponse(
        handle,
        as_attachment=not inline,
        filename=filename,
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


@login_required
def delete(request, pk):
    """
    Delete a receipt: its data, its uploaded file and any corrected copy.

    GET shows what is about to go and asks; only the POST from that page
    deletes, so a stray link or prefetch can never remove anything. Open to
    the owner and to staff, like every other page for the receipt.
    """
    receipt = get_object_or_404(
        Receipt.objects.visible_to(request.user), pk=pk)
    if request.method == 'POST':
        name = receipt.vendor_name or 'Receipt'
        receipt.delete()  # the post_delete signal removes both files
        messages.success(request, '%s was deleted.' % name)
        return redirect('receipts:history')
    return render(request, 'receipts/confirm_delete.html',
                  {'receipt': receipt})


@login_required
def rescan(request, pk):
    """
    Send a receipt's original picture through extraction again.

    For receipts read by an older, less thorough prompt, or read badly. The
    fresh reading replaces the data and any hand edits; if it fails, the
    earlier data is kept (see the worker). POST only, from the page's button.
    """
    receipt = get_object_or_404(
        Receipt.objects.visible_to(request.user),
        pk=pk, status__in=[Receipt.STATUS_SUCCESS, Receipt.STATUS_FAILED])
    if request.method != 'POST':
        return redirect('receipts:detail', pk=receipt.pk)
    receipt.status = Receipt.STATUS_PENDING
    receipt.attempts = 0
    receipt.started_at = None
    receipt.error_message = ''
    receipt.save(update_fields=[
        'status', 'attempts', 'started_at', 'error_message'])
    messages.info(request, 'Re-scan started. This page updates when it is done.')
    return redirect('receipts:detail', pk=receipt.pk)
