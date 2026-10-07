from django.core.management.base import BaseCommand

from apps.accounts.retention import purge_expired_users


class Command(BaseCommand):
    """
    Delete users, and their receipts, USER_DATA_TTL_HOURS after sign-up.

    The worker and the web app already run this every minute; this command is
    for running it by hand or from cron.
    """

    help = 'Delete ordinary users and their receipts once their time is up.'

    def handle(self, *args, **options):
        deleted = purge_expired_users()
        self.stdout.write(self.style.SUCCESS(
            'Deleted %d expired user(s) with their receipts.' % deleted))
