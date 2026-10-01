# Deploying siresoft-receiptiq on lsnet (10.0.2.2)

This project installs as its own deployment, separate from anything already on
the host. Nothing here is shared with an older install — its own folder, venv,
database, port and systemd units.

    Project dir:   /home/siresoft/siresoft-receiptiq
    Service name:  siresoft-receiptiq
    Port:          9001
    Database:      siresoft_receiptiq_db

The wrapper scripts work out the project directory from their own location, so
the same files work if you ever clone somewhere else — only the `.service`
files name a path.

| Service | Wrapper | Purpose |
|---|---|---|
| `siresoft-receiptiq` | `run-app.sh` | Django via gunicorn on `APP_PORT` |
| `siresoft-receiptiq-ngrok` | `run-ngrok.sh` | Stable public URL, works without the VPN |
| `siresoft-receiptiq-tunnel` | `run-cloudflared.sh` | Cloudflare backup route |
| `siresoft-receiptiq-worker` | `run-worker.sh` | Reads receipts with the local Ollama model |

Settings live in one place only — `/home/siresoft/siresoft-receiptiq/.env`:

    APP_PORT=9001
    GUNICORN_WORKERS=3
    GUNICORN_TIMEOUT=600
    NGROK_URL=https://<your-reserved-domain>.ngrok-free.dev
    OLLAMA_BASE_URL=http://localhost:11434
    OLLAMA_MODEL=qwen2.5vl:3b
    OLLAMA_TIMEOUT=900
    OLLAMA_NUM_CTX=8192

## First install

The repo is private, so cloning needs a GitHub personal access token (classic,
scope `repo`). Generate one under Settings -> Developer settings -> Personal
access tokens, and keep it somewhere safe -- GitHub shows it only once.

    ssh siresoft@10.0.2.2

    git clone https://<TOKEN>@github.com/Engr-Mahnoor-code/siresoft-receiptiq.git ~/siresoft-receiptiq
    cd ~/siresoft-receiptiq

Embedding the token in the URL writes it to `.git/config` in plain text. To keep
it out of there, clone without it and let a credential helper cache it instead:

    git clone https://github.com/Engr-Mahnoor-code/siresoft-receiptiq.git ~/siresoft-receiptiq
    cd ~/siresoft-receiptiq
    git config credential.helper store    # paste the token as the password once

This clones into its own folder. An older `~/receiptiq` install on the same host
is untouched -- separate folder, venv, database and port.

    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt gunicorn

Create its own database (the older install keeps its own):

    sudo -u postgres psql -c "CREATE DATABASE siresoft_receiptiq_db;"

Then write `.env` from the template and fill in real values:

    cp .env.example .env
    nano .env          # SECRET_KEY, DB_*, OLLAMA_MODEL, APP_PORT=9001
    chmod 600 .env

`.env` is gitignored and is never overwritten by `git pull`. Keep a copy
somewhere safe — it is the only thing a fresh clone cannot recreate.

    ./venv/bin/python manage.py migrate
    ./venv/bin/python manage.py collectstatic --noinput
    ./venv/bin/python manage.py createsuperuser

## The local model (Ollama)

Receipts are read by a vision model running on this host. There is no API key
and no request leaves the machine, so the only cost is time and memory.

Install Ollama and pull a **vision** model — a text-only model will accept the
request and return nonsense, because it never sees the image:

    curl -fsSL https://ollama.com/install.sh | sh
    sudo systemctl enable --now ollama

    ollama pull qwen2.5vl:3b
    ollama list

| Hardware | Model | Notes |
|---|---|---|
| Any, including CPU only | `qwen2.5vl:3b` | 3.2 GB, strong on printed receipts. The default. |
| GPU with room to spare | `qwen2.5vl:7b` | Larger, better on faint or handwritten print |
| CPU, tight on RAM | `moondream` | Fastest, weakest at small print |

Whatever you pull must match `OLLAMA_MODEL` in `.env`.

**Do not use `llama3.2-vision`.** It is built on the `mllama` architecture,
which Ollama dropped in its newer engine, so on 0.34 it downloads its full
7.8 GB and then fails every single receipt with:

    error loading model: unknown model architecture: 'mllama'

Nothing in the log points at the model choice, so this is worth recognising.

`OLLAMA_NUM_CTX` matters as much as the model. A receipt image costs thousands
of tokens and Ollama's own default is 4096, which a full page overflows:

    request (4351 tokens) exceeds the available context size (4096 tokens)

