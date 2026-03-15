"""
Gemini API service — completely isolated from Django views.
Calls the Gemini REST API directly (no SDK).
"""

import base64
import os
import json
import requests

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/models'
MODELS_TO_TRY = ['gemini-2.5-flash',
                 'gemini-2.0-flash', 'gemini-2.0-flash-lite']

EXTRACTION_PROMPT = """Analyze this receipt or invoice image/PDF and extract all data.
Return ONLY a valid JSON object with exactly this structure (no markdown, no extra text):
{
    "establishment": {
        "name": "",
        "address": "",
        "date": "",
        "time": ""
    },
    "items": [
        {"name": "", "quantity": 1, "unit_price": 0.0, "total": 0.0}
    ],
    "bill_summary": {
        "subtotal": 0.0,
        "tax": 0.0,
        "discount": 0.0,
        "grand_total": 0.0,
        "payment_method": ""
    },
    "insights": [
        "Most expensive item: ...",
        "Payment method: ..."
    ]
}
All numeric fields (unit_price, total, subtotal, tax, grand_total, etc.) MUST be plain numbers, not strings."""


class GeminiQuotaError(Exception):
    """Raised when all Gemini models have exhausted their quota."""


class GeminiAPIError(Exception):
    """Raised for non-quota Gemini API errors."""


def extract_receipt_data(file_data: bytes, mime_type: str) -> dict:
    """
    Send file bytes to the Gemini REST API and return parsed JSON data.

    Tries models in order and falls back on 429 quota errors.
    Raises GeminiQuotaError if all models are exhausted.
    Raises GeminiAPIError for other API failures.
    """
    encoded = base64.b64encode(file_data).decode('utf-8')
    payload = {
        'contents': [{
            'parts': [
                {'inline_data': {'mime_type': mime_type, 'data': encoded}},
                {'text': EXTRACTION_PROMPT},
            ]
        }]
    }

    last_quota_error = None
    for model in MODELS_TO_TRY:
        url = f'{GEMINI_BASE_URL}/{model}:generateContent?key={GEMINI_API_KEY}'
        try:
            resp = requests.post(url, json=payload, timeout=60)
        except requests.RequestException as e:
            raise GeminiAPIError(
                f'Network error contacting Gemini: {e}') from e

        if resp.status_code == 429:
            last_quota_error = resp.json().get('error', {}).get('message', 'Quota exceeded')
            continue

        if not resp.ok:
            msg = resp.json().get('error', {}).get('message', resp.text)
            raise GeminiAPIError(msg)

        return _parse_response(resp.json())

    raise GeminiQuotaError(
        last_quota_error or 'All Gemini model quotas exhausted.')


def _parse_response(api_response: dict) -> dict:
    """Extract and parse the JSON text from a Gemini API response."""
    try:
        raw = api_response['candidates'][0]['content']['parts'][0]['text'].strip()
    except (KeyError, IndexError) as e:
        raise GeminiAPIError(
            f'Unexpected Gemini response structure: {api_response}') from e

    # Strip markdown code fences if present
    if '```json' in raw:
        raw = raw.split('```json')[1].split('```')[0].strip()
    elif '```' in raw:
        raw = raw.split('```')[1].split('```')[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise GeminiAPIError(f'Gemini returned invalid JSON: {e}') from e
