"""
Price Tracker
-------------
Watches product pages, logs every check to a CSV, and emails you
when a price drops below your target.

Usage:
    python tracker.py                 # check every product once
    python tracker.py --no-email      # check and log, skip notifications
    python tracker.py --config my.json

Config lives in config.json. See config.example.json.
"""

import argparse
import csv
import json
import os
import random
import smtplib
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HISTORY_FILE = Path("price_history.csv")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def load_config(path):
    """Read the JSON config, with a clear error if it's missing or malformed."""
    config_path = Path(path)
    if not config_path.exists():
        sys.exit(
            f"No config found at {config_path}.\n"
            "Copy config.example.json to config.json and fill it in."
        )
    try:
        with config_path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"config.json is not valid JSON: {e}")


def fetch(url, timeout=20):
    """Get a page, with a rotated user agent and a readable error on failure."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def parse_price(text):
    """
    Turn a messy price string into a float.

    Handles: '$1,299.00'  '₹2,499'  'USD 45.90'  '1.299,00 €'
    """
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch in ".,")
    if not cleaned:
        raise ValueError(f"no digits found in {text!r}")

    # European format: 1.299,00  ->  last separator is a comma
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Comma could be decimal (19,99) or thousands (1,299)
        if len(cleaned.split(",")[-1]) == 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    return float(cleaned)


def scrape_product(product):
    """Return (name, price) for one product entry from the config."""
    html = fetch(product["url"])
    soup = BeautifulSoup(html, "html.parser")

    price_el = soup.select_one(product["price_selector"])
    if price_el is None:
        raise LookupError(
            f"price selector {product['price_selector']!r} matched nothing"
        )
    price = parse_price(price_el.get_text(strip=True))

    name = product.get("name")
    if not name and product.get("name_selector"):
        name_el = soup.select_one(product["name_selector"])
        name = name_el.get_text(strip=True) if name_el else None

    return name or product["url"], price


def log_row(name, url, price, status):
    """Append one line to the history CSV, writing a header on first run."""
    new_file = not HISTORY_FILE.exists()
    with HISTORY_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["checked_at", "product", "price", "status", "url"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            name,
            f"{price:.2f}" if price is not None else "",
            status,
            url,
        ])


def previous_price(url):
    """Last recorded price for this URL, or None if we've never seen it."""
    if not HISTORY_FILE.exists():
        return None
    last = None
    with HISTORY_FILE.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["url"] == url and row["price"]:
                last = float(row["price"])
    return last


def send_email(settings, subject, body):
    """Send one notification. Credentials come from environment variables."""
    user = os.environ.get("TRACKER_EMAIL")
    password = os.environ.get("TRACKER_PASSWORD")

    if not user or not password:
        print("  ! TRACKER_EMAIL / TRACKER_PASSWORD not set, skipping email")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = settings["notify_email"]
    msg.set_content(body)

    with smtplib.SMTP_SSL(settings["smtp_host"], settings["smtp_port"]) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    print(f"  > emailed {settings['notify_email']}")


def check_product(product, settings, allow_email):
    """Scrape one product, log it, and notify if it hit the target."""
    url = product["url"]
    try:
        name, price = scrape_product(product)
    except Exception as e:
        print(f"  x failed: {type(e).__name__}: {e}")
        log_row(product.get("name", url), url, None, f"error: {type(e).__name__}")
        return

    before = previous_price(url)
    target = product.get("target_price")

    if before is None:
        change = "first check"
    elif price < before:
        change = f"down from {before:.2f}"
    elif price > before:
        change = f"up from {before:.2f}"
    else:
        change = "no change"

    hit_target = target is not None and price <= target
    status = "TARGET HIT" if hit_target else change

    print(f"  {name[:52]:<54} {price:>9.2f}   {status}")
    log_row(name, url, price, status)

    if hit_target and allow_email:
        send_email(
            settings,
            subject=f"Price drop: {name} is now {price:.2f}",
            body=(
                f"{name}\n\n"
                f"Current price: {price:.2f}\n"
                f"Your target:   {target:.2f}\n"
                f"Previous:      {before if before is not None else 'n/a'}\n\n"
                f"{url}\n"
            ),
        )


def main():
    parser = argparse.ArgumentParser(description="Track product prices over time.")
    parser.add_argument("--config", default="config.json", help="path to config file")
    parser.add_argument("--no-email", action="store_true", help="log only, don't notify")
    args = parser.parse_args()

    config = load_config(args.config)
    products = config.get("products", [])
    settings = config.get("settings", {})
    delay = settings.get("delay_seconds", 3)

    if not products:
        sys.exit("No products in config.")

    print(f"\nChecking {len(products)} product(s) at "
          f"{datetime.now():%Y-%m-%d %H:%M}\n")

    for i, product in enumerate(products):
        check_product(product, settings, allow_email=not args.no_email)
        if i < len(products) - 1:
            time.sleep(delay)   # be polite to the server

    print(f"\nDone. History saved to {HISTORY_FILE}\n")


if __name__ == "__main__":
    main()
