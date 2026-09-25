"""
Ollama vision service — completely isolated from Django views.

Talks to a local Ollama server over its REST API. There is no API key and no
call leaves the host: the model runs here, so the only limits are its own speed
and memory. Because a local model can spend minutes on one image, nothing in
this module is meant to run inside a web request — see the process_receipts
management command.
"""

import base64
import json
import os
import re

import requests

OLLAMA_BASE_URL = os.environ.get(
    'OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5vl:3b')
OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '900'))
# A receipt image costs thousands of tokens. Ollama's 4096 default is not
# enough for a full page, and overflowing it fails the request outright.
OLLAMA_NUM_CTX = int(os.environ.get('OLLAMA_NUM_CTX', '8192'))
# Longest edge, in pixels, of the image handed to the model. This is the real
# guard on context: a page rendered at a fixed DPI grows without limit, so cap
# the result instead and let the DPI fall where it must.
MAX_IMAGE_EDGE = int(os.environ.get('MAX_IMAGE_EDGE', '1400'))
# Ceiling for PDF rasterising; the edge cap above usually lands below this.
PDF_RENDER_DPI = int(os.environ.get('PDF_RENDER_DPI', '150'))

# PyMuPDF opens these as single-page documents, which is how an oversized
# photo gets scaled down before it reaches the model.
_IMAGE_FILETYPES = {
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/bmp': 'bmp',
    'image/webp': 'webp',
}

EXTRACTION_PROMPT = """You are reading a receipt or invoice. Extract every line item and total you can see.

Reply with ONE JSON object and nothing else. No explanation, no markdown fences.

Use exactly this structure:
{
    "establishment": {
        "name": "shop or company name",
        "address": "street address if shown, else empty string",
        "date": "date on the receipt as printed, else empty string",
        "time": "time on the receipt as printed, else empty string"
    },
    "details": [
        {"label": "Invoice No.", "value": "as printed"}
    ],
    "items": [
        {"name": "item as printed", "quantity": 1, "unit_price": 0.0, "total": 0.0}
    ],
    "bill_summary": {
        "subtotal": 0.0,
        "tax": 0.0,
        "discount": 0.0,
        "grand_total": 0.0,
        "payment_method": "cash, card, or whatever is printed"
    },
    "insights": [
        "one short observation about this receipt",
        "another short observation"
    ]
}

Rules:
- Every price, quantity and total must be a plain number such as 12.5 — never a string, never a currency symbol.
- If a value is not printed on the receipt, use 0.0 for numbers and an empty string for text. Do not invent values.
- List every item you can read, in the order they appear.
- "details" holds every other labelled field printed on the receipt, in the order printed: bill or invoice number, due date, PO number, phone, email, website, tax or GST numbers, bill from, bill to, vehicle number, cashier, table, and so on. Use the label as printed. Leave out anything already in "establishment", the items or the bill summary."""


class OllamaError(Exception):
    """
    Base for every extraction failure.

    Carries two messages on purpose: `str(e)` is the technical detail, which
    belongs in the worker log, and `user_message` is what the upload page
    shows. Users should never be handed a raw API error payload.
    """

    default_user_message = 'This receipt could not be read. Please try again.'

    def __init__(self, message, user_message=None):
        super().__init__(message)
        self.user_message = user_message or self.default_user_message


class OllamaUnavailableError(OllamaError):
    """Raised when the Ollama server cannot be reached at all."""

    default_user_message = (
        'The extraction service is not responding right now. This receipt has '
        'been saved and will be processed automatically once it is back.')


class OllamaModelMissingError(OllamaError):
    """Raised when Ollama is running but the configured model is not usable."""

    default_user_message = (
        'The extraction service is not configured correctly. Please contact '
        'your administrator.')


class OllamaContextError(OllamaError):
    """Raised when the image does not fit in the model's context window."""

    default_user_message = (
        'This file was too detailed to read in one pass. Try uploading a '
        'smaller or clearer scan.')


