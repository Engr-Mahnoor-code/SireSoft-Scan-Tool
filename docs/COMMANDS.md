# siresoft-receiptiq - Server Commands

The app runs as a systemd service. It starts on boot and restarts on crash.
You do NOT need to start it manually.

    URL (on VPN):  http://10.0.2.2:8002
    URL (anywhere): the Cloudflare tunnel - see "Public URL" below
    Project dir:   /home/siresoft/siresoft-receiptiq
    Service name:  siresoft-receiptiq
    Port:          8002

## Login

    ssh siresoft@10.0.2.2
    cd ~/siresoft-receiptiq

## Check that it is running   <-- needed 99% of the time

    systemctl status siresoft-receiptiq --no-pager
    systemctl is-active siresoft-receiptiq
    curl -I http://10.0.2.2:8002/

Good signs: "active (running)", "enabled", and HTTP 200 or 302.

## Restart (only after changing code or .env)

    sudo systemctl restart siresoft-receiptiq siresoft-receiptiq-worker

The worker is the process that actually reads receipts with the local model.
Restart it too, or the app will serve new code while the extraction keeps
running the old.

Python code is loaded into memory, so edits do not apply until a restart.

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

    source venv/bin/activate
    python manage.py runserver 0.0.0.0:8003
    # Ctrl+C to stop, then: deactivate

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
