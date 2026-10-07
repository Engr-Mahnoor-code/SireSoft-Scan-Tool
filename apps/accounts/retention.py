"""
Delete every ordinary user, and all their receipts, a set time after sign-up.

Each user has their own clock: someone who signs up at 15:00 is removed at
15:00 the next day, someone who signs up at 09:30 at 09:30 the next day. The
receipt rows go with the account (ForeignKey CASCADE), and the receipt
model's post_delete handler removes their uploaded and corrected files from
disk, so nothing of theirs is left in PostgreSQL or under media/.

Staff and superusers are never touched: the admin account must survive.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

logger = logging.getLogger(__name__)


def data_lifetime():
    return timedelta(hours=settings.USER_DATA_TTL_HOURS)


def expires_at(user):
    """When `user` and their receipts will be deleted, or None if never."""
    if user.is_staff or user.is_superuser:
        return None
    return user.date_joined + data_lifetime()


def expired_users(now=None):
    cutoff = (now or timezone.now()) - data_lifetime()
    return User.objects.filter(
        is_staff=False, is_superuser=False, date_joined__lte=cutoff)


def purge_expired_users(now=None):
    """Delete expired users with their receipts. Returns how many users went."""
    deleted = 0
    for user in expired_users(now):
        # One at a time, so a single failure doesn't keep everyone else's
        # data past its deadline.
        try:
            user.delete()
            deleted += 1
            logger.info('Deleted expired user %s and their receipts.',
                        user.username)
        except Exception:  # noqa: BLE001
            logger.exception('Could not delete expired user %s.',
                             user.username)
    return deleted
