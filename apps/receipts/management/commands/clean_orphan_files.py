"""
Delete uploaded files that no receipt row points at any more.

Receipts deleted before the post_delete cleanup existed left their files
behind, and nothing distinguishes those from live ones except the table. This
finds them by comparing the two, and reports before it removes anything: a
wrong match here destroys a user's receipt with no way back.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.receipts.models import Receipt


class Command(BaseCommand):
    help = ('Find uploaded receipt files with no database row. '
            'Reports only, unless --delete is given.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete', action='store_true',
            help='Actually remove the files. Without this, only reports.')

    def handle(self, *args, **options):
        folder = os.path.join(settings.MEDIA_ROOT, 'receipts')

        if not os.path.isdir(folder):
            self.stdout.write('No upload folder at %s - nothing to do.' % folder)
            return

        on_disk = {name for name in os.listdir(folder)
                   if os.path.isfile(os.path.join(folder, name))}
        referenced = {
            os.path.basename(path)
            for path in Receipt.objects.values_list('file', flat=True) if path
        }
        orphans = sorted(on_disk - referenced)

        self.stdout.write('Files on disk:        %d' % len(on_disk))
        self.stdout.write('Referenced by a row:  %d' % len(referenced & on_disk))
        self.stdout.write('Orphaned:             %d' % len(orphans))

        if not orphans:
            self.stdout.write(self.style.SUCCESS('Nothing to clean up.'))
            return

        total = 0
        for name in orphans:
            path = os.path.join(folder, name)
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
            self.stdout.write('  %s' % name)

        self.stdout.write('')
        self.stdout.write('Total: %.1f MB' % (total / 1024 / 1024))

        if not options['delete']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Nothing deleted. Re-run with --delete to remove these.'))
            return

        removed = 0
        for name in orphans:
            try:
                os.remove(os.path.join(folder, name))
                removed += 1
            except OSError as e:
                self.stderr.write(self.style.ERROR(
                    'Could not delete %s: %s' % (name, e)))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            'Deleted %d file(s), freeing %.1f MB.' % (removed, total / 1024 / 1024)))