def _load_pdf_renderer():
    """
    Import PyMuPDF under whichever name this version exposes.

    PyMuPDF renamed its module from `fitz` to `pymupdf` in 1.24; both names work
    on current releases but only one exists on older ones.
    """
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        pass
    try:
        import fitz
        return fitz
    except ImportError as e:
        raise OllamaError(
            'PDF support needs PyMuPDF. Install it with: pip install pymupdf',
            'PDF receipts are not available on this server yet. Please upload '
            'an image instead.') from e


def _render_pdf_page(file_data: bytes, max_edge: int) -> bytes:
    """
    Render page 1 of a PDF to PNG bytes, capped at `max_edge` pixels.

    Ollama's vision models read images, not PDFs. Only the first page is sent:
    receipts are single-page, and a taller stacked image would just be scaled
    back down by the model. Multi-page invoices lose their later pages.
    """
    renderer = _load_pdf_renderer()
    try:
        doc = renderer.open(stream=file_data, filetype='pdf')
    except Exception as e:
        raise OllamaError(
            'Could not read the PDF: %s' % e,
            'This PDF could not be opened. It may be damaged or password '
            'protected.') from e

    try:
        if doc.page_count == 0:
            raise OllamaError('The PDF has no pages.',
                              'This PDF is empty.')
        page = doc.load_page(0)
        # A page is measured in points: 72 to the inch. Pick the DPI that lands
        # on the edge cap, never above PDF_RENDER_DPI.
        longest_points = max(page.rect.width, page.rect.height) or 1
        dpi = min(PDF_RENDER_DPI, int(max_edge * 72 / longest_points))
        return page.get_pixmap(dpi=max(dpi, 48)).tobytes('png')
    except OllamaError:
        raise
    except Exception as e:
        raise OllamaError(
            'Could not render the PDF: %s' % e,
            'This PDF could not be converted to an image.') from e
    finally:
        doc.close()


def render_pdf_preview(file_data: bytes, max_edge: int = 2000) -> bytes:
    """
    Page 1 of a PDF as a PNG for showing on the detail page.

    A receipt saved as PDF is usually a photo placed on a blank page under a
    title. When page 1 carries images, only the area they cover is rendered,
    at their own resolution, so the page shows the receipt and not the sheet
    it sits on. A text-only PDF renders the whole page.
    """
    renderer = _load_pdf_renderer()
    doc = renderer.open(stream=file_data, filetype='pdf')
    try:
        page = doc.load_page(0)
        clip = page.rect
        dpi = PDF_RENDER_DPI
        images = [info for info in page.get_image_info()
                  if renderer.Rect(info['bbox']).intersects(page.rect)]
        if images:
            clip = renderer.Rect()
            for info in images:
                clip |= renderer.Rect(info['bbox'])
            clip &= page.rect
            # Match the pixels the embedded image actually has.
            widest = max(images, key=lambda i: renderer.Rect(i['bbox']).width)
            dpi = int(widest['width'] * 72
                      / (renderer.Rect(widest['bbox']).width or 1))
        longest_points = max(clip.width, clip.height) or 1
        dpi = min(dpi, int(max_edge * 72 / longest_points))
        return page.get_pixmap(dpi=max(dpi, 48), clip=clip).tobytes('png')
    finally:
        doc.close()


def _shrink_image(file_data: bytes, mime_type: str, max_edge: int) -> bytes:
    """
    Scale an image down so its longest edge is at most `max_edge` pixels.

    Best effort by design: a format PyMuPDF cannot open is passed through
    untouched rather than failing the receipt, since most photos are already
    small enough and the model is the better judge of the rest.
    """
    filetype = _IMAGE_FILETYPES.get((mime_type or '').lower())
    if not filetype:
        return file_data

    try:
        renderer = _load_pdf_renderer()
        doc = renderer.open(stream=file_data, filetype=filetype)
        try:
            page = doc.load_page(0)
            longest = max(page.rect.width, page.rect.height) or 1
            if longest <= max_edge:
                return file_data
            zoom = max_edge / longest
            matrix = renderer.Matrix(zoom, zoom)
            return page.get_pixmap(matrix=matrix).tobytes('png')
        finally:
            doc.close()
    except Exception:
        return file_data


