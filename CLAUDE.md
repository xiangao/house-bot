# house-bot

Daily house listing monitor using Redfin's unofficial API.

## Setup

1. Copy `.env.example` to `.env` and fill in Gmail credentials (use an App Password)
2. `test -d .venv || python3 -m venv .venv`
3. `source .venv/bin/activate && pip install -r requirements.txt`
4. `python main.py` to run manually

## Systemd Timer (daily at 9am)

```bash
mkdir -p ~/.config/systemd/user
cp house-bot.service house-bot.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now house-bot.timer
```

Logs: `journalctl --user -u house-bot.service`

## Config

`config/searches.yaml` — towns, price range ($800K–$1.2M), bed/bath minimums (3+/2+).

## Output

- `data/listings.csv` — all seen listings with first_seen / last_price for change detection
- `output/latest.txt` — last run summary (new listings + price drops)

## Alert Logic

- **New listing**: listing_id not in data/listings.csv → email
- **Price drop**: same listing_id, price decreased since last run → email
- No email if nothing changed

## API

Uses Redfin unofficial GIS-CSV endpoint. No API key required.
- Autocomplete: `stingray/do/location-autocomplete` resolves town → region_id
- Listings: `stingray/api/gis-csv` returns CSV of matching listings

### Anti-bot (AWS WAF / CloudFront)

Redfin sits behind AWS WAF, which JA3/JA4-fingerprints the TLS ClientHello and
returns `403 Request blocked` to plain `requests` *at the handshake* — before any
header/cookie is read (verified 2026-06-01: same IP, `curl` → 200, `requests` → 403).
`code/searcher.py` therefore uses **`curl_cffi` with `Session(impersonate="chrome")`**
to present a real Chrome TLS fingerprint. Header tweaks alone do nothing.
If 403s return, bump the `_IMPERSONATE` Chrome target in `code/searcher.py`.
