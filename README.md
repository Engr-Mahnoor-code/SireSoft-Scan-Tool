# SireSoft Scan Tool

## Yeh project kya hai?

Ek website jahan user **receipt / bill ki photo ya PDF upload** karta hai, aur
app khud us receipt ko parh kar data nikaal leti hai: dukaan ka naam, date,
items, total. Yeh data **PostgreSQL** database mein save hota hai aur user use
**History** page par dekh sakta hai, edit kar sakta hai, delete kar sakta hai.

Receipt parhne ka kaam ek **local AI model** (Ollama + `qwen2.5vl:3b`) karta hai
jo isi server par chalta hai. Koi data bahar internet par nahin jaata.

Project ke 3 hisse:

| Hissa | Kaam |
|---|---|
| Website (Django + gunicorn) | Login, upload, History, admin panel |
| Worker (`manage.py process_receipts`) | Background mein receipts AI ko bhej kar data nikaalta hai |
| PostgreSQL | Users aur receipts ka data |

## Kaun kya dekh sakta hai

| Kaun | Kya dekh sakta hai |
|---|---|
| **Admin** (`admin@siresoft.com`) | **Sab users ki** sab receipts (History mein "Uploaded By" column ke saath) aur Django Administration |
| **Aam user** | Sirf **apni** receipts |

## 24 ghante baad data khud delete

Har aam user ka apna 24 ghante ka clock hai, jo **uske sign-up ke waqt se** shuru hota hai:

- User 3:00 baje sign-up kare → agle din 3:00 baje uska account **aur** uski
  saari receipts (database rows + upload ki hui files) delete.
- Doosra user 9:30 baje aaye → uska clock 9:30 se, agle din 9:30 baje delete.
- **Admin kabhi delete nahin hota.**

Yeh har minute khud chalta hai (worker mein bhi aur website mein bhi), koi cron
nahin chahiye. User ko History page par likha nazar aata hai ke uska data kab
delete hoga. Ghante badalne hon to `.env` mein `USER_DATA_TTL_HOURS=24` badlen.
Haath se chalana ho: `python manage.py purge_expired_users`

## Login

| Kahan | Email / Username | Password |
|---|---|---|
| App login | `admin@siresoft.com` | `.env` ka `ADMIN_PASSWORD` |
| Django Administration (`/admin/`) | `admin` **ya** `admin@siresoft.com` | `.env` ka `ADMIN_PASSWORD` |

Password GitHub par nahin jaata, sirf `.env` mein hota hai (`ADMIN_EMAIL`, `ADMIN_PASSWORD`).
`python manage.py ensure_admin` database ko `.env` ke mutabiq kar deta hai.
Server par app restart hone par yeh khud chal jaata hai.

## Links (URLs)

Neeche `<BASE>` ki jagah apna address lagayen:

| Jagah | `<BASE>` |
|---|---|
| Apne laptop par (`python manage.py runserver`) | `http://127.0.0.1:9000` |
| Server, VPN on | `http://10.0.2.2:9000` |
| Server, VPN off | ngrok address (`.env` mein `NGROK_URL`) |

| Kya kholna hai | Link |
|---|---|
| App login | `<BASE>/auth/login/` |
| Receipt upload | `<BASE>/` |
| History | `<BASE>/history/` |
| **Django Administration** | `<BASE>/admin/` |
| Database mein saari receipts | `<BASE>/admin/receipts/receipt/` |
| Database mein saare users | `<BASE>/admin/auth/user/` |

Data save hua ya nahin dekhne ke liye: `<BASE>/admin/` kholen → `admin` aur
admin password se login → **Receipts** par click.

## Apne laptop par chalana

    venv\Scripts\activate
    python manage.py migrate
    python manage.py ensure_admin
    python manage.py runserver          # website, port 9000
    python manage.py process_receipts   # doosri terminal mein: worker

Ollama chal raha hona chahiye aur model pulled: `ollama pull qwen2.5vl:3b`

## Server par pehli dafa naam badalna (siresoft-receiptiq → siresoft-scan-tool)

Sirf ek dafa, purane folder se:

    ssh siresoft@10.0.2.2
    cd ~/siresoft-receiptiq
    git pull
    bash deploy/rename-on-server.sh

Script purani services band karti hai, folder ko `~/siresoft-scan-tool` kar
deti hai, nayi services lagati hai, `.env` mein admin ki lines daalti hai
(password ek dafa poochti hai) aur app start kar deti hai. Database wohi rehta
hai, data safe.

## Server par update karna

    ssh siresoft@10.0.2.2
    cd ~/siresoft-scan-tool
    git pull
    sudo restorecon -v deploy/*.sh
    ./venv/bin/python manage.py migrate
    ./venv/bin/python manage.py ensure_admin
    ./venv/bin/python manage.py collectstatic --noinput
    sudo systemctl restart siresoft-scan-tool siresoft-scan-tool-worker

Chal raha hai ya nahin: `systemctl is-active siresoft-scan-tool siresoft-scan-tool-worker`
(dono "active" aane chahiyen).

Server pehli baar install karna ho to poori detail: [deploy/README.md](deploy/README.md)

## Folders

| Folder | Kya hai |
|---|---|
| `apps/accounts/` | Login, sign-up, admin account, 24-ghante wala delete |
| `apps/receipts/` | Upload, History, AI se parhna, worker |
| `templates/`, `static/` | Pages ka HTML / CSS |
| `config/` | Django settings aur URLs |
| `deploy/` | Server ke scripts aur systemd services |
| `pictures/` | Test karne ke liye sample receipts |
