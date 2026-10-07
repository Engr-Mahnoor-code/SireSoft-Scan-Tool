#!/bin/bash
# One-off: move the server install from ~/siresoft-receiptiq to
# ~/siresoft-scan-tool and swap the siresoft-receiptiq* systemd services for
# siresoft-scan-tool*.
#
# Run it from the OLD folder, after `git pull`:
#     cd ~/siresoft-receiptiq && git pull && bash deploy/rename-on-server.sh
#
# The database is not renamed: DB_NAME in .env still points at the same one,
# so every user and receipt carries over.
set -euo pipefail

OLD_DIR="$HOME/siresoft-receiptiq"
NEW_DIR="$HOME/siresoft-scan-tool"
OLD=siresoft-receiptiq
NEW=siresoft-scan-tool

if [ -d "$NEW_DIR" ]; then
    echo "[ERROR] $NEW_DIR already exists - nothing moved." >&2
    exit 1
fi
if [ ! -d "$OLD_DIR" ]; then
    echo "[ERROR] $OLD_DIR not found." >&2
    exit 1
fi

echo "[1/6] Stopping the old services ..."
was_enabled=()
for suffix in "" -worker -ngrok -tunnel; do
    if systemctl is-enabled --quiet "$OLD$suffix" 2>/dev/null; then
        was_enabled+=("$suffix")
    fi
    sudo systemctl disable --now "$OLD$suffix" 2>/dev/null || true
    sudo rm -f "/etc/systemd/system/$OLD$suffix.service"
done
sudo systemctl daemon-reload

echo "[2/6] Moving $OLD_DIR -> $NEW_DIR ..."
mv "$OLD_DIR" "$NEW_DIR"
cd "$NEW_DIR"

echo "[3/6] Admin account settings in .env ..."
set_env() {
    # Replace KEY=... if present, otherwise append it.
    if grep -q "^$1=" .env; then
        sed -i "s|^$1=.*|$1=$2|" .env
    else
        echo "$1=$2" >> .env
    fi
}
set_env ADMIN_USERNAME admin
set_env ADMIN_EMAIL admin@siresoft.com
if ! grep -q '^ADMIN_PASSWORD=.\+' .env; then
    read -r -s -p "Admin password to set: " pw; echo
    set_env ADMIN_PASSWORD "$pw"
fi
grep -q '^USER_DATA_TTL_HOURS=' .env || set_env USER_DATA_TTL_HOURS 24
set_env APP_PORT 9000
chmod 600 .env

echo "[4/6] Database, admin account, static files ..."
./venv/bin/python manage.py migrate
./venv/bin/python manage.py ensure_admin
./venv/bin/python manage.py collectstatic --noinput

echo "[5/6] Installing the $NEW services ..."
chmod +x deploy/*.sh
# SELinux: systemd may only execute scripts labelled bin_t.
if command -v semanage >/dev/null; then
    sudo semanage fcontext -a -t bin_t "$NEW_DIR/deploy/.*\.sh" 2>/dev/null \
        || sudo semanage fcontext -m -t bin_t "$NEW_DIR/deploy/.*\.sh"
    sudo restorecon -v deploy/*.sh
elif command -v chcon >/dev/null; then
    sudo chcon -t bin_t deploy/*.sh 2>/dev/null || true
fi
if command -v firewall-cmd >/dev/null; then
    sudo firewall-cmd --permanent --add-port=9000/tcp
    sudo firewall-cmd --reload
fi
sudo cp deploy/$NEW*.service /etc/systemd/system/
sudo systemctl daemon-reload

echo "[6/6] Starting ..."
sudo systemctl enable --now "$NEW" "$NEW-worker"
for suffix in "${was_enabled[@]}"; do
    case "$suffix" in
        -ngrok|-tunnel) sudo systemctl enable --now "$NEW$suffix" ;;
    esac
done

sleep 3
systemctl is-active "$NEW" "$NEW-worker" || true
echo
echo "Done. The project now lives in $NEW_DIR."
echo "From here on:  cd ~/siresoft-scan-tool"
echo "Open:  http://10.0.2.2:9000/   (admin: http://10.0.2.2:9000/admin/)"
