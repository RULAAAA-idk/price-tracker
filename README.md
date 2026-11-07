# Price Tracker

Watches product pages, logs every price check to a CSV, and emails you when
something drops below your target.

Point it at any site by giving it a CSS selector — no code changes needed to
add a new product.

```
Checking 2 product(s) at 2026-11-07 10:24

  Sony WH-1000XM5 Headphones                                279.00   down from 299.00
  Logitech MX Master 3S                                      94.50   TARGET HIT

Done. History saved to price_history.csv
```

## What it does

- Scrapes the current price from any product page via a CSS selector
- Handles messy price formats: `$1,299.00`, `₹2,499`, `1.299,00 €`
- Appends every check to `price_history.csv` so you build a price history
- Compares against the previous check and reports up / down / no change
- Emails you when the price hits a target you set
- Rotates user agents and waits between requests

## Setup

```bash
git clone https://github.com/<your-username>/price-tracker.git
cd price-tracker
pip install -r requirements.txt
cp config.example.json config.json
```

Then edit `config.json`.

## Configuration

```json
{
  "settings": {
    "notify_email": "you@example.com",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "delay_seconds": 3
  },
  "products": [
    {
      "name": "Sony WH-1000XM5",
      "url": "https://example.com/product/wh1000xm5",
      "price_selector": "span.price-now",
      "target_price": 280.00
    }
  ]
}
```

| Field | Required | What it does |
|---|---|---|
| `url` | yes | Product page to check |
| `price_selector` | yes | CSS selector for the price element |
| `name` | no | Label used in output and CSV |
| `name_selector` | no | Scrape the name instead of hardcoding it |
| `target_price` | no | Email when the price is at or below this |

### Finding the price selector

Right-click the price on the page, Inspect, then copy the element's class.
If the price sits in `<span class="price-now">$279.00</span>`, your selector
is `span.price-now`.

## Running it

```bash
python tracker.py                 # check everything, email on target hits
python tracker.py --no-email      # check and log only
python tracker.py --config other.json
```

### Email setup

Credentials are read from environment variables, never from the config file:

```bash
export TRACKER_EMAIL="you@gmail.com"
export TRACKER_PASSWORD="your-app-password"
```

For Gmail you need an [App Password](https://myaccount.google.com/apppasswords),
not your normal account password.

### Running it on a schedule

Daily at 9am via cron:

```
0 9 * * * cd /path/to/price-tracker && /usr/bin/python3 tracker.py
```

On Windows, use Task Scheduler with the same command.

## Output

`price_history.csv` grows one row per product per check:

| checked_at | product | price | status | url |
|---|---|---|---|---|
| 2026-11-07 09:00:04 | Sony WH-1000XM5 | 299.00 | first check | https://... |
| 2026-11-08 09:00:03 | Sony WH-1000XM5 | 279.00 | down from 299.00 | https://... |

Open it in Excel and chart the price column to see the trend.

## Notes

- Scrapes publicly accessible pages only. Check a site's terms of service
  and `robots.txt` before pointing this at it.
- Sites that render prices with JavaScript won't work with `requests`.
  Those need a browser-based scraper such as Playwright.
- Failed checks are logged with an error status rather than crashing the run.

## Built with

Python · requests · BeautifulSoup
