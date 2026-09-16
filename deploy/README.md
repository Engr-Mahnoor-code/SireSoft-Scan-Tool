# Deploying ReceiptIQ on lsnettest5 (10.0.2.13)

Three systemd services run the stack. None of them hardcode the port or the
public URL — each calls a small wrapper script that sources the project's own
`.env`, so `~/receiptiq/.env` is the single place those settings live:

    APP_PORT=8001
    GUNICORN_WORKERS=3
    GUNICORN_TIMEOUT=600
    NGROK_URL=https://unaroused-uncontributively-kalyn.ngrok-free.dev

| Service | Wrapper | Purpose |
|---|---|---|
| `receiptiq` | `run-app.sh` | Django via gunicorn on `APP_PORT` |
| `receiptiq-ngrok` | `run-ngrok.sh` | Stable public URL, works without the VPN |
| `receiptiq-tunnel` | `run-cloudflared.sh` | Cloudflare backup route |

## Why wrappers instead of systemd's EnvironmentFile

`EnvironmentFile=/home/siresoft/receiptiq/.env` does not work here. systemd
reads that file as PID 1, and SELinux (Enforcing on this host) denies `init_t`
access to `user_home_t`, so every start fails with:

    Failed to load environment files: Permission denied

The wrapper runs as `siresoft`, who owns the file, so sourcing `.env` succeeds.

## Install

    cp deploy/*.sh deploy/*.service ~/receiptiq/deploy/
    chmod +x ~/receiptiq/deploy/run-*.sh

    # SELinux: scripts under /home are user_home_t, which systemd may not
    # execute. Relabel them as bin_t or every start fails with status=203/EXEC.
    sudo chcon -t bin_t ~/receiptiq/deploy/run-*.sh

    sudo cp ~/receiptiq/deploy/*.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now receiptiq receiptiq-ngrok receiptiq-tunnel

To survive a full filesystem relabel, make the context permanent:

    sudo semanage fcontext -a -t bin_t "/home/siresoft/receiptiq/deploy/run-.*\.sh"
    sudo restorecon -v ~/receiptiq/deploy/run-*.sh

## Changing the port

Edit `APP_PORT` in `~/receiptiq/.env`, then:

    sudo systemctl restart receiptiq receiptiq-ngrok receiptiq-tunnel

All three pick up the new value. Open the new port in firewalld if it is not
already allowed:

    sudo firewall-cmd --permanent --add-port=<port>/tcp && sudo firewall-cmd --reload

## Health check

    systemctl is-active receiptiq receiptiq-ngrok receiptiq-tunnel
    curl -I http://10.0.2.13:8001/

## Cloudflare URL

The Cloudflare quick tunnel is issued a new hostname every restart. Read the
current one with:

    journalctl -u receiptiq-tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1

The ngrok URL is reserved to the account and does not change.
