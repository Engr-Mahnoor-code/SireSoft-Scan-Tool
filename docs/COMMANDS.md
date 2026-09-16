# siresoft-receiptiq - Server Commands

The app runs as a systemd service. It starts on boot and restarts on crash.
You do NOT need to start it manually.

    URL (on VPN):  http://10.0.2.13:8002
    Project dir:   /home/siresoft/siresoft-receiptiq
    Service name:  siresoft-receiptiq
    Port:          8002

## Login

    ssh siresoft@10.0.2.13
    cd ~/siresoft-receiptiq

## Check that it is running   <-- needed 99% of the time

    systemctl status siresoft-receiptiq --no-pager
    systemctl is-active siresoft-receiptiq
    curl -I http://10.0.2.13:8002/

Good signs: "active (running)", "enabled", and HTTP 200 or 302.

## Restart (only after changing code or .env)

    sudo systemctl restart siresoft-receiptiq

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

- Without the VPN, 10.0.2.13 cannot be reached. Fixing that needs a
  port-forward rule on the router (10.0.2.1). That is a network admin
  task - no Django or .env setting can do it.
- If the screen freezes showing ":" or "(END)", press q.
- "Worker was sent SIGKILL! Perhaps out of memory?" in the logs is usually
  a false alarm. Check with: free -h
