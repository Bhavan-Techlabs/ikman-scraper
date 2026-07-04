"""
Scraper for lankapropertyweb.com property listings.
Parses HTML with BeautifulSoup (no embedded JSON).
"""
import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lankapropertyweb.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def extract_location_name(url):
    """Extract a readable location name from a lankapropertyweb URL."""
    # Pattern: /forsale-Central_Kandy-all.html  or  /sale/index.php?location=Central_Kandy
    parsed = urlparse(url)
    path = parsed.path

    # /forsale-LOCATION-all.html  e.g. Western_Piliyandala → Piliyandala, Ja+Ela → Ja Ela
    match = re.search(r"/forsale-(.+?)-all\.html", path)
    if match:
        raw = match.group(1).replace("_", " ").replace("+", " ").title()
        # Drop leading region prefix (e.g. "Western ", "Central ", "Southern ")
        raw = re.sub(r"^[A-Z][a-z]+ ", "", raw)
        return raw

    # query param location=
    qs = parse_qs(parsed.query)
    if "location" in qs:
        return qs["location"][0].replace("_", " ").title()

    return "LankaPropertyWeb"


def _build_page_url(base_url, page_no):
    """Build the URL for a given page number."""
    if page_no == 1:
        return base_url

    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query)

    # /forsale-LOCATION-all.html uses query params for paging
    match = re.search(r"/forsale-(.+?)-all\.html", parsed.path)
    if match:
        location = match.group(1)
        params = {
            "page": page_no,
            "location": location.replace("_", " "),
            "searchbox": location.split("_")[-1],
            "neighbourhoods": "Y",
        }
        new_query = urlencode(params)
        new_parsed = parsed._replace(
            path="/sale/index.php",
            query=new_query,
        )
        return urlunparse(new_parsed)

    # Already an index.php style URL
    qs["page"] = [str(page_no)]
    new_query = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse(parsed._replace(query=new_query))


