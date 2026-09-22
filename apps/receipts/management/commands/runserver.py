"""
`runserver`, printing addresses someone can actually open.

Binding to 0.0.0.0 is right - it is what makes the site reachable both on the
machine itself and from anywhere else on the network. Printing it is not:
`http://0.0.0.0:8002/` is not an address anyone can type, and on a screen shown
to a client it reads as something misconfigured.

So the bind is left alone and only the banner is replaced, with the addresses
that actually work: loopback, and this machine's own address on the network.

It lives in apps.receipts because management commands resolve in INSTALLED_APPS
order, and this app is listed ahead of django.contrib.staticfiles so that this
file wins over the runserver that ships with it. Moving it back down the list
silently disables this.
"""

import re
import socket

from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticfilesRunserverCommand,
)

# Django's own line, which we swap out. Matched loosely so a wording change in
# a future Django simply leaves the default banner in place.
ADDRESS_LINE = re.compile(r'Starting development server at \S+/?\n')


def local_network_address():
    """
    This machine's address on the network it routes through, or None.

    Opening a UDP socket sends nothing; it only asks the OS which interface it
    would use to reach the outside, which is the address other machines on the
    network can reach this one by.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('8.8.8.8', 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


class BannerRewriter:
    """Wraps the command's stdout and rewrites the address line once."""

    def __init__(self, stream, replacement):
        self.__dict__['_stream'] = stream
        self.__dict__['_replacement'] = replacement
        self.__dict__['_rewritten'] = False

    def write(self, msg='', style_func=None, ending=None):
        if not self._rewritten and 'Starting development server at' in msg:
            msg = ADDRESS_LINE.sub(self._replacement, msg)
            self.__dict__['_rewritten'] = True
        return self._stream.write(msg, style_func, ending)

    def __getattr__(self, name):
        return getattr(self.__dict__['_stream'], name)

    def __setattr__(self, name, value):
        setattr(self.__dict__['_stream'], name, value)


class Command(StaticfilesRunserverCommand):
    help = 'Starts a lightweight development web server, on APP_PORT.'

    def inner_run(self, *args, **options):
        replacement = self.build_address_banner()
        if replacement is None:
            return super().inner_run(*args, **options)

        original = self.stdout
        self.stdout = BannerRewriter(original, replacement)
        try:
            super().inner_run(*args, **options)
        finally:
            self.stdout = original

    def build_address_banner(self):
        """The replacement lines, or None to leave Django's banner alone."""
        if self.addr not in ('0.0.0.0', '::'):
            # An explicit address was given; Django's line is already usable.
            return None

        entries = [('http://127.0.0.1:%s/' % self.port, 'this machine')]

        address = local_network_address()
        if address:
            entries.append(('http://%s:%s/' % (address, self.port),
                            'from other machines on this network'))

        width = max(len(url) for url, _ in entries)
        lines = ['Serving on port %s. Open it at:\n' % self.port, '\n']
        lines += ['    %-*s   (%s)\n' % (width, url, note)
                  for url, note in entries]
        lines.append('\n')
        # re.sub treats backslashes in the replacement as escapes, and an
        # address never contains one, but be explicit rather than lucky.
        return ''.join(lines).replace('\\', '\\\\')
