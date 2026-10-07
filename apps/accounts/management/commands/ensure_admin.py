import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """
    Create or repair the admin account from .env.

    The admin's credentials live in the server's .env (ADMIN_USERNAME,
    ADMIN_EMAIL, ADMIN_PASSWORD), never in the repository. Running this makes
    the database match them: the account exists, can sign in to the app by
    email and to /admin/ by email or username, and has full rights. Safe to run again.
    """

    help = 'Create or update the admin account from ADMIN_* settings in .env.'

    def handle(self, *args, **options):
        username = os.environ.get('ADMIN_USERNAME', 'admin').strip()
        email = os.environ.get('ADMIN_EMAIL', '').strip()
        password = os.environ.get('ADMIN_PASSWORD', '')
        if not email or not password:
            raise CommandError(
                'Set ADMIN_EMAIL and ADMIN_PASSWORD in .env first.')

        clash = (User.objects.filter(email__iexact=email)
                 .exclude(username=username).first())
        if clash:
            # Sign-in by email needs the address to name one account only.
            raise CommandError(
                '%s already belongs to user "%s". Change that account\'s '
                'email first.' % (email, clash.username))

        user, created = User.objects.get_or_create(username=username)
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(
            '%s admin "%s" (%s). Sign in to the app and to /admin/ with '
            'either the email or the username.'
            % ('Created' if created else 'Updated', username, email)))
