import json
import math
import time
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

import requests

DEFAULT_MAX_AGE_DAYS = 14

logger = logging.getLogger(__name__)

URL_PREFIX = "https://ikman.lk/en/ad/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_page(url, max_retries=3):
    """Fetch a page and extract the embedded JSON data from window.initialData."""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.encoding = "utf-8"

            if response.status_code == 200:
                data_str = response.text.split("window.initialData =")[1].split("</script>")[0].strip()
                if data_str.endswith(";"):
                    data_str = data_str[:-1]
                return json.loads(data_str)

            logger.warning("Attempt %d/%d failed (HTTP %d) for %s", attempt, max_retries, response.status_code, url)
        except (requests.RequestException, IndexError, json.JSONDecodeError) as e:
            logger.warning("Attempt %d/%d error for %s: %s", attempt, max_retries, url, e)

        if attempt < max_retries:
            time.sleep(2 * attempt)

    raise RuntimeError(f"Failed to fetch data from {url} after {max_retries} attempts")


def _url_has_price_filter(url):
    """Check if the URL already contains price filter parameters."""
    parsed = parse_qs(urlparse(url).query)
    return "money.price.minimum" in parsed or "money.price.maximum" in parsed


def _extract_location_name(url):
    """Extract a human-readable location name from the URL path."""
    path_parts = urlparse(url).path.strip("/").split("/")
    # URL pattern: /en/ads/{location}/houses-for-sale
    for i, part in enumerate(path_parts):
        if part == "ads" and i + 1 < len(path_parts):
            return path_parts[i + 1].replace("-", " ").title()
    return "Unknown"


def get_listings(base_url, config):
    """
    Scrape all listing pages for a given base URL.
    Returns a list of ad summary dicts with keys: title, price, slug, details, location.
    """
    max_pages = config.get("max_pages", 20)
    request_delay = config.get("request_delay", 1.5)
    price_min = None
    price_max = None

    if not _url_has_price_filter(base_url):
        pf = config.get("price_filter") or {}
        price_min = pf.get("min")
        price_max = pf.get("max")

    max_age_days = config.get("max_age_days", DEFAULT_MAX_AGE_DAYS)

    separator = "&" if "?" in base_url else "?"
    all_ads = []
    max_page_number = -1

    for page_no in range(1, max_pages + 1):
        page_url = f"{base_url}{separator}page={page_no}"
        logger.info("Fetching listing page %d: %s", page_no, page_url)

        data = fetch_page(page_url)
        ads_data = data["serp"]["ads"]["data"]
        ads = ads_data["ads"]

        if max_page_number < 0:
            pagination = ads_data["paginationData"]
            max_page_number = math.ceil(pagination["total"] / pagination["pageSize"])
            logger.info("Total ads: %d, pages: %d", pagination["total"], max_page_number)

        page_has_recent_organic = False

        for ad in ads:
            if ad.get("isBanner"):
                continue

            is_promoted = ad.get("isFeaturedAd") or ad.get("isTopAd")
            timestamp = ad.get("timeStamp", "")
            is_bumped = timestamp.strip().lower() == "bump_up"

            age_days = _parse_age_days(timestamp)

            if not is_promoted and not is_bumped:
                if age_days is not None and age_days > max_age_days:
                    continue
                if age_days is not None:
                    page_has_recent_organic = True

            raw_price = ad.get("price", "")
            numeric_price = _parse_price(raw_price)

            if price_min and numeric_price and numeric_price < price_min:
                continue
            if price_max and numeric_price and numeric_price > price_max:
                continue

            all_ads.append({
                "title": ad.get("title", ""),
                "price_raw": raw_price,
                "price_numeric": numeric_price,
                "slug": ad.get("slug", ""),
                "details": ad.get("details", ""),
                "location": ad.get("location", ""),
                "ad_url": f"{URL_PREFIX}{ad['slug']}" if ad.get("slug") else None,
                "time_stamp": timestamp if not is_bumped else "",
            })

        if not page_has_recent_organic:
            logger.info("No organic ads within %d days on page %d, stopping", max_age_days, page_no)
            break

        if page_no >= max_page_number:
            logger.info("Reached last page (%d)", page_no)
            break

        time.sleep(request_delay)

    logger.info("Collected %d ads from listings", len(all_ads))
    return all_ads


def get_ad_details(ad_url, request_delay=1.5):
    """
    Fetch an individual ad page and extract detailed property information.
    Returns a dict with description, bedrooms, bathrooms, land_size, house_size, address, etc.
    """
    time.sleep(request_delay)
    data = fetch_page(ad_url)

    ad_data = data.get("adDetail", {}).get("data", {}).get("ad", {})

    properties = ad_data.get("properties", [])
    prop_map = {}
    for prop in properties:
        key = prop.get("key", "")
        value = prop.get("value", "")
        label = prop.get("label", "")
        prop_map[key] = value

    return {
        "description": ad_data.get("description", ""),
        "bedrooms": prop_map.get("bedrooms", ""),
        "bathrooms": prop_map.get("bathrooms", ""),
        "land_size": prop_map.get("land_size", ""),
        "house_size": prop_map.get("house_size", ""),
        "address": prop_map.get("address") or (
            ad_data["location"]["name"] if isinstance(ad_data.get("location"), dict)
            else ad_data.get("location", "")
        ),
        "posted_date": (datetime.now() - timedelta(days=int(ad_data["postedDate"]))).strftime("%Y-%m-%d")
        if isinstance(ad_data.get("postedDate"), (int, float)) else ad_data.get("postedDate", ""),
    }


def _parse_price(price_str):
    """Convert a price string like 'Rs 42,000,000' to an integer."""
    if not price_str:
        return None
    digits = re.sub(r"[^\d]", "", str(price_str))
    return int(digits) if digits else None


def _parse_age_days(timestamp_str):
    """
    Parse ikman's relative timestamp (e.g. '6 days', '2 hours', '1 month')
    into approximate number of days. Returns None if unparseable.
    """
    if not timestamp_str:
        return None

    ts = timestamp_str.strip().lower()

    if ts in ("just now", "now"):
        return 0

    match = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?", ts)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    multipliers = {
        "second": 0,
        "minute": 0,
        "hour": 0,
        "day": 1,
        "week": 7,
        "month": 30,
        "year": 365,
    }
    return value * multipliers.get(unit, 0)


def extract_location_name(url):
    """Public wrapper for location name extraction."""
    return _extract_location_name(url)
