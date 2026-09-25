from django.core.management.base import BaseCommand

from apps.receipts.corrected import save_corrected_copy
from apps.receipts.models import Receipt


class Command(BaseCommand):
    """
    Redraw every existing corrected copy with the current layout.

    Run once after a change to how corrected copies are drawn; edits made
    afterwards draw their own. Receipts whose original file is missing are
    reported and left as they are.
    """

    help = 'Redraw the corrected copy of every edited receipt.'

    def handle(self, *args, **options):
        receipts = Receipt.objects.exclude(corrected_file='').select_related(
            'edited_by')
        done = failed = 0
        for receipt in receipts:
            try:
                save_corrected_copy(receipt)
                receipt.save(update_fields=['corrected_file'])
                done += 1
            except Exception as e:  # noqa: BLE001 - one receipt must not stop the rest
                failed += 1
                self.stderr.write('Receipt #%d: %s' % (receipt.pk, e))
        self.stdout.write(self.style.SUCCESS(
            'Redrew %d corrected copies, %d failed.' % (done, failed)))
