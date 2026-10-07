from django.core.management.base import BaseCommand

from apps.accounts.retention import purge_expired_receipts


class Command(BaseCommand):
    """
    Delete receipts USER_DATA_TTL_HOURS after each one was uploaded.

    The worker and the web app already run this every minute; this command is
    for running it by hand or from cron.
    """

    help = 'Delete receipts whose 24 hours since upload are up.'

    def handle(self, *args, **options):
        deleted = purge_expired_receipts()
        self.stdout.write(self.style.SUCCESS(
            'Deleted %d expired receipt(s).' % deleted))
