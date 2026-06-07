# house-bot

Daily house listing monitor. Searches Redfin for homes matching your criteria, publishes results to a GitHub Pages site, and sends a desktop notification when new listings or price drops appear.

**Live site:** https://xiangao.github.io/house-bot-site/

## Changing search criteria

All criteria live in one file: **`config/searches.yaml`**

```yaml
search:
  min_price: 900000       # lower price bound
  max_price: 1500000      # upper price bound
  min_beds: 3             # minimum bedrooms
  min_baths: 2            # minimum bathrooms
  min_year_built: 2010    # exclude homes built before this year
                          # (unknown year = always kept, may be renovated)
  property_types: "1,2,3" # 1=house  2=condo  3=townhouse  4=multi-family
```

After editing, run `python main.py` to apply immediately and redeploy the site.

### Adding or removing towns

Towns are listed at the bottom of `config/searches.yaml`. To add one:

1. Find it on Redfin: `https://www.redfin.com/city/NNNNN/MA/TownName`
2. The number in the URL is the `region_id`
3. Add a block:

```yaml
  - name: "Newton, MA"
    region_id: "29777"   # from redfin.com/city/29777/MA/Newton
    region_type: "6"
    market: boston       # use "newhampshire" for NH towns
```

To remove a town, delete or comment out its block.

## Running manually

```bash
cd ~/projects/claude/house-bot
source .venv/bin/activate
python main.py
```

## Automatic schedule

Runs daily at 9am via systemd timer.

```bash
systemctl --user status house-bot.timer   # check status
systemctl --user list-timers house-bot.timer  # next run time
journalctl --user -u house-bot.service    # logs
```

## How it works

1. Queries Redfin's CSV API for each town
2. Filters client-side: price, beds, baths, year built
3. Compares against `data/listings.csv` to find new listings and price drops
4. Computes each house's **driving distance to the nearest MBTA commuter rail
   station** (OSRM, no API key; cached per listing), shown on each card and in
   the email as `🚆 X.X mi · Y min by car to <station>`.
5. Generates `output/listings.html` and deploys it to GitHub Pages. The page
   opens with a **🆕 New in last 7 days** section (listings first seen within
   the rolling window, grouped by town, newest-first), followed by the full
   per-town sections.
5. Sends a desktop notification if anything changed

## Limitations

- **Newly renovated** homes cannot be auto-detected — renovation info is only in individual listing descriptions, not in Redfin's download API. Year built is shown on every card so you can judge manually.
- Redfin's API returns at most ~350 listings per town per query.
- Redfin is behind AWS WAF, which blocks ordinary HTTP clients by TLS fingerprint. The bot uses `curl_cffi` (Chrome impersonation) to get through; if you ever see `403 Request blocked`, bump the impersonation target in `code/searcher.py`.
