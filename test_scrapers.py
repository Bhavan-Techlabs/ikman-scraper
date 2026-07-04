#!/usr/bin/env python3
"""
Smoke test: fetch one listing from each site, get its details,
build a row, and write it to output/test_output.xlsx.
Run with: venv/bin/python3 test_scrapers.py
"""
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_scrapers")

import yaml
import excel_writer
import scraper_factory as factory
from data_processor import build_row, row_to_list

# One representative URL per site
TEST_URLS = {
    "ikman": "https://ikman.lk/en/ads/piliyandala/houses-for-sale",
    "lankapropertyweb": (
        "https://www.lankapropertyweb.com/sale/index.php"
        "?search=1&location=Western_Piliyandala&property-type=House"
        "&from_index=1&min=Any&max=30000000&price-option=price_total&searchbox=Piliyandala"
    ),
    "ceylonproperty": "https://ceylonproperty.lk/sale/property/in-piliyandala?toAmount=30000000",
}

# Minimal config — price filter off so we don't accidentally drop everything
CONFIG = {
    "price_filter": {"min": None, "max": None},
    "max_age_days": 9999,
    "max_pages": 1,
    "request_delay": 1.5,
    "similarity_threshold": 0.9,
}

# Write to a test-specific file so we don't pollute the real output
_ORIG_OUTPUT_PATH = excel_writer._output_path


def _test_output_path():
    os.makedirs("output", exist_ok=True)
    return os.path.join("output", "test_output.xlsx")


excel_writer._output_path = _test_output_path

# Clean previous test file
if os.path.exists(_test_output_path()):
    os.remove(_test_output_path())

results = {}

for site, url in TEST_URLS.items():
    logger.info("=" * 60)
    logger.info("Testing %s", site)
    location_name = factory.extract_location_name(url)
    logger.info("Location name: %s", location_name)

    try:
        listings = factory.get_listings(url, CONFIG)
    except Exception as e:
        logger.error("get_listings failed: %s", e)
        results[site] = {"status": "FAIL", "error": f"get_listings: {e}"}
        continue

    if not listings:
        logger.error("No listings returned")
        results[site] = {"status": "FAIL", "error": "0 listings returned"}
        continue

    logger.info("Got %d listings, fetching details for first one: %s", len(listings), listings[0].get("ad_url", ""))

    try:
        details = factory.get_ad_details(listings[0]["ad_url"], request_delay=1.5)
    except Exception as e:
        logger.error("get_ad_details failed: %s", e)
        results[site] = {"status": "FAIL", "error": f"get_ad_details: {e}"}
        continue

    row = build_row(listings[0], details, location_name)
    excel_writer.append_rows(location_name, [row_to_list(row)])

    logger.info("Row written. Key fields:")
    logger.info("  Title:    %s", row["Title"])
    logger.info("  Location: %s", row["Location"])
    logger.info("  Price:    %s", row["Price (LKR)"])
    logger.info("  Posted:   %s", row["Posted"])
    logger.info("  Bedrooms: %s", row["Bedrooms"])
    logger.info("  Land:     %s P  House: %s sqft", row["Land Size (Perches)"], row["House Size (SqFt)"])
    logger.info("  URL:      %s", row["URL"])

    results[site] = {"status": "OK", "location_name": location_name, "title": row["Title"], "posted": row["Posted"], "price": row["Price (LKR)"]}

logger.info("=" * 60)
logger.info("RESULTS SUMMARY")
all_passed = True
for site, r in results.items():
    status = r["status"]
    if status == "OK":
        logger.info("  %-20s OK  — location=%s  posted=%s  price=%s", site, r["location_name"], r["posted"], r.get("price"))
    else:
        logger.error("  %-20s FAIL — %s", site, r["error"])
        all_passed = False

if all_passed:
    logger.info("All sites passed. Excel written to: %s", _test_output_path())
else:
    logger.error("One or more sites failed.")
    sys.exit(1)
