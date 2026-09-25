"""
Background worker: turns pending receipts into extracted data.

Runs as its own long-lived process (systemd unit siresoft-receiptiq-worker) so
that a local vision model taking minutes over one image never holds a web
request open. Safe to run more than once: rows are claimed with
SELECT ... FOR UPDATE SKIP LOCKED, so two workers never take the same receipt.
"""

import signal
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.receipts.models import Receipt
from apps.receipts.services import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OllamaError,
    OllamaModelMissingError,
    OllamaUnavailableError,
    check_ollama_ready,
    extract_receipt_data,
)

# How often an infrastructure failure may send a receipt back to the queue
# before it is reported to the user as failed.
MAX_ATTEMPTS = 3
# Wait this long after Ollama looks down, rather than spinning on the queue.
BACKOFF_SECONDS = 15
# Shown on the upload page when nothing more specific is known.
DEFAULT_USER_MESSAGE = 'This receipt could not be read. Please try again.'


class Command(BaseCommand):
    help = 'Extract data from pending receipts using the local Ollama model.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once', action='store_true',
            help='Process everything currently pending, then exit.')
        parser.add_argument(
            '--poll-interval', type=float, default=3.0,
            help='Seconds to wait when the queue is empty (default: 3).')

    def handle(self, *args, **options):
        self._running = True
        # systemd stops services with SIGTERM; finish the receipt in hand
        # instead of leaving it stuck in "processing".
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)

        once = options['once']
        poll_interval = options['poll_interval']

        self.stdout.write('Worker starting — Ollama at %s, model %s'
                          % (OLLAMA_BASE_URL, OLLAMA_MODEL))

        # One clear line at startup beats the same error on every receipt.
        try:
            check_ollama_ready()
            self.stdout.write(self.style.SUCCESS('Ollama is reachable.'))
        except (OllamaUnavailableError, OllamaModelMissingError) as e:
            self.stderr.write(self.style.WARNING(
                'Ollama is not ready: %s' % e))
            self.stderr.write(
                'Continuing anyway — receipts will queue until it comes up.')

        requeued = self._reset_orphans()
        if requeued:
            self.stdout.write(
                'Requeued %d receipt(s) left mid-process by an earlier run.'
                % requeued)

        while self._running:
            receipt = self._claim_one()

            if receipt is None:
                if once:
                    self.stdout.write('Queue empty — exiting.')
                    return
                self._sleep(poll_interval)
                continue

            paused = self._process(receipt)
            if paused and self._running:
                # Ollama looked down. Give it room before trying the next one.
                self._sleep(BACKOFF_SECONDS)

        self.stdout.write('Worker stopped.')

    # ---- lifecycle ----

    def _stop(self, signum, frame):
        self.stdout.write('\nStop requested — finishing current receipt...')
        self._running = False

    def _sleep(self, seconds):
        """Sleep in short slices so a stop signal is noticed promptly."""
        deadline = time.monotonic() + seconds
        while self._running and time.monotonic() < deadline:
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    def _reset_orphans(self):
        """
        Return receipts stuck in 'processing' to the queue.

        A worker killed mid-receipt leaves the row claimed. Nothing else will
        ever pick it up, and the upload page would poll it forever.
        """
        return Receipt.objects.filter(
            status=Receipt.STATUS_PROCESSING).update(
                status=Receipt.STATUS_PENDING, started_at=None)

    # ---- queue ----

    def _claim_one(self):
        """Take the oldest pending receipt, or None if the queue is empty."""
        with transaction.atomic():
            receipt = (Receipt.objects
                       .select_for_update(skip_locked=True)
                       .filter(status=Receipt.STATUS_PENDING)
                       .order_by('created_at')
                       .first())
            if receipt is None:
                return None
            receipt.status = Receipt.STATUS_PROCESSING
            receipt.started_at = timezone.now()
            receipt.save(update_fields=['status', 'started_at'])
            return receipt

    # ---- extraction ----

    def _process(self, receipt):
        """
        Extract one receipt. Returns True if Ollama appeared to be down.

        Infrastructure failures go back on the queue so a restart of Ollama
        rescues them; a receipt the model simply could not read fails outright,
        because retrying would produce the same result.
        """
        started = time.monotonic()
        self.stdout.write('Receipt #%d (%s) — extracting...'
                          % (receipt.id, receipt.filename))

        try:
            with open(receipt.file.path, 'rb') as f:
                file_data = f.read()
        except OSError as e:
            self._fail(receipt, 'Could not read the uploaded file: %s' % e,
                       'The uploaded file could not be opened. Please upload '
                       'it again.')
            return False

        try:
            data = extract_receipt_data(file_data, receipt.content_type)
        except (OllamaUnavailableError, OllamaModelMissingError) as e:
            self._requeue(receipt, str(e), e.user_message)
            return True
        except OllamaError as e:
            self._fail(receipt, str(e), e.user_message)
            return False
        except Exception as e:  # noqa: BLE001 - one receipt must not kill the worker
            self._fail(receipt, 'Unexpected error: %s' % e,
                       'This receipt could not be read. Please try again.')
            return False

        receipt.set_extracted_data(data)
        receipt.scanned_data = data
        receipt.clear_corrections()
        receipt.status = Receipt.STATUS_SUCCESS
        receipt.error_message = ''
        receipt.processed_at = timezone.now()
        receipt.save()

        self.stdout.write(self.style.SUCCESS(
            'Receipt #%d done in %.1fs — %s, total %s'
            % (receipt.id, time.monotonic() - started,
               receipt.vendor_name, receipt.total_amount)))
        return False

    def _fail(self, receipt, log_message, user_message=None):
        """
        Mark a receipt failed.

        Two messages, deliberately: the log gets the technical detail, the
        upload page gets something a person can act on. Showing a raw API
        payload on screen helps nobody and looks broken.
        """
        receipt.status = self._failed_status(receipt)
        receipt.error_message = user_message or DEFAULT_USER_MESSAGE
        receipt.processed_at = timezone.now()
        receipt.save(update_fields=[
            'status', 'error_message', 'processed_at'])
        self.stderr.write(self.style.ERROR(
            'Receipt #%d failed — %s' % (receipt.id, log_message)))

    @staticmethod
    def _failed_status(receipt):
        """
        A failed re-scan keeps the receipt's earlier data, so it stays a
        success; `error_message` still tells the page the re-scan failed.
        """
        if receipt.extracted_data:
            return Receipt.STATUS_SUCCESS
        return Receipt.STATUS_FAILED

    def _requeue(self, receipt, log_message, user_message=None):
        """Send a receipt back to the queue, giving up after MAX_ATTEMPTS."""
        receipt.attempts += 1

        if receipt.attempts >= MAX_ATTEMPTS:
            receipt.status = self._failed_status(receipt)
            receipt.error_message = user_message or DEFAULT_USER_MESSAGE
            receipt.processed_at = timezone.now()
            receipt.save(update_fields=[
                'status', 'error_message', 'processed_at', 'attempts'])
            self.stderr.write(self.style.ERROR(
                'Receipt #%d failed after %d attempts — %s'
                % (receipt.id, receipt.attempts, log_message)))
            return

        # Still pending as far as the page is concerned: an outage is not this
        # receipt's fault, and it will be picked up again on its own.
        receipt.status = Receipt.STATUS_PENDING
        receipt.started_at = None
        receipt.save(update_fields=['status', 'started_at', 'attempts'])
        self.stderr.write(self.style.WARNING(
            'Receipt #%d requeued (attempt %d/%d) — %s'
            % (receipt.id, receipt.attempts, MAX_ATTEMPTS, log_message)))