def _prepare_image(file_data: bytes, mime_type: str, max_edge: int) -> bytes:
    """Return image bytes the model can read, sized to fit its context."""
    if (mime_type or '').lower() == 'application/pdf':
        return _render_pdf_page(file_data, max_edge)
    return _shrink_image(file_data, mime_type, max_edge)


def check_ollama_ready() -> None:
    """
    Raise if Ollama is unreachable or the configured model is not installed.

    The worker calls this once at startup so a misconfiguration shows up as one
    clear log line instead of an identical failure on every single receipt.
    """
    try:
        resp = requests.get(OLLAMA_BASE_URL + '/api/tags', timeout=10)
    except requests.RequestException as e:
        raise OllamaUnavailableError(
            'Cannot reach Ollama at ' + OLLAMA_BASE_URL + ': ' + str(e)) from e

    if not resp.ok:
        raise OllamaUnavailableError(
            'Ollama at %s returned HTTP %s.' % (OLLAMA_BASE_URL, resp.status_code))

    try:
        installed = [m.get('name', '') for m in resp.json().get('models', [])]
    except ValueError as e:
        raise OllamaUnavailableError(
            'Ollama returned a response that was not JSON.') from e

    # Ollama reports tagged names ("llava:latest"); accept a bare name too.
    wanted = OLLAMA_MODEL.split(':')[0]
    if not any(name.split(':')[0] == wanted for name in installed):
        raise OllamaModelMissingError(
            "Model '%s' is not installed. Pull it with: ollama pull %s. "
            "Installed: %s" % (
                OLLAMA_MODEL, OLLAMA_MODEL, ', '.join(installed) or 'none'))


def extract_receipt_data(file_data: bytes, mime_type: str) -> dict:
    """
    Send a receipt to the local Ollama model and return parsed, normalised data.

    A file that overflows the model's context is retried once at a smaller size
    rather than reported as a failure: shrinking costs a second, and the user
    cannot act on "too many tokens" in any case.
    """
    sizes = (MAX_IMAGE_EDGE, int(MAX_IMAGE_EDGE * 0.6))
    overflow = None

    for max_edge in sizes:
        image_bytes = _prepare_image(file_data, mime_type, max_edge)
        try:
            return _normalise(_parse_json(_ask_model(image_bytes)))
        except OllamaContextError as e:
            overflow = e
            continue

    raise overflow


def _ask_model(image_bytes: bytes) -> str:
    """POST one image to Ollama and return the model's raw reply."""
    encoded = base64.b64encode(image_bytes).decode('utf-8')

    payload = {
        'model': OLLAMA_MODEL,
        'prompt': EXTRACTION_PROMPT,
        'images': [encoded],
        'stream': False,
        # Constrains decoding to valid JSON, which a small local model will
        # otherwise wrap in prose however firmly the prompt asks it not to.
        'format': 'json',
        'options': {'temperature': 0, 'num_ctx': OLLAMA_NUM_CTX},
    }

    try:
        resp = requests.post(
            OLLAMA_BASE_URL + '/api/generate', json=payload,
            timeout=OLLAMA_TIMEOUT)
    except requests.Timeout as e:
        raise OllamaError(
            'The model took longer than %ss on this receipt. Try a smaller '
            'model or raise OLLAMA_TIMEOUT.' % OLLAMA_TIMEOUT,
            'This receipt took too long to read. Try a smaller or clearer '
            'scan.') from e
    except requests.RequestException as e:
        raise OllamaUnavailableError(
            'Cannot reach Ollama at ' + OLLAMA_BASE_URL + ': ' + str(e)) from e

    if resp.status_code == 404:
        raise OllamaModelMissingError(
            "Model '%s' is not installed. Pull it with: ollama pull %s"
            % (OLLAMA_MODEL, OLLAMA_MODEL))

    # Ollama reports an oversized prompt as a 400 naming the context size.
    if resp.status_code == 400 and 'context' in resp.text.lower():
        raise OllamaContextError(
            'Image did not fit the context window: %s' % resp.text[:300])

    if not resp.ok:
        raise OllamaError(
            'Ollama returned HTTP %s: %s' % (resp.status_code, resp.text[:300]))

    try:
        return resp.json().get('response', '')
    except ValueError as e:
        raise OllamaError(
            'Ollama returned a response that was not JSON.') from e


