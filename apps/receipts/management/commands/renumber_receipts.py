"""
Number the receipts that are left 1, 2, 3 ... by upload time.

Receipts are deleted 24 hours after upload, so the IDs in Django
Administration keep climbing over gaps. This gives the remaining rows
consecutive IDs, oldest first, and points the ID counter just past the last
one, so the next upload gets the next number.

Nothing else in the database points at a receipt's ID, so renumbering is
safe. Stop the worker while it runs, so a receipt being read is not saved
back under its old number.
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.receipts.models import Receipt


class Command(BaseCommand):
    help = 'Renumber receipts 1, 2, 3 ... by upload time and reset the counter.'

    def handle(self, *args, **options):
        table = Receipt._meta.db_table
        with transaction.atomic(), connection.cursor() as cursor:
            # Move every row out of the way first, so new numbers never clash
            # with old ones still in the table.
            cursor.execute(f'UPDATE {table} SET id = -id')
            cursor.execute(f'''
                UPDATE {table} AS r SET id = n.new_id
                FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id)
                      AS new_id FROM {table}) AS n
                WHERE r.id = n.id''')
            cursor.execute(f'''
                SELECT setval(pg_get_serial_sequence('{table}', 'id'),
                              COALESCE(MAX(id), 1), MAX(id) IS NOT NULL)
                FROM {table}''')
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = cursor.fetchone()[0]
        self.stdout.write(self.style.SUCCESS(
            'Renumbered %d receipt(s) as 1 to %d. The next upload gets %d.'
            % (count, count, count + 1)))
