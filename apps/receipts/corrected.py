"""
The corrected copy of a receipt: a clean receipt drawn from its edited data.

The uploaded scan is evidence of what the vendor printed and is never altered;
it stays on the Original scan tab. When someone corrects the extracted data,
this module draws a fresh receipt carrying every corrected value - name,
address, date, details, items, totals, insights - in SireSoft's own layout, labelled as
a corrected copy with who edited it and when. It is never a replica of the
vendor's document.

Drawing reuses PyMuPDF, already installed to rasterise PDF uploads: the receipt
is laid out as HTML on a tall page, then only the part the content filled is
rendered to PNG, as wide in pixels as the original scan.
"""

import io

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from .services import _load_pdf_renderer, render_pdf_preview

PAGE_WIDTH = 560     # points; about an A4 page less its margins
PAGE_HEIGHT = 8000   # tall enough for any item list; cropped after layout
DEFAULT_WIDTH_PX = 1400
MIN_WIDTH_PX, MAX_WIDTH_PX = 600, 2400


def corrected_context(receipt):
    data = receipt.extracted_data or {}
    details = [d for d in data.get('details') or [] if isinstance(d, dict)]
    return {
        'receipt': receipt,
        'establishment': data.get('establishment') or {},
        # Two label/value pairs per row, like the header of an invoice.
        'detail_rows': [details[i:i + 2] for i in range(0, len(details), 2)],
        'items': data.get('items') or [],
        'bill': data.get('bill_summary') or {},
        'insights': [i for i in data.get('insights') or [] if i],
        'edited_at': timezone.localtime(receipt.edited_at or timezone.now()),
        'editor': (receipt.edited_by.email or receipt.edited_by.username
                   if receipt.edited_by else 'a user'),
    }


def _to_png(data):
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        out = io.BytesIO()
        image.convert('RGB').save(out, format='PNG')
        return out.getvalue()


def _original_width(receipt, renderer):
    """Pixel width of the uploaded scan, so both tabs show alike."""
    try:
        with receipt.file.open('rb') as handle:
            data = handle.read()
        if receipt.content_type == 'application/pdf':
            data = render_pdf_preview(data)
        try:
            width = renderer.Pixmap(data).width
        except Exception:
            # MuPDF has no WebP decoder, and uploads accept WebP.
            width = renderer.Pixmap(_to_png(data)).width
    except Exception:
        return DEFAULT_WIDTH_PX
    return min(max(width, MIN_WIDTH_PX), MAX_WIDTH_PX)


def render_corrected_png(receipt) -> bytes:
    renderer = _load_pdf_renderer()
    html = render_to_string('receipts/corrected_receipt.html',
                            corrected_context(receipt))

    doc = renderer.open()
    try:
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        box = renderer.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT)
        spare, _ = page.insert_htmlbox(box, html)
        used = max(PAGE_HEIGHT - spare, 100) if spare >= 0 else PAGE_HEIGHT
        clip = renderer.Rect(0, 0, PAGE_WIDTH, used)
        zoom = _original_width(receipt, renderer) / PAGE_WIDTH
        return page.get_pixmap(matrix=renderer.Matrix(zoom, zoom),
                               clip=clip).tobytes('png')
    finally:
        doc.close()


def save_corrected_copy(receipt):
    """
    Draw the corrected copy and store it on `receipt`, replacing any older one.

    The caller saves the receipt row; this only writes the file and sets the
    field, so a failed drawing leaves the previous copy in place.
    """
    png = render_corrected_png(receipt)
    old = receipt.corrected_file.name if receipt.corrected_file else ''
    receipt.corrected_file.save(
        'receipt-%d-corrected.png' % receipt.pk, ContentFile(png), save=False)
    if old and old != receipt.corrected_file.name:
        receipt.corrected_file.storage.delete(old)
