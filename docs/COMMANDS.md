# siresoft-receiptiq - Server Commands

    Project dir:   /home/siresoft/siresoft-receiptiq
    Services:      siresoft-receiptiq, siresoft-receiptiq-worker,
                   siresoft-receiptiq-tunnel
    Port:          8002

## How to open the project

**There is no command to run.** The app is already running and has been since
the server booted - systemd starts it, and restarts it if it crashes. To use
it, just open a browser:

| Situation | Address |
|---|---|
| Connected to the VPN | `http://10.0.2.2:8002` |
| VPN off, anywhere | the tunnel address - see "Public URL" below |

`10.0.2.2` is a private address inside the VPN. With the VPN off it is not
merely slow, it is unreachable - nothing on the server can change that, which
is what the tunnel is for.

### Do not run `manage.py runserver` on the server

It looks like it should work and it does not. `runserver` binds to
`127.0.0.1:8000`, which means the server's own loopback, so it answers only
from inside that machine and nothing on your laptop can reach it. It is also a
development server, and it dies the moment the SSH session closes.

`runserver` is for a laptop, where `127.0.0.1` really is your own machine. On
the server, gunicorn under systemd is what serves the app, on port 8002.

If you try it here anyway, it now stops with "That port is already in use" -
manage.py defaults `runserver` to `0.0.0.0:APP_PORT`, and gunicorn already holds
8002. That refusal is the point: it says the app is running, rather than quietly
starting a second one on a port nobody can reach.

## Is it running?   <-- needed 99% of the time

    systemctl is-active siresoft-receiptiq siresoft-receiptiq-worker
    curl -I http://10.0.2.2:8002/

Two "active" lines and `HTTP/1.1 302 Found` mean yes. The 302 is the app
redirecting to its login page, which is the correct answer for a logged-out
request.

For more detail:

    systemctl status siresoft-receiptiq --no-pager

Good signs: "active (running)" and "enabled".

## Start, stop, restart

    sudo systemctl start   siresoft-receiptiq siresoft-receiptiq-worker
    sudo systemctl restart siresoft-receiptiq siresoft-receiptiq-worker
    sudo systemctl stop    siresoft-receiptiq siresoft-receiptiq-worker

`start` on something already running does nothing - that is fine, not an error.

Run these one line at a time. Pasting several together while `sudo` is waiting
for a password feeds the next line in as the password, and the rest silently
never run.

## Log in to the server

    ssh siresoft@10.0.2.2
    cd ~/siresoft-receiptiq

## Deploying a code change

Write and commit the change on your laptop, push it, then on the server:

    cd ~/siresoft-receiptiq
    git pull
    sudo restorecon -v deploy/*.sh
    ./venv/bin/python manage.py migrate              # only if models changed
    ./venv/bin/python manage.py collectstatic --noinput
    sudo systemctl restart siresoft-receiptiq siresoft-receiptiq-worker

Restart **both** services. The worker is the process that actually reads
receipts with the local model, so restarting only the app leaves new code being
served while extraction still runs the old.

Python is loaded into memory at start, so an edit on disk changes nothing until
a restart. `collectstatic` matters just as much: WhiteNoise serves hashed
filenames out of `staticfiles/`, so without it the browser keeps getting the
previous CSS and JS and the change appears not to have worked.

`restorecon` is not optional here - see the note in deploy/README.md.

## Logs

    journalctl -u siresoft-receiptiq -n 50 --no-pager          last 50 lines
    journalctl -u siresoft-receiptiq -f                        live, Ctrl+C to quit
    journalctl -u siresoft-receiptiq -p err -n 30 --no-pager   errors only

## Django tasks

    source venv/bin/activate
    python manage.py migrate
    python manage.py createsuperuser
    python manage.py collectstatic --noinput
    deactivate
    sudo systemctl restart siresoft-receiptiq

## Testing code on a spare port (never use 8002)

A bare `runserver` will refuse here, because 8002 belongs to gunicorn. Name a
free port explicitly:

    source venv/bin/activate
    python manage.py runserver 0.0.0.0:8003
    # Ctrl+C to stop, then: deactivate

On a laptop none of this applies: `python manage.py runserver` picks up
`0.0.0.0:8002` on its own, so the app sits at http://127.0.0.1:8002 - the same
port as the server, and reachable from another device on the same network by
that laptop's own address.

`0.0.0.0` means every interface, so on untrusted wifi that offers the
development server to everyone on the network. Put `RUNSERVER_HOST=127.0.0.1`
in `.env` to keep it to your own machine.

## The extraction worker

    systemctl is-active siresoft-receiptiq-worker
    journalctl -u siresoft-receiptiq-worker -f              live
    journalctl -u siresoft-receiptiq-worker | grep "receipt #"

"Ollama is reachable." at startup means the model is wired up. A receipt stuck
on "Queued" in the browser means this service is not running.

## Public URL (works without the VPN)

    journalctl -u siresoft-receiptiq-tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1

This address changes every time the tunnel restarts. Re-run the command after
any restart or reboot, and tell whoever uses the app.

## Network checks

    sudo ss -tlnp | grep 8002
    sudo firewall-cmd --list-all
    curl -s ifconfig.me

## Handle with care

    sudo systemctl stop siresoft-receiptiq      stops the app
    sudo systemctl disable siresoft-receiptiq   stops it starting at boot
    rm                                 deletes permanently
    cat > file                         wipes the file immediately

## Notes

- Without the VPN, 10.0.2.2 cannot be reached: it is a private address that
  only exists inside that network. The Cloudflare tunnel above is the way
  around it - the server dials out, so no router change is needed.
- Any hostname the app is reached by must be listed in ALLOWED_HOSTS, and its
  origin in CSRF_TRUSTED_ORIGINS, in .env. Otherwise Django answers 400.
- If the screen freezes showing ":" or "(END)", press q.
- "Worker was sent SIGKILL! Perhaps out of memory?" in the logs is usually
  a false alarm. Check with: free -h