def _fetch_html(url, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.text
            logger.warning("Attempt %d/%d HTTP %d for %s", attempt, max_retries, resp.status_code, url)
        except requests.RequestException as e:
            logger.warning("Attempt %d/%d error for %s: %s", attempt, max_retries, url, e)
        if attempt < max_retries:
            time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts")


def _parse_price(text):
    """Extract the Rs numeric value from a price string."""
    if not text:
        return None, ""
    # Take the first Rs. value before any parenthetical conversions
    match = re.search(r"Rs\.?\s*([\d,]+(?:\.\d+)?)\s*([MBK])?", text, re.IGNORECASE)
    if not match:
        return None, text.strip()
    raw = match.group(1).replace(",", "")
    multiplier = {"M": 1_000_000, "B": 1_000_000_000, "K": 1_000}.get(
        (match.group(2) or "").upper(), 1
    )
    return int(float(raw) * multiplier), text.strip()


def _parse_posted_date(text):
    """Convert '36 days ago' / 'just now' style text to YYYY-MM-DD."""
    if not text:
        return ""
    ts = text.strip().lower()
    now = datetime.now()

    if "just now" in ts or "today" in ts:
        return now.strftime("%Y-%m-%d")

    match = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?", ts)
    if not match:
        return ""
    value = int(match.group(1))
    unit = match.group(2)
    deltas = {
        "second": timedelta(seconds=value),
        "minute": timedelta(minutes=value),
        "hour": timedelta(hours=value),
        "day": timedelta(days=value),
        "week": timedelta(weeks=value),
        "month": timedelta(days=value * 30),
        "year": timedelta(days=value * 365),
    }
    return (now - deltas.get(unit, timedelta())).strftime("%Y-%m-%d")


def _parse_listing_cards(html, price_min, price_max):
    """Parse listing cards from a search results page."""
    soup = BeautifulSoup(html, "lxml")
    ads = []

    for a_tag in soup.find_all("a", href=re.compile(r"/sale/property_details-\d+\.html")):
        href = a_tag.get("href", "")
        ad_url = urljoin(BASE_URL, href)

        title_tag = a_tag.find(["h4", "h5"])
        title = title_tag.get_text(strip=True) if title_tag else ""

        price_tag = a_tag.find(class_="price")
        price_text = price_tag.get_text(strip=True) if price_tag else ""
        numeric_price, price_raw = _parse_price(price_text)

        if price_min and numeric_price and numeric_price < price_min:
            continue
        if price_max and numeric_price and numeric_price > price_max:
            continue

        location_tags = a_tag.find_all("p")
        location_text = ""
        for p in location_tags:
            if "price" not in (p.get("class") or []):
                location_text = p.get_text(strip=True)
                break

        ads.append({
            "title": title,
            "price_raw": price_raw,
            "price_numeric": numeric_price,
            "location": location_text,
            "ad_url": ad_url,
            "slug": re.search(r"property_details-(\d+)", href).group(1) if re.search(r"property_details-(\d+)", href) else "",
            "time_stamp": "",
        })

    return ads


def _has_next_page(html, current_page):
    """Check whether a next page link exists."""
    soup = BeautifulSoup(html, "lxml")
    next_page = str(current_page + 1)
    for a in soup.find_all("a", href=True):
        if f"page={next_page}" in a["href"] or a.get_text(strip=True) == next_page:
            return True
    return False


def get_listings(base_url, config):
    """Scrape all listing pages and return summary dicts."""
    max_pages = config.get("max_pages", 20)
    request_delay = config.get("request_delay", 1.5)
    pf = config.get("price_filter") or {}
    price_min = pf.get("min")
    price_max = pf.get("max")

    all_ads = []

    for page_no in range(1, max_pages + 1):
        page_url = _build_page_url(base_url, page_no)
        logger.info("Fetching listing page %d: %s", page_no, page_url)

        html = _fetch_html(page_url)
        ads = _parse_listing_cards(html, price_min, price_max)
        logger.info("Page %d: found %d ads", page_no, len(ads))

        if not ads:
            logger.info("No ads found on page %d, stopping", page_no)
            break

        all_ads.extend(ads)

        if not _has_next_page(html, page_no):
            logger.info("No next page after page %d, stopping", page_no)
            break

        time.sleep(request_delay)

    logger.info("Collected %d ads from lankapropertyweb", len(all_ads))
    return all_ads


def get_ad_details(ad_url, request_delay=1.5):
    """Fetch and parse a single property details page."""
    time.sleep(request_delay)
    html = _fetch_html(ad_url)
    soup = BeautifulSoup(html, "lxml")

    # Description
    desc = ""
    for section in soup.find_all(["section", "div"]):
        h = section.find(["h2", "h3"])
        if h and "property details" in h.get_text(strip=True).lower():
            p = section.find("p")
            if p:
                desc = p.get_text(strip=True)
            break

    # Specs from <dl><dt>/<dd> pairs
    spec_map = {}
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            spec_map[dt.get_text(strip=True).lower()] = dd.get_text(strip=True)

    # Posted date
    posted_raw = ""
    for tag in soup.find_all(string=re.compile(r"Posted", re.I)):
        posted_raw = tag.strip()
        break

    # Floor area → house_size, land_size
    floor_area = spec_map.get("floor area", "")
    bedrooms = (
        spec_map.get("bedrooms", "")
        or spec_map.get("units/rooms", "")
        or spec_map.get("no. of bedrooms", "")
    )
    bathrooms = (
        spec_map.get("bathrooms", "")
        or spec_map.get("bathrooms/wcs", "")
        or spec_map.get("no. of bathrooms", "")
    )
    land_size = spec_map.get("land size", "") or spec_map.get("land extent", "")
    address = spec_map.get("address", "")

    return {
        "description": desc,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "land_size": land_size,
        "house_size": floor_area,
        "address": address,
        "posted_date": _parse_posted_date(posted_raw),
    }
