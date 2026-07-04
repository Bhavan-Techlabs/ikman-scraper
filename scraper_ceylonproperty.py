"""
Scraper for ceylonproperty.lk property listings.
Parses HTML with BeautifulSoup (server-side rendered, no embedded JSON).
"""
import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://ceylonproperty.lk"

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
    """Extract a readable location name from a ceylonproperty URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    if "city" in qs:
        return qs["city"][0].replace("-", " ").replace("_", " ").title()
    if "district" in qs:
        return qs["district"][0].replace("-", " ").replace("_", " ").title()

    return "CeylonProperty"


def _build_page_url(base_url, page_no):
    """Build the URL for a given page number."""
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)

    if page_no == 1:
        qs.pop("page", None)
    else:
        qs["page"] = [str(page_no)]

    # ceylonproperty uses sort=boosted on paginated pages
    if page_no > 1 and "sort" not in qs:
        qs["sort"] = ["boosted"]

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
    """Extract a numeric LKR value from strings like '50 Million (neg)' or '50,000,000 LKR'."""
    if not text:
        return None, ""
    clean = text.strip()

    # Format: "50,000,000 LKR ..."
    match = re.search(r"([\d,]+)\s*LKR", clean, re.IGNORECASE)
    if match:
        numeric = int(match.group(1).replace(",", ""))
        return numeric, clean

    # Format: "50 Million" / "1.5 Billion"
    match = re.search(r"([\d.]+)\s*(Million|Billion|Thousand|M|B|K)", clean, re.IGNORECASE)
    if match:
        val = float(match.group(1))
        mult = {"million": 1_000_000, "m": 1_000_000, "billion": 1_000_000_000, "b": 1_000_000_000,
                "thousand": 1_000, "k": 1_000}.get(match.group(2).lower(), 1)
        return int(val * mult), clean

    return None, clean


def _parse_posted_date(text):
    """Convert 'X minutes/hours/days ago' text to YYYY-MM-DD."""
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
    """Parse property-card divs from a search results page."""
    soup = BeautifulSoup(html, "lxml")
    ads = []

    for card in soup.find_all("div", class_="property-card"):
        a_tag = card.find("a", href=re.compile(r"/property/"))
        if not a_tag:
            continue

        href = a_tag.get("href", "")
        ad_url = urljoin(BASE_URL, href) if href.startswith("/") else href

        title_tag = a_tag.find("h5") or a_tag.find("h4")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Price: last <p> in card (not inside the <a> title link)
        price_text = ""
        for p in card.find_all("p"):
            txt = p.get_text(strip=True)
            if txt and any(c.isdigit() for c in txt):
                price_text = txt

        numeric_price, price_raw = _parse_price(price_text)

        if price_min and numeric_price and numeric_price < price_min:
            continue
        if price_max and numeric_price and numeric_price > price_max:
            continue

        # Location: first <p> that doesn't look like a price
        location_text = ""
        for p in card.find_all("p"):
            txt = p.get_text(strip=True)
            if txt and not any(c.isdigit() for c in txt):
                location_text = txt
                break

        ads.append({
            "title": title,
            "price_raw": price_raw,
            "price_numeric": numeric_price,
            "location": location_text,
            "ad_url": ad_url,
            "time_stamp": "",
        })

    return ads


def _has_next_page(html, current_page):
    """Check whether a next page link exists in the pagination section."""
    soup = BeautifulSoup(html, "lxml")
    next_page = str(current_page + 1)
    pagination = soup.find("div", class_="pagination") or soup.find("ul", class_=re.compile(r"paginat"))
    if pagination:
        for a in pagination.find_all("a", href=True):
            if f"page={next_page}" in a["href"]:
                return True
    # Fallback: search all links
    for a in soup.find_all("a", href=True):
        if f"page={next_page}" in a["href"]:
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

    logger.info("Collected %d ads from ceylonproperty.lk", len(all_ads))
    return all_ads


def get_ad_details(ad_url, request_delay=1.5):
    """Fetch and parse a single property detail page."""
    time.sleep(request_delay)
    html = _fetch_html(ad_url)
    soup = BeautifulSoup(html, "lxml")

    # Title (h3 on detail page)
    title = ""
    h3 = soup.find("h3")
    if h3:
        title = h3.get_text(strip=True)

    # Address / location text
    address = ""
    for p in soup.find_all("p"):
        txt = p.get_text(strip=True)
        if "," in txt and len(txt) < 100 and not any(kw in txt.lower() for kw in ("posted", "lkr", "million")):
            address = txt
            break

    # Specs: look for img alt tags (bedroom/bathroom/landArea/floorAreaSq) followed by sibling h5
    bedrooms = bathrooms = land_size = house_size = ""

    for div in soup.find_all("div"):
        img = div.find("img")
        if not img:
            continue
        alt = (img.get("alt") or img.get("src") or "").lower()
        h5 = div.find("h5")
        val = h5.get_text(strip=True) if h5 else ""
        if not val:
            continue
        if "bedroom" in alt:
            bedrooms = val
        elif "bathroom" in alt:
            bathrooms = val
        elif "landarea" in alt or "land" in alt:
            land_size = val
        elif "floorareasq" in alt or "floor" in alt:
            house_size = val

    # Description
    description = ""
    desc_div = soup.find("div", class_="description")
    if desc_div:
        p = desc_div.find("p")
        description = p.get_text(strip=True) if p else desc_div.get_text(strip=True)

    # Posted date
    posted_date = ""
    for tag in soup.find_all(string=re.compile(r"posted", re.I)):
        posted_date = _parse_posted_date(tag.strip())
        if posted_date:
            break

    return {
        "description": description,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "land_size": land_size,
        "house_size": house_size,
        "address": address,
        "posted_date": posted_date,
    }
