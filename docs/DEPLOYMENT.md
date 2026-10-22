# Deploying FinPulse

Everything here is free to run. You need [Docker](https://docs.docker.com/get-docker/) (with Compose) and a machine that stays on.

## Quick start

```bash
docker compose up -d --build
```

Open <http://localhost:8080>. The market data, signals and charts work immediately. Paper trading asks you to create an account (an email and a password; no email is ever sent).

Optional: download the historical NIFTY 50 / Apple / BTC / ETH data used by the "Historical price analytics" panel (needs internet; takes a minute):

```bash
docker compose --profile seed run --rm seed
```

## What runs

| Container | Role |
|---|---|
| `web` | nginx serving the built React app, forwarding `/api` and `/ws` to `api`. The only published port (`8080`). |
| `api` | FastAPI: live Binance feed, signals, backtests, accounts, paper trading. Not published; reachable only through `web`. |
| `caddy` (optional) | Free automatic HTTPS, see below. |

All state is one SQLite file in the `finpulse-data` Docker volume (WAL mode). Containers run as non-root with a read-only filesystem and no extra Linux capabilities.

The API runs **one worker on purpose**: the live price feed, the WebSocket hub and the login rate limiter live in that process's memory. Do not scale it to several replicas.

## Settings

Set them in your shell or in a `.env` file next to `docker-compose.yml` (see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `WEB_PORT` | `8080` | Port the site is served on. |
| `ALLOW_REGISTRATION` | `true` | Set `false` once your own accounts exist to stop strangers signing up. |
| `COOKIE_SECURE` | `false` | Must be `true` whenever the site is served over HTTPS (the HTTPS file sets it for you). |
| `SESSION_DAYS` | `30` | How long a login lasts. |
| `PUBLIC_URL` | `http://localhost:8080` | The address people use to reach the site. **Set this in production:** links in emails are built from it. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` | empty | Outgoing email; see [Email](#email-verification-and-password-reset). Empty means email is off. |
| `REQUIRE_EMAIL_VERIFICATION` | on when email is set up | Whether new accounts must confirm their address before paper trading. |
| `PAPER_STARTING_CASH` | `100000` | Virtual starting balance for new accounts. |
| `PAPER_FEE_PCT` | `0.1` | Simulated fee per trade. |
| `LIVE_SYMBOLS` | BTC, ETH, SOL, BNB, XRP | Coins to stream (Binance `XXX/USDT` pairs). |

## Email (verification and password reset)

Email is optional. **Without it** nothing changes: accounts work immediately, and the operator handles password resets with the admin commands below. **With it**:

- New accounts must click a confirmation link before they can paper trade (everything else stays open). This stops people registering with an address that isn't theirs.
- **Forgot password** on the sign-in form emails a one-time link. Using it signs the account out everywhere and also confirms the address, so it doubles as the recovery path if someone registered your address before you did.

Links work once, expire (24 hours to confirm, 60 minutes to reset), are stored only as hashes, and are built from `PUBLIC_URL`, never from the request.

**Any SMTP account works, and free ones exist.** Examples (check each provider's current free limits and terms yourself):

| Provider | Notes |
|---|---|
| Gmail | Needs 2-step verification and an [app password](https://myaccount.google.com/apppasswords): `smtp.gmail.com`, port 587. Fine for a personal deployment; messages from a personal address can land in spam. |
| Brevo, Resend, Mailjet | Have free tiers and, once you verify your domain, send with proper SPF/DKIM so mail is delivered reliably. Better for a public site. |

Put the settings in `.env`:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-character-app-password
EMAIL_FROM=FinPulse <you@gmail.com>
PUBLIC_URL=https://finpulse.example.com
```

then `docker compose up -d`. Port 587 uses STARTTLS automatically; port 465 uses TLS from the start.

**Try it without a real mail account.** This starts a local inbox that catches every email, with a web page to read them:

```bash
docker compose -f docker-compose.yml -f docker-compose.mail.yml up -d --build
```

Register at <http://localhost:8080>, then read the confirmation email at <http://localhost:8025>. Nothing leaves your machine.

If you turn email on after people have already signed up, their accounts show as unconfirmed: they are asked to confirm on their next visit, or you can mark them with `python -m backend.admin verify-user`.

## HTTPS (needed for any public deployment)

Without HTTPS, passwords and login cookies cross the internet in clear text. Do not expose the plain-HTTP port publicly.

**Option A: Caddy with a domain (free certificates).** Point a domain (or a free dynamic-DNS subdomain such as DuckDNS) at the machine, open ports 80 and 443, then:

```bash
DOMAIN=finpulse.example.com docker compose \
  -f docker-compose.yml -f docker-compose.https.yml up -d --build
```

Caddy obtains and renews the Let's Encrypt certificate itself.

**Option B: Cloudflare Tunnel (free, no open ports, no domain setup on the router).** Run the stack normally, then create a tunnel to `http://localhost:8080` with `cloudflared` and set `COOKIE_SECURE=true`.

> I tested the base stack end to end. The Caddy file and Cloudflare Tunnel setup are standard configurations, but I could not issue real certificates or create a tunnel from a development machine, so treat the first run as something to verify.

## Free places to host it

- **Your own computer or a spare/old PC** with Option B: costs nothing. It must stay on, and its internet connection is the service's connection.
- **A free-forever cloud VM** (for example Oracle Cloud's "Always Free" instances) with Option A: install Docker, clone the repo, run the HTTPS command above. Free-tier terms change, so check the provider's current offer.
- **Not recommended: free app platforms** (Render, Fly.io, Railway free tiers). They put idle apps to sleep, which drops the live price stream, and many have no persistent disk, so the SQLite database (all accounts and portfolios) would be wiped on redeploy. Using them would need a hosted database, which this project does not support yet.

## Operating it

```bash
docker compose logs -f api          # watch the API
git pull && docker compose up -d --build   # update to the latest code
docker compose down                 # stop (data is kept in the volume)
```

**Accounts.** With email set up, people reset their own passwords. These commands are for everything else (and for deployments without email):

```bash
docker compose exec api python -m backend.admin list-users
docker compose exec api python -m backend.admin verify-user someone@example.com
docker compose exec api python -m backend.admin set-password someone@example.com
docker compose exec api python -m backend.admin delete-user someone@example.com
```

`verify-user` confirms an address without an email round trip. `set-password` also signs that person out everywhere. `delete-user` removes the account, its sessions and all of its paper-trading history.

**Backups.** Take a consistent copy of the database while it is running:

```bash
docker compose exec api python -c "import sqlite3; s=sqlite3.connect('/app/data/finpulse.db'); d=sqlite3.connect('/app/data/backup.db'); s.backup(d)"
docker compose cp api:/app/data/backup.db ./finpulse-backup.db
```

## Known limitations

- **Single instance.** In-memory rate limits reset when the API restarts (the remembered networks live in the database and persist).
- **Email needs an SMTP account.** Without one there is no verification or emailed reset. With one, deliverability is up to the provider: a verified domain avoids the spam folder. Turn registration off with `ALLOW_REGISTRATION=false` for a private deployment.
- **Login throttling.** Five wrong passwords block that email *from that IP address* for 15 minutes, so a stranger cannot lock you out from their own network; someone behind the same shared address as you (one office or household NAT) could. Guessing spread over many addresses trips a per-email ceiling (60 failures in 15 minutes); while it is active, only networks you have signed in from within the last 30 days can still try, so you are safe on your usual networks, but signing in from somewhere new waits until it ends.
- **Binance availability.** Binance blocks some regions. The API automatically tries `data-stream.binance.vision` / `data-api.binance.vision` as a fallback; if both are blocked from your server, set `BINANCE_WS_URLS` / `BINANCE_REST_URLS` to another reachable endpoint.
- **Paper trading is a simulation.** Fills use the live price with a flat fee and no slippage, so real trades would differ. Signals are educational, not advice, and the backtests show no consistent edge.
