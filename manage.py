#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:  # manage.py has to work before requirements are installed
    def load_dotenv(*args, **kwargs):
        return False


def default_runserver_address(argv):
    """
    Give a bare `runserver` the address this project is actually served on.

    Django defaults to 127.0.0.1:8000. Both halves are wrong here:

    - The port is 9001 everywhere else - gunicorn, the systemd unit, the
      tunnel, both guides. Developing against 8000 means the address you use
      while working is not the address you were told to use.
    - 127.0.0.1 means "only this machine". Run that on a server and it starts
      fine, reports success, and is unreachable from anywhere else, which reads
      as a broken app rather than a wrong bind address.

    So a bare `runserver` becomes 0.0.0.0:APP_PORT, reachable both as
    127.0.0.1:9001 on the machine itself and by its LAN or VPN address from
    elsewhere. Set RUNSERVER_HOST=127.0.0.1 to keep it private instead - worth
    doing on a laptop on untrusted wifi, since 0.0.0.0 offers the development
    server to everyone on that network.

    An explicit address still wins: `runserver 9000` and `runserver 0.0.0.0:80`
    are untouched. Flags are ignored when deciding, so `runserver --noreload`
    still picks up the default.
    """
    if argv[1:2] != ['runserver']:
        return argv

    if any(not arg.startswith('-') for arg in argv[2:]):
        return argv

    host = os.environ.get('RUNSERVER_HOST', '0.0.0.0')
    port = os.environ.get('APP_PORT', '9001')
    return argv + ['%s:%s' % (host, port)]


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
    execute_from_command_line(default_runserver_address(sys.argv))


if __name__ == '__main__':
    main()
