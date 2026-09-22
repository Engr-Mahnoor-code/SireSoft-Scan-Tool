#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:  # manage.py has to work before requirements are installed
    def load_dotenv(*args, **kwargs):
        return False


def default_runserver_port(argv):
    """
    Append APP_PORT to a bare `runserver`.

    Django's own default is 8000, but this project is served on APP_PORT (8002)
    everywhere else - gunicorn, the systemd unit, the tunnel, the docs. Leaving
    development on a different port means the address you use while working is
    not the address you have been told to use, which reads as "the app is
    broken" rather than "wrong port".

    An explicit address still wins: `runserver 9000` and `runserver 0.0.0.0:80`
    are untouched. Flags are ignored when deciding, so `runserver --noreload`
    still picks up the default.
    """
    if argv[1:2] != ['runserver']:
        return argv

    if any(not arg.startswith('-') for arg in argv[2:]):
        return argv

    return argv + [os.environ.get('APP_PORT', '8002')]


def main():
    """Run administrative tasks."""
    load_dotenv()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(default_runserver_port(sys.argv))


if __name__ == '__main__':
    main()
