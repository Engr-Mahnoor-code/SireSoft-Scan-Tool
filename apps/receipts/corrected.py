"""
The corrected copy of a receipt: the original scan, annotated with the edits.

The uploaded scan is evidence of what the vendor printed and is never altered,
neither on disk nor in this picture. When someone corrects the extracted data,
this module draws the original picture as it is, with a CORRECTED banner above
it and a list of every value changed below it - old value struck through, new
value beside it. It looks like the receipt because it is the receipt, and it
cannot pass for a document the vendor issued.

Drawing reuses PyMuPDF, already installed to rasterise PDF uploads. The page is
laid out 560 points wide so text sizes stay constant, then rendered at the
pixel width of the original scan.
"""

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from .services import _load_pdf_renderer, render_pdf_preview

LAYOUT_WIDTH = 560          # points
MEASURE_HEIGHT = 6000       # scratch page for measuring HTML blocks
MIN_WIDTH_PX, MAX_WIDTH_PX = 600, 2400


def _number(value):
    if isinstance(value, (int, float)):
        return '%.2f' % value
    return str(value or '').strip()


def _flatten(data):
    """
    A receipt's data as ordered (label, value) pairs, for comparing two
    versions field by field.
    """
    data = data or {}
    pairs = []
    est = data.get('establishment') or {}
    for key, label in (('name', 'Name'), ('address', 'Address'),
                       ('date', 'Date'), ('time', 'Time')):
        pairs.append((label, str(est.get(key) or '').strip()))

    for detail in data.get('details') or []:
        if isinstance(detail, dict):
            pairs.append((str(detail.get('label') or '').strip(),
                          str(detail.get('value') or '').strip()))

    for index, item in enumerate(data.get('items') or [], start=1):
        if not isinstance(item, dict):
            continue
        quantity = item.get('quantity')
        if isinstance(quantity, float) and quantity.is_integer():
            quantity = int(quantity)
        value = '%s · %s × %s = %s' % (
            str(item.get('name') or '').strip(), quantity,
            _number(item.get('unit_price')), _number(item.get('total')))
        if item.get('note'):
            value += ' (%s)' % str(item['note']).strip()
        pairs.append(('Item %d' % index, value))

    bill = data.get('bill_summary') or {}
    for key, label in (('subtotal', 'Subtotal'), ('tax', 'Tax'),
                       ('discount', 'Discount'), ('tip', 'Tip')):
        if bill.get(key):
            pairs.append((label, _number(bill.get(key))))
    for line in bill.get('other_lines') or []:
        if isinstance(line, dict):
            pairs.append((str(line.get('label') or '').strip(),
                          _number(line.get('amount'))))
    pairs.append(('Grand Total', _number(bill.get('grand_total'))))
    if bill.get('payment_method'):
        pairs.append(('Payment', str(bill['payment_method']).strip()))
    return pairs


def list_changes(before, after):
    """Every field whose value differs, in the order the receipt reads."""
    old = dict(_flatten(before))
    new = _flatten(after)
    changes = []
    for label, value in new:
        previous = old.pop(label, '')
        if previous != value:
            changes.append({'label': label, 'old': previous, 'new': value})
    # Fields the edit removed altogether.
    for label, value in old.items():
        if value:
            changes.append({'label': label, 'old': value, 'new': ''})
    return changes


def corrected_context(receipt):
    return {
        'receipt': receipt,
        'changes': list_changes(receipt.scanned_data or receipt.extracted_data,
                                receipt.extracted_data),
        'edited_at': timezone.localtime(receipt.edited_at or timezone.now()),
        'editor': (receipt.edited_by.email or receipt.edited_by.username
                   if receipt.edited_by else 'a user'),
    }


def _original_pixmap(receipt, renderer):
    """The uploaded scan as a pixmap; page 1 for a PDF."""
    with receipt.file.open('rb') as handle:
        data = handle.read()
    if receipt.content_type == 'application/pdf':
        data = render_pdf_preview(data)
    try:
        pixmap = renderer.Pixmap(data)
    except Exception:
        # MuPDF has no WebP decoder, and uploads accept WebP.
        pixmap = renderer.Pixmap(_to_png(data))
    if pixmap.alpha:
        pixmap = renderer.Pixmap(pixmap, 0)
    return pixmap


def _to_png(data):
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        out = io.BytesIO()
        image.convert('RGB').save(out, format='PNG')
        return out.getvalue()


def _html_height(renderer, html):
    doc = renderer.open()
    try:
        page = doc.new_page(width=LAYOUT_WIDTH, height=MEASURE_HEIGHT)
        spare, _ = page.insert_htmlbox(
            renderer.Rect(0, 0, LAYOUT_WIDTH, MEASURE_HEIGHT), html)
        return MEASURE_HEIGHT - spare if spare >= 0 else MEASURE_HEIGHT
    finally:
        doc.close()


def render_corrected_png(receipt) -> bytes:
    renderer = _load_pdf_renderer()
    original = _original_pixmap(receipt, renderer)
    context = corrected_context(receipt)
    banner = render_to_string('receipts/corrected_banner.html', context)
    panel = render_to_string('receipts/corrected_changes.html', context)

    banner_h = _html_height(renderer, banner)
    image_h = LAYOUT_WIDTH * original.height / original.width
    panel_h = _html_height(renderer, panel)

    doc = renderer.open()
    try:
        page = doc.new_page(width=LAYOUT_WIDTH,
                            height=banner_h + image_h + panel_h)
        page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
        page.insert_htmlbox(renderer.Rect(0, 0, LAYOUT_WIDTH, banner_h), banner)
        page.insert_image(
            renderer.Rect(0, banner_h, LAYOUT_WIDTH, banner_h + image_h),
            pixmap=original)
        page.insert_htmlbox(
            renderer.Rect(0, banner_h + image_h, LAYOUT_WIDTH,
                          banner_h + image_h + panel_h), panel)
        width_px = min(max(original.width, MIN_WIDTH_PX), MAX_WIDTH_PX)
        zoom = width_px / LAYOUT_WIDTH
        return page.get_pixmap(matrix=renderer.Matrix(zoom, zoom)).tobytes('png')
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
