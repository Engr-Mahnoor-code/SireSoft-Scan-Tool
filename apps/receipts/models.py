import os

from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User


class ReceiptQuerySet(models.QuerySet):
    def visible_to(self, user):
        """
        The receipts `user` may see: every receipt for staff, otherwise only
        their own. Every page and endpoint that looks up receipts goes through
        this, so the rule lives in one place.
        """
        if user.is_staff:
            return self.all()
        return self.filter(user=user)


class Receipt(models.Model):
    """
    One uploaded receipt.

    Extraction happens in a background worker, not in the upload request, so a
    receipt row exists before any model has looked at the file. `status` is what
    the upload page polls to follow along.
    """

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='receipts')
    vendor_name = models.CharField(max_length=255, null=True, blank=True)
    date = models.CharField(max_length=100, null=True, blank=True)
    total_amount = models.FloatField(default=0.0)
    file = models.FileField(upload_to='receipts/')
    # A picture drawn from the extracted data after someone corrects it. The
    # uploaded `file` is never altered: it stays as the proof of what the
    # vendor actually printed.
    corrected_file = models.FileField(
        upload_to='receipts/corrected/', blank=True)
    # Recorded at upload: the worker runs long after the request is gone
    # and still needs to know whether to rasterise a PDF.
    content_type = models.CharField(max_length=100, blank=True, default='')
    extracted_data = models.JSONField(null=True, blank=True)
    # What the scan read, kept apart from `extracted_data` once someone edits
    # it, so the corrected copy can show each value before and after.
    scanned_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING,
        db_index=True)
    error_message = models.TextField(blank=True, default='')
    # Counts only infrastructure retries (Ollama down, model not pulled).
    # A receipt the model genuinely could not read fails on the first try.
    attempts = models.PositiveSmallIntegerField(default=0)
    # Set when the worker picks the receipt up, so a job orphaned by a restart
    # can be told apart from one that is genuinely still running.
    started_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    # Set when someone corrects the extracted data by hand.
    edited_at = models.DateTimeField(null=True, blank=True)
    edited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+')

    objects = ReceiptQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vendor_name or 'Unknown'} — {self.total_amount} ({self.user.username})"

    @property
    def filename(self):
        """The stored file's base name, for showing next to a result."""
        return os.path.basename(self.file.name) if self.file else ''

    @property
    def is_finished(self):
        return self.status in (self.STATUS_SUCCESS, self.STATUS_FAILED)

    def set_extracted_data(self, data):
        """
        Store `data` and the list columns copied out of it.

        History lists vendor, date and total from their own columns, so they
        are refreshed every time the data changes, by the worker or by hand.
        """
        establishment = data.get('establishment') or {}
        summary = data.get('bill_summary') or {}
        self.vendor_name = establishment.get('name') or 'Unknown Vendor'
        self.date = establishment.get('date') or 'N/A'
        self.total_amount = summary.get('grand_total') or 0.0
        self.extracted_data = data

    def clear_corrections(self):
        """
        Drop the hand edits' record and picture, for a fresh scan's data.

        A corrected copy drawn from the old data would contradict the new
        reading, so it goes with the edit stamp.
        """
        if self.corrected_file:
            try:
                self.corrected_file.delete(save=False)
            except Exception:
                pass
        self.corrected_file = ''
        self.edited_at = None
        self.edited_by = None

    @property
    def is_rescanning(self):
        """Queued again although it already has data from an earlier scan."""
        return (self.status in (self.STATUS_PENDING, self.STATUS_PROCESSING)
                and bool(self.extracted_data))


@receiver(post_delete, sender=Receipt)
def delete_receipt_file(sender, instance, **kwargs):
    """
    Remove the uploaded file, and any corrected copy, when the receipt row goes.

    Django deletes the row and leaves the file, which is the safe default for a
    framework but wrong here: nothing else ever references that file, so it just
    accumulates. Deleting ten failed receipts once already left ten files behind
    with no way to tell them from live ones except by comparing against the
    table.

    Failures are swallowed on purpose - the row is already gone by this point,
    and raising here would turn a tidy-up into a broken delete.
    """
    for field in (instance.file, instance.corrected_file):
        if not field:
            continue
        try:
            field.delete(save=False)
        except Exception:
            pass
