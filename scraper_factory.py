"""
Factory that dispatches scraping calls to the right scraper based on URL domain.
To add a new scraper, import it and add an entry to SCRAPERS mapping its domain to the module.
"""
from urllib.parse import urlparse

import scraper_ikman as ikman_scraper
import scraper_lankapropertyweb as lpw_scraper
import scraper_ceylonproperty as cp_scraper

# Maps a domain substring to its scraper module. Checked in order; ikman is the fallback.
SCRAPERS = {
    "ikman.lk": ikman_scraper,
    "lankapropertyweb.com": lpw_scraper,
    "ceylonproperty.lk": cp_scraper,
}


def _resolve(url):
    domain = urlparse(url).netloc.lower()
    for key, scraper in SCRAPERS.items():
        if key in domain:
            return scraper
    raise ValueError(f"No scraper registered for domain: {domain}")


def get_listings(url, config):
    return _resolve(url).get_listings(url, config)


def get_ad_details(ad_url, request_delay=1.5):
    return _resolve(ad_url).get_ad_details(ad_url, request_delay=request_delay)


def extract_location_name(url):
    return _resolve(url).extract_location_name(url)