The service already caps image size (`MAX_IMAGE_EDGE`) and retries once at 60%
scale before giving up, so this should not reach a user — but lowering
`OLLAMA_NUM_CTX` will bring it back.

Expect a local model to be slower than a hosted one: seconds on a GPU, minutes
on a CPU. That is why extraction runs in the worker rather than in the upload
request, and why `OLLAMA_TIMEOUT` defaults to 900 seconds.

PDF receipts are rasterised to an image first (PyMuPDF, `pip install pymupdf`)
because these models read images, not PDFs. Only page 1 is sent, so a
multi-page invoice loses its later pages.

## How a receipt is processed

    upload  ->  row saved as 'pending', request returns immediately
                    |
                worker claims it ('processing')
                    |
                Ollama reads the image
                    |
            'success' with data, or 'failed' with a message

The upload page polls `/api/receipts/status/` and renders each receipt as it
lands. Nothing waits on a request staying open, which matters because ngrok and
Cloudflare both cut connections long before a slow model finishes.

If the worker is not running, uploads still succeed — they simply sit at
"Queued" until it starts.

## Why wrappers instead of systemd's EnvironmentFile

`EnvironmentFile=/home/siresoft/…/.env` does not work here. systemd reads that
file as PID 1, and SELinux (Enforcing on this host) denies `init_t` access to
`user_home_t`, so every start fails with:

    Failed to load environment files: Permission denied

The wrapper runs as `siresoft`, who owns the file, so sourcing `.env` succeeds.

## Install the services

    chmod +x ~/siresoft-receiptiq/deploy/*.sh

    # SELinux: scripts under /home are user_home_t, which systemd may not
    # execute. Relabel them as bin_t or every start fails with status=203/EXEC.
    sudo chcon -t bin_t ~/siresoft-receiptiq/deploy/*.sh

    sudo cp ~/siresoft-receiptiq/deploy/*.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now siresoft-receiptiq siresoft-receiptiq-worker

Open the port:

    sudo firewall-cmd --permanent --add-port=9001/tcp && sudo firewall-cmd --reload

To survive a full filesystem relabel, make the SELinux context permanent:

    sudo semanage fcontext -a -t bin_t "/home/siresoft/siresoft-receiptiq/deploy/.*\.sh"
    sudo restorecon -v ~/siresoft-receiptiq/deploy/*.sh

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
    sudo restorecon -v deploy/*.sh                 # see below - not optional
    ./venv/bin/pip install -r requirements.txt     # only if requirements changed
    ./venv/bin/python manage.py migrate            # only if models changed
    ./venv/bin/python manage.py collectstatic --noinput
    sudo systemctl restart siresoft-receiptiq siresoft-receiptiq-worker

`restorecon` is not optional on this host. `git pull` writes a replacement file
rather than editing in place, so anything it touches comes back labelled
`user_home_t`, and systemd refuses to execute that:

    Failed at step EXEC spawning .../deploy/run-worker.sh: Permission denied
    Main process exited, code=exited, status=203/EXEC

It only works if the `semanage fcontext` rule from "Install the services" was
added. Without that rule, use `sudo chcon -t bin_t deploy/*.sh` instead, and
repeat it after every pull.

`collectstatic` is not optional. WhiteNoise serves hashed filenames from
`staticfiles/`, so without it the server keeps serving the previous CSS and JS
and your changes simply will not appear in the browser.

## Health check

    systemctl is-active siresoft-receiptiq siresoft-receiptiq-worker
    curl -I http://10.0.2.2:9001/
    journalctl -u siresoft-receiptiq -n 50 --no-pager

The worker log is where a stuck receipt explains itself — it names the
model, how long each receipt took, and why any of them failed:

    journalctl -u siresoft-receiptiq-worker -f

To run it by hand instead, stop the service first so the two do not
compete for the queue:

    sudo systemctl stop siresoft-receiptiq-worker
    ./venv/bin/python manage.py process_receipts --once

## Changing the port

Edit `APP_PORT` in `.env`, then:

    sudo systemctl restart siresoft-receiptiq siresoft-receiptiq-ngrok siresoft-receiptiq-tunnel
    sudo firewall-cmd --permanent --add-port=<new-port>/tcp && sudo firewall-cmd --reload

## Cloudflare URL

The Cloudflare quick tunnel gets a new hostname every restart. Read the current
one with:

    journalctl -u siresoft-receiptiq-tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
