"""
Delete every receipt a set time after it was uploaded.

Each receipt has its own clock: one uploaded at 15:00 is removed at 15:00 the
next day, one uploaded at 16:00 at 16:00 the next day. The row leaves
PostgreSQL (so History and Django Administration no longer show it) and the
receipt model's post_delete handler removes its uploaded and corrected files
from disk. User accounts are kept.

Receipts owned by staff (the admin) are never touched.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def data_lifetime():
    return timedelta(hours=settings.USER_DATA_TTL_HOURS)


def is_exempt(user):
    return user.is_staff or user.is_superuser


def expires_at(receipt):
    """When `receipt` will be deleted, or None if it is kept."""
    if is_exempt(receipt.user):
        return None
    return receipt.created_at + data_lifetime()


def expired_receipts(now=None):
    from apps.receipts.models import Receipt
    cutoff = (now or timezone.now()) - data_lifetime()
    return Receipt.objects.filter(
        user__is_staff=False, user__is_superuser=False,
        created_at__lte=cutoff)


def purge_expired_receipts(now=None):
    """Delete receipts past their lifetime. Returns how many went."""
    deleted = 0
    for receipt in expired_receipts(now):
        # One at a time, so a single failure doesn't keep everyone else's
        # data past its deadline.
        try:
            receipt.delete()
            deleted += 1
        except Exception:  # noqa: BLE001
            logger.exception('Could not delete expired receipt #%s.',
                             receipt.pk)
    if deleted:
        logger.info('Deleted %d expired receipt(s).', deleted)
    return deleted
