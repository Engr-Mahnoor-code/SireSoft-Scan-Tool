"""
The corrected copy of a receipt: a clean picture drawn from its edited data.

The uploaded scan is evidence of what the vendor printed and is never touched.
When someone corrects the extracted data, this module draws a fresh receipt
from it - clearly labelled as a corrected copy, with who edited it and when -
so the picture people look at matches the numbers they now trust.

Drawing reuses PyMuPDF, already installed to rasterise PDF uploads: the receipt
is laid out as HTML on a tall page, then only the part the content filled is
rendered to PNG.
"""

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from .services import _load_pdf_renderer

PAGE_WIDTH = 420     # points; a receipt-roll proportion
PAGE_HEIGHT = 6000   # tall enough for any item list; cropped after layout
RENDER_DPI = 200


def render_corrected_png(receipt) -> bytes:
    renderer = _load_pdf_renderer()
    data = receipt.extracted_data or {}
    html = render_to_string('receipts/corrected_receipt.html', {
        'receipt': receipt,
        'establishment': data.get('establishment') or {},
        'items': data.get('items') or [],
        'bill': data.get('bill_summary') or {},
        'edited_at': timezone.localtime(receipt.edited_at or timezone.now()),
    })

    doc = renderer.open()
    try:
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        box = renderer.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT)
        spare, _ = page.insert_htmlbox(box, html)
        used = max(PAGE_HEIGHT - spare, 100) if spare >= 0 else PAGE_HEIGHT
        clip = renderer.Rect(0, 0, PAGE_WIDTH, used)
        return page.get_pixmap(dpi=RENDER_DPI, clip=clip).tobytes('png')
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