def _parse_json(raw: str) -> dict:
    """Pull a JSON object out of the model's reply."""
    text = (raw or '').strip()
    if not text:
        raise OllamaError(
            'The model returned an empty response.',
            'Nothing could be read from this file. Try a clearer scan.')

    # `format: json` normally makes fences impossible, but a model that ignores
    # it still produces something recoverable.
    if '```' in text:
        fenced = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} span.
        start, end = text.find('{'), text.rfind('}')
        if start == -1 or end <= start:
            raise OllamaError(
                'The model did not return JSON: ' + text[:200],
                'This file did not look like a receipt. Please check the '
                'image and try again.') from None
        try:
            parsed = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            raise OllamaError('The model returned invalid JSON: %s' % e) from e

    if not isinstance(parsed, dict):
        raise OllamaError('The model returned JSON that was not an object.')
    return parsed


def _to_number(value, default=0.0) -> float:
    """
    Coerce a model-supplied value to a float, tolerating '$1,234.50'.

    Always returns a float, including for `default`: callers pass ints like 1
    for quantity, and letting that through would hand the templates a mix of
    types for the same field.
    """
    fallback = float(default)
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return fallback
    cleaned = re.sub(r'[^\d.\-]', '', str(value).replace(',', ''))
    if cleaned in ('', '-', '.', '-.'):
        return fallback
    try:
        return float(cleaned)
    except ValueError:
        return fallback


def _to_text(value) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ''
    return str(value).strip()


def _normalise(data: dict) -> dict:
    """
    Force the model's output into the shape the templates and JS expect.

    A local model is looser than a hosted one: it returns prices as strings,
    drops keys, or makes `items` a single object. Repairing that here keeps
    every consumer downstream free of defensive checks.
    """
    establishment = data.get('establishment')
    if not isinstance(establishment, dict):
        establishment = {}

    summary = data.get('bill_summary')
    if not isinstance(summary, dict):
        summary = {}

    raw_items = data.get('items')
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    elif not isinstance(raw_items, list):
        raw_items = []

    items = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        name = _to_text(entry.get('name') or entry.get('item'))
        if not name:
            continue
        items.append({
            'name': name,
            'quantity': _to_number(entry.get('quantity'), 1) or 1.0,
            'unit_price': _to_number(entry.get('unit_price') or entry.get('price')),
            'total': _to_number(entry.get('total')),
        })

    raw_insights = data.get('insights')
    if isinstance(raw_insights, str):
        raw_insights = [raw_insights]
    elif not isinstance(raw_insights, list):
        raw_insights = []
    insights = [_to_text(i) for i in raw_insights if _to_text(i)]

    raw_details = data.get('details')
    if isinstance(raw_details, dict):
        raw_details = [{'label': k, 'value': v} for k, v in raw_details.items()]
    elif not isinstance(raw_details, list):
        raw_details = []
    details = []
    for entry in raw_details:
        if not isinstance(entry, dict):
            continue
        label = _to_text(entry.get('label'))
        value = _to_text(entry.get('value'))
        if label and value:
            details.append({'label': label, 'value': value})

    grand_total = _to_number(summary.get('grand_total'))
    if not grand_total:
        # Some models fill only the line items; a sum beats showing zero.
        grand_total = round(sum(i['total'] for i in items), 2)

    return {
        'establishment': {
            'name': _to_text(establishment.get('name')),
            'address': _to_text(establishment.get('address')),
            'date': _to_text(establishment.get('date')),
            'time': _to_text(establishment.get('time')),
        },
        'details': details,
        'items': items,
        'bill_summary': {
            'subtotal': _to_number(summary.get('subtotal')),
            'tax': _to_number(summary.get('tax')),
            'discount': _to_number(summary.get('discount')),
            'grand_total': grand_total,
            'payment_method': _to_text(summary.get('payment_method')),
        },
        'insights': insights,
    }
