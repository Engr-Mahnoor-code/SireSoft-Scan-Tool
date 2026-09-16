# Deploying siresoft-receiptiq on lsnettest5 (10.0.2.13)

This project installs as its own deployment, separate from anything already on
the host. Nothing here is shared with an older install — its own folder, venv,
database, port and systemd units.

    Project dir:   /home/siresoft/siresoft-receiptiq
    Service name:  siresoft-receiptiq
    Port:          8002
    Database:      siresoft_receiptiq_db

The wrapper scripts work out the project directory from their own location, so
the same files work if you ever clone somewhere else — only the `.service`
files name a path.

| Service | Wrapper | Purpose |
|---|---|---|
| `siresoft-receiptiq` | `run-app.sh` | Django via gunicorn on `APP_PORT` |
| `siresoft-receiptiq-ngrok` | `run-ngrok.sh` | Stable public URL, works without the VPN |
| `siresoft-receiptiq-tunnel` | `run-cloudflared.sh` | Cloudflare backup route |

Settings live in one place only — `/home/siresoft/siresoft-receiptiq/.env`:

    APP_PORT=8002
    GUNICORN_WORKERS=3
    GUNICORN_TIMEOUT=600
    NGROK_URL=https://<your-reserved-domain>.ngrok-free.dev

## First install

    ssh siresoft@10.0.2.13

    git clone https://github.com/engr-mahnoor-naeem/siresoft-receiptiq.git ~/siresoft-receiptiq
    cd ~/siresoft-receiptiq

    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt gunicorn

Create its own database (the older install keeps its own):

    sudo -u postgres psql -c "CREATE DATABASE siresoft_receiptiq_db;"

Then write `.env` from the template and fill in real values:

    cp .env.example .env
    nano .env          # SECRET_KEY, DB_*, GEMINI_API_KEY, APP_PORT=8002
    chmod 600 .env

`.env` is gitignored and is never overwritten by `git pull`. Keep a copy
somewhere safe — it is the only thing a fresh clone cannot recreate.

    ./venv/bin/python manage.py migrate
    ./venv/bin/python manage.py collectstatic --noinput
    ./venv/bin/python manage.py createsuperuser

## Why wrappers instead of systemd's EnvironmentFile

`EnvironmentFile=/home/siresoft/…/.env` does not work here. systemd reads that
file as PID 1, and SELinux (Enforcing on this host) denies `init_t` access to
`user_home_t`, so every start fails with:

    Failed to load environment files: Permission denied

The wrapper runs as `siresoft`, who owns the file, so sourcing `.env` succeeds.

## Install the services

    chmod +x ~/siresoft-receiptiq/deploy/run-*.sh

    # SELinux: scripts under /home are user_home_t, which systemd may not
    # execute. Relabel them as bin_t or every start fails with status=203/EXEC.
    sudo chcon -t bin_t ~/siresoft-receiptiq/deploy/run-*.sh

    sudo cp ~/siresoft-receiptiq/deploy/*.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now siresoft-receiptiq

Open the port:

    sudo firewall-cmd --permanent --add-port=8002/tcp && sudo firewall-cmd --reload

To survive a full filesystem relabel, make the SELinux context permanent:

    sudo semanage fcontext -a -t bin_t "/home/siresoft/siresoft-receiptiq/deploy/run-.*\.sh"
    sudo restorecon -v ~/siresoft-receiptiq/deploy/run-*.sh

## Public access (optional)

Start these only if this project needs a public URL:

    sudo systemctl enable --now siresoft-receiptiq-ngrok siresoft-receiptiq-tunnel

A free ngrok account allows **one** agent session at a time. If an older ngrok
service is already running on this host, this one will keep restarting until
that one is stopped. Check with `journalctl -u siresoft-receiptiq-ngrok -n 30`.

Whatever public hostname you use must be listed in `ALLOWED_HOSTS`, and its
`https://` origin in `CSRF_TRUSTED_ORIGINS`, in `.env`.

## Updating after a code change

    cd ~/siresoft-receiptiq
    git pull
    ./venv/bin/pip install -r requirements.txt     # only if requirements changed
    ./venv/bin/python manage.py migrate            # only if models changed
    ./venv/bin/python manage.py collectstatic --noinput
    sudo systemctl restart siresoft-receiptiq

`collectstatic` is not optional. WhiteNoise serves hashed filenames from
`staticfiles/`, so without it the server keeps serving the previous CSS and JS
and your changes simply will not appear in the browser.

## Health check

    systemctl is-active siresoft-receiptiq
    curl -I http://10.0.2.13:8002/
    journalctl -u siresoft-receiptiq -n 50 --no-pager

## Changing the port

Edit `APP_PORT` in `.env`, then:

    sudo systemctl restart siresoft-receiptiq siresoft-receiptiq-ngrok siresoft-receiptiq-tunnel
    sudo firewall-cmd --permanent --add-port=<new-port>/tcp && sudo firewall-cmd --reload

## Cloudflare URL

The Cloudflare quick tunnel gets a new hostname every restart. Read the current
one with:

    journalctl -u siresoft-receiptiq-tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
