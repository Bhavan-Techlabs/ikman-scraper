import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

COLUMNS = [
    "Title",
    "Location",
    "Bedrooms",
    "Bathrooms",
    "Land Size (Perches)",
    "House Size (SqFt)",
    "Price (LKR)",
    "Address",
    "Description",
    "URL",
    "Posted",
    "Date Scraped",
    "Status",
    "Notes",
]

# Column index map (0-based) — used by excel_writer for per-column formatting
COL = {name: i for i, name in enumerate(COLUMNS)}


def normalize_int(val):
    """Return val as int, or None if not parseable."""
    if val is None or val == "":
        return None
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        m = re.search(r"\d+", str(val))
        return int(m.group()) if m else None


def normalize_land_size(val):
    """Return land size as float perches, or None."""
    if val is None or val == "":
        return None
    m = re.search(r"([\d.]+)", str(val))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def normalize_house_size(val):
    """Return house size as float sqft (strips 'SqFt', 'sqft', commas), or None."""
    if val is None or val == "":
        return None
    cleaned = re.sub(r"[,]", "", str(val))
    m = re.search(r"([\d.]+)", cleaned)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def normalize_price(price_numeric, price_raw):
    """Return price as integer LKR.

    Prefers price_numeric (already parsed by scraper). Falls back to parsing
    price_raw for M/Million/Billion/K suffixes.
    """
    if price_numeric is not None:
        try:
            return int(price_numeric)
        except (ValueError, TypeError):
            pass

    if not price_raw:
        return None

    text = str(price_raw).strip()

    # "45,000,000 LKR" or "Rs 220,000,000" — plain digits with commas
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:LKR)?$", text.replace(",", ""), re.IGNORECASE)

    # "36 Million", "1.5 Billion", "3M", "Rs. 3M"
    m2 = re.search(r"([\d.]+)\s*(million|billion|thousand|[mbk])\b", text, re.IGNORECASE)
    if m2:
        val = float(m2.group(1))
        suffix = m2.group(2).lower()
        mult = {"million": 1_000_000, "m": 1_000_000,
                "billion": 1_000_000_000, "b": 1_000_000_000,
                "thousand": 1_000, "k": 1_000}.get(suffix, 1)
        return int(val * mult)

    # Plain number with commas: "Rs. 3,000,000" or "Rs 220,000,000"
    m3 = re.search(r"[\d,]+", text)
    if m3:
        try:
            return int(m3.group().replace(",", ""))
        except ValueError:
            pass

    return None


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
    """Combine listing summary and ad detail into a typed flat dict matching COLUMNS."""
    return {
        "Title": listing.get("title", ""),
        "Location": location_name,
        "Bedrooms": normalize_int(details.get("bedrooms")),
        "Bathrooms": normalize_int(details.get("bathrooms")),
        "Land Size (Perches)": normalize_land_size(details.get("land_size")),
        "House Size (SqFt)": normalize_house_size(details.get("house_size")),
        "Price (LKR)": normalize_price(listing.get("price_numeric"), listing.get("price_raw", "")),
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
    """Convert a row dict to a list ordered by COLUMNS, preserving native types."""
    result = []
    for col in COLUMNS:
        val = row_dict.get(col)
        if val is None:
            result.append("")
        else:
            result.append(val)
    return result


# 1 perch = 25.2929 m² ≈ 272.25 sqft (Sri Lankan standard)
_PERCH_TO_SQFT = 272.25


def compute_value_score(price_lkr, land_perches, house_sqft, bedrooms, bathrooms):
    """Return a value score: higher = more space per rupee spent.

    Primary driver: total effective sqft / price.
    Secondary: room count adds a small bonus (10% weight).
    Returns None if price is missing or zero.
    """
    if not price_lkr:
        return None

    land_sqft = (land_perches or 0) * _PERCH_TO_SQFT
    space = land_sqft + (house_sqft or 0)

    if space == 0:
        return None

    room_bonus = ((bedrooms or 0) * 200 + (bathrooms or 0) * 100)
    adjusted = space + room_bonus * 0.1

    return round(adjusted / price_lkr * 1_000_000, 4)
