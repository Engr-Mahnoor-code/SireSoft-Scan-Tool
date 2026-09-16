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
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3.2-vision')
OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '900'))
# PDFs are rasterised before the model sees them. 200 dpi keeps small print
# legible without producing an image the model would only downscale again.
PDF_RENDER_DPI = int(os.environ.get('PDF_RENDER_DPI', '200'))

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
- List every item you can read, in the order they appear."""


class OllamaUnavailableError(Exception):
    """Raised when the Ollama server cannot be reached at all."""


class OllamaModelMissingError(Exception):
    """Raised when Ollama is running but the configured model is not pulled."""


class OllamaError(Exception):
    """Raised for any other extraction failure."""


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
            'PDF support needs PyMuPDF. Install it with: pip install pymupdf'
        ) from e


def _pdf_first_page_to_png(file_data: bytes) -> bytes:
    """
    Render page 1 of a PDF to PNG bytes.

    Ollama's vision models read images, not PDFs. Only the first page is sent:
    receipts are single-page, and a taller stacked image would just be scaled
    back down by the model. Multi-page invoices lose their later pages.
    """
    renderer = _load_pdf_renderer()
    try:
        doc = renderer.open(stream=file_data, filetype='pdf')
    except Exception as e:
        raise OllamaError(f'Could not read the PDF: {e}') from e

    try:
        if doc.page_count == 0:
            raise OllamaError('The PDF has no pages.')
        pixmap = doc.load_page(0).get_pixmap(dpi=PDF_RENDER_DPI)
        return pixmap.tobytes('png')
    except OllamaError:
        raise
    except Exception as e:
        raise OllamaError(f'Could not render the PDF: {e}') from e
    finally:
        doc.close()


def _as_image_bytes(file_data: bytes, mime_type: str) -> bytes:
    """Return image bytes the model can read, converting a PDF if needed."""
    if (mime_type or '').lower() == 'application/pdf':
        return _pdf_first_page_to_png(file_data)
    return file_data


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

    Raises OllamaUnavailableError if the server is down, OllamaModelMissingError
    if the model is not pulled, and OllamaError for everything else.
    """
    image_bytes = _as_image_bytes(file_data, mime_type)
    encoded = base64.b64encode(image_bytes).decode('utf-8')

    payload = {
        'model': OLLAMA_MODEL,
        'prompt': EXTRACTION_PROMPT,
        'images': [encoded],
        'stream': False,
        # Constrains decoding to valid JSON, which a small local model will
        # otherwise wrap in prose however firmly the prompt asks it not to.
        'format': 'json',
        'options': {'temperature': 0},
    }

    try:
        resp = requests.post(
            OLLAMA_BASE_URL + '/api/generate', json=payload,
            timeout=OLLAMA_TIMEOUT)
    except requests.Timeout as e:
        raise OllamaError(
            'The model took longer than %ss on this receipt. Try a smaller '
            'model or raise OLLAMA_TIMEOUT.' % OLLAMA_TIMEOUT) from e
    except requests.RequestException as e:
        raise OllamaUnavailableError(
            'Cannot reach Ollama at ' + OLLAMA_BASE_URL + ': ' + str(e)) from e

    if resp.status_code == 404:
        raise OllamaModelMissingError(
            "Model '%s' is not installed. Pull it with: ollama pull %s"
            % (OLLAMA_MODEL, OLLAMA_MODEL))

    if not resp.ok:
        raise OllamaError(
            'Ollama returned HTTP %s: %s' % (resp.status_code, resp.text[:300]))

    try:
        raw = resp.json().get('response', '')
    except ValueError as e:
        raise OllamaError('Ollama returned a response that was not JSON.') from e

    return _normalise(_parse_json(raw))


def _parse_json(raw: str) -> dict:
    """Pull a JSON object out of the model's reply."""
    text = (raw or '').strip()
    if not text:
        raise OllamaError('The model returned an empty response.')

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
                'The model did not return JSON: ' + text[:200]) from None
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
