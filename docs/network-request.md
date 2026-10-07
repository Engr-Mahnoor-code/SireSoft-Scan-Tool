# Network request: public access for ReceiptIQ

ReceiptIQ runs on `lsnet` (`10.0.2.2`) and is reachable today only from inside
the VPN, at `http://10.0.2.2:9000`. Staff need to reach it from outside as well.

It is currently served through a temporary Cloudflare quick tunnel. That works,
but the hostname is random, it changes on every restart, and it is not something
we want to hand to a client. Two changes would let us drop it and serve the app
on our own domain instead.

## 1. DNS record

On `ns1.siresoft.com` / `ns2.siresoft.com`:

    receipts.siresoft.com.    IN  A    <the public IP chosen below>

Any hostname is fine — `receipts.siresoft.com` is only a suggestion. It just
needs to be one we control and can keep.

## 2. Port forward

Forward inbound TCP from that public IP to the application server:

| Public port | Destination | Why |
|---|---|---|
| 443 | `10.0.2.2:443` | HTTPS, the address people will use |
| 80 | `10.0.2.2:80` | Let's Encrypt renews the certificate over port 80 |

Port 80 is only used for certificate issuance and renewal; all real traffic is
redirected to HTTPS. If DNS-01 validation is preferred instead, port 80 can be
left closed — say which you prefer.

Note this is **443/80, not 9000**. A reverse proxy on the server will terminate
TLS and pass requests to the application on 9000 internally, so 9000 itself
never needs to be exposed.

## What happens on the server afterwards

Handled on our side, no further network work needed:

- Install a reverse proxy on `10.0.2.2` terminating TLS on 443
- Obtain and auto-renew a Let's Encrypt certificate
- Add the hostname to Django's `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
- Shut down the Cloudflare tunnel

## Security

The application requires a login on every page; there is no anonymous access,
and no part of it is readable without signing in. Receipts are processed by a
model running locally on `lsnet` — no receipt data is sent to any external
service, and that stays true after this change.

If exposing it directly is not acceptable, the alternative is to keep it on the
VPN only and drop external access altogether. That is a reasonable call to make;
we just need to know which way to go.

## Questions we need answered

1. Which public IP should `receipts.siresoft.com` point at?
2. Is forwarding 443 (and 80) to `10.0.2.2` acceptable, or is there a preferred
   reverse proxy or DMZ host it should sit behind instead?
