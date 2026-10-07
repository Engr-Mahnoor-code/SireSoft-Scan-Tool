# SireSoft Scan Tool - Server Commands

    Server:        10.0.2.2
    Address:       http://10.0.2.2:9000
    Project dir:   /home/siresoft/siresoft-scan-tool
    Services:      siresoft-scan-tool, siresoft-scan-tool-worker
    Database:      siresoft_receiptiq_db (PostgreSQL)

## How to open the project

**There is no command to run.** The app starts by itself when the server boots
and restarts itself if it crashes. Connect to the VPN and open a browser:

| Page | Address |
|---|---|
| App (login) | http://10.0.2.2:9000/ |
| History | http://10.0.2.2:9000/history/ |
| Django Administration | http://10.0.2.2:9000/admin/ |
| All receipts in the database | http://10.0.2.2:9000/admin/receipts/receipt/ |
| All users and emails | http://10.0.2.2:9000/admin/auth/user/ |

Django Administration login: username `admin` (or `admin@siresoft.com`) and
the admin password from `ADMIN_PASSWORD` in the server's `.env`.

`10.0.2.2` is a private address inside the VPN. With the VPN off it cannot be
reached.

## Is it running?

    systemctl is-active siresoft-scan-tool siresoft-scan-tool-worker
    curl -I http://10.0.2.2:9000/

Two "active" lines and `HTTP/1.1 302 Found` mean yes. The 302 is the app
redirecting to its login page.

If `curl` shows `200 OK` with `Server: Werkzeug`, another app is holding port
9000 - see "Network checks" below.

## Start, stop, restart

    sudo systemctl start   siresoft-scan-tool siresoft-scan-tool-worker
    sudo systemctl restart siresoft-scan-tool siresoft-scan-tool-worker
    sudo systemctl stop    siresoft-scan-tool siresoft-scan-tool-worker

Run these one line at a time. Pasting several together while `sudo` is waiting
for a password feeds the next line in as the password.

## Log in to the server

From your laptop terminal (prompt `DC@Mahnoor MINGW64`):

    ssh siresoft@10.0.2.2
    cd ~/siresoft-scan-tool

The prompt then shows `[siresoft@lsnet siresoft-scan-tool]$`. Server commands
only work there.

## Deploying a code change

Commit and push on your laptop, then on the server:

    cd ~/siresoft-scan-tool
    git pull
    sudo restorecon -v deploy/*.sh
    ./venv/bin/python manage.py migrate
    ./venv/bin/python manage.py collectstatic --noinput
    sudo systemctl restart siresoft-scan-tool siresoft-scan-tool-worker

Restart **both** services, and always run `collectstatic`, or the browser keeps
the old CSS and JavaScript.

## Logs

    journalctl -u siresoft-scan-tool -n 50 --no-pager          website, last 50 lines
    journalctl -u siresoft-scan-tool -f                        live, Ctrl+C to quit
    journalctl -u siresoft-scan-tool-worker -n 50 --no-pager   worker (AI reading)

A "Server Error (500)" page always has its cause in the website log.

## Looking at the data in PostgreSQL

    sudo -u postgres psql siresoft_receiptiq_db

    SELECT id, email, date_joined FROM auth_user;
    SELECT id, user_id, vendor_name, total_amount, created_at FROM receipts_receipt ORDER BY created_at DESC;
    \q

Uploaded files: `ls -lh ~/siresoft-scan-tool/media/receipts/`

## 24-hour receipt deletion

Every receipt is deleted 24 hours after its own upload - from History, from
PostgreSQL (so from Django Administration too) and its file from disk. Admin
receipts are kept. It runs every minute by itself; to run it by hand:

    ./venv/bin/python manage.py purge_expired_receipts

## Network checks

    sudo ss -tlnp | grep :9000
    sudo firewall-cmd --list-all

## Handle with care

    sudo systemctl stop siresoft-scan-tool      stops the app
    sudo systemctl disable siresoft-scan-tool   stops it starting at boot
    rm                                 deletes permanently
    cat > file                         wipes the file immediately

## Notes

- Any hostname the app is reached by must be listed in ALLOWED_HOSTS, and its
  origin in CSRF_TRUSTED_ORIGINS, in .env. Otherwise Django answers 400.
- If the screen freezes showing ":" or "(END)", press q.
