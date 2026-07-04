import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

COLUMNS = [
    "Title",
    "Location",
    "Bedrooms",
    "Bathrooms",
    "Land Size",
    "House Size",
    "Price",
    "Address",
    "Description",
    "URL",
    "Posted",
    "Date Scraped",
    "Status",
    "Notes",
]



def normalize_land_size(land_size_str):
    """Extract numeric perches value from strings like '10.5 perches'."""
    if not land_size_str:
        return ""
    match = re.search(r"([\d.]+)", str(land_size_str))
    return match.group(1) if match else land_size_str


def _estimate_posted_date(time_stamp):
    """Convert a relative timestamp like '6 days' into an approximate date string."""
    if not time_stamp:
        return ""

    ts = time_stamp.strip().lower()
    now = datetime.now()

    if ts in ("just now", "now"):
        return now.strftime("%Y-%m-%d")

    match = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?", ts)
    if not match:
        return time_stamp

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
    posted = now - deltas.get(unit, timedelta())
    return posted.strftime("%Y-%m-%d")


def build_row(listing, details, location_name):
    """
    Combine listing summary and ad detail data into a single flat dict
    matching the COLUMNS schema.
    """
    return {
        "Title": listing.get("title", ""),
        "Location": location_name,
        "Bedrooms": details.get("bedrooms", ""),
        "Bathrooms": details.get("bathrooms", ""),
        "Land Size": normalize_land_size(details.get("land_size", "")),
        "House Size": details.get("house_size", ""),
        "Price": listing.get("price_raw", ""),
        "Address": details.get("address", ""),
        "Description": details.get("description", ""),
        "URL": listing.get("ad_url", ""),
        "Posted": (
            _estimate_posted_date(listing.get("time_stamp", ""))
            or details.get("posted_date", "")
        ),
        "Date Scraped": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Status": "",
        "Notes": "",
    }


def row_to_list(row_dict):
    """Convert a row dict to a list ordered by COLUMNS."""
    return [str(row_dict.get(col, "")) for col in COLUMNS]
