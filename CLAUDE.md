# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Sri Lankan House Sales Scraper is a Python web scraper that extracts house-for-sale listings from multiple Sri Lankan property sites (ikman.lk, lankapropertyweb.com) and writes structured property data to Excel (.xlsx) and/or Google Sheets. It runs every 12 hours via GitHub Actions, which uploads the Excel file as a downloadable artifact.

## Setup

```bash
pip install -r requirements.txt
# config.yaml is committed and used directly — edit output_mode and URLs as needed
```

Only one file must be present locally and is gitignored:
- `credentials.json` — Google service account key for Sheets API (only needed when output_mode includes "sheets")

## Running

```bash
# Incremental run — appends new listings, preserves existing data
python main.py

# Clear all sheets then scrape fresh
python main.py --clean

# Use a custom config file
python main.py --config path/to/config.yaml
```

## Architecture

The scraper is a linear pipeline over location URLs defined in config:

```
Config → output backend(s) init → per-location loop:
  factory dispatch → fetch listing pages → filter by price/age
  → fetch ad detail pages → deduplicate → build rows
  → append to Excel sheet tab and/or Google Sheets tab → sort & format
```

**Modules:**

- `main.py` — CLI entry point; `process_location(url, config, excel_mod, spreadsheet)` drives the per-location loop
- `scraper_factory.py` — factory that dispatches `get_listings`, `get_ad_details`, `extract_location_name` to the right scraper based on URL domain
- `scraper.py` — ikman.lk scraper; HTTP fetching; extracts embedded `window.initialData` JSON; handles pagination and promoted-ad filtering
- `scraper_lankapropertyweb.py` — lankapropertyweb.com scraper; parses HTML with BeautifulSoup; handles pagination via URL query params
- `data_processor.py` — normalizes scraped data into 14-column rows; `COLUMNS` defines the schema; converts relative timestamps to ISO dates
- `duplicate_detector.py` — `DuplicateDetector` class checks exact URL match first, then falls back to `difflib.SequenceMatcher` description similarity (threshold configurable, default 0.9)
- `excel_writer.py` — writes/appends rows to `output/srilanka_house_sales_YYYY-MM-DD.xlsx`; one sheet tab per location; auto-column widths
- `sheets.py` — Google Sheets API via service account; auto-creates tabs per location; auto-sorts by Posted date; auto-formats headers and row height

## Key Behaviors to Know

**Output mode**: Controlled by `output_mode` in `config.yaml`:
- `"excel"` — writes to `output/srilanka_house_sales_YYYY-MM-DD.xlsx` (default)
- `"sheets"` — writes to Google Sheets (requires `credentials.json` and `spreadsheet_id`)
- `"both"` — writes to both

**Multi-site factory**: `scraper_factory.py` inspects the URL domain and routes to `scraper.py` (ikman.lk), `scraper_lankapropertyweb.py` (lankapropertyweb.com), or `scraper_ceylonproperty.py` (ceylonproperty.lk). To add a new site, create a new `scraper_SITENAME.py` and add a domain check in the factory.

**Pagination cutoff (ikman)**: Stops paginating when a page has no organic (non-promoted) ads newer than `max_age_days`.

**Price filtering**: Applied at config level (`price_filter.min`/`price_filter.max`) unless the URL already contains price query parameters.

**Duplicate detection**: Catches both exact URL matches and description similarity matches (cross-batch against existing data and intra-batch).

**Sheet layout**: Each location gets its own worksheet tab named after the location. Status and Notes columns are user-editable and preserved across incremental runs.

## GitHub Actions

`.github/workflows/scrape.yml` runs on a 12-hour cron (`0 */12 * * *`) and on manual dispatch. It:
1. Writes `credentials.json` from `GOOGLE_CREDENTIALS` secret (skipped if secret not set)
2. Runs the scraper
3. **Uploads `output/*.xlsx` as a downloadable artifact** named `srilanka-house-sales` (retained 30 days)
4. Cleans up `credentials.json`

The job timeout is 180 minutes.

## Configuration Reference (`config.yaml`)

- `output_mode` — `"excel"` | `"sheets"` | `"both"` (default: `"excel"`)
- `spreadsheet_id` — Google Sheets document ID (only needed for Sheets output)
- `credentials_path` — path to service account JSON (default: `credentials.json`)
- `urls` — list of property search URLs (ikman.lk or lankapropertyweb.com)
- `price_filter.min` / `price_filter.max` — price filter in LKR
- `max_age_days` — skip ads older than this (ikman.lk only)
- `max_pages` — pagination limit per location
- `similarity_threshold` — duplicate detection sensitivity (0–1, default 0.9)
- `request_delay` — seconds between HTTP requests
