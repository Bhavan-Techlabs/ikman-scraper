# ikman.lk Property Scraper

A Python web scraper that extracts house-for-sale listings from [ikman.lk](https://ikman.lk/), Sri Lanka's largest marketplace, and writes structured data to Google Sheets. Supports multiple locations, price filtering, pagination, and intelligent duplicate detection.

## Features

- **Multi-location scraping** -- configure multiple ikman.lk URLs, each gets its own sheet tab (e.g., Maharagama, Boralesgamuwa)
- **Full ad details** -- visits each individual ad page to extract description, bedrooms, bathrooms, land size, house size, address, and more
- **Price filtering** -- filter ads by min/max price range, configurable globally or via URL parameters
- **Age cutoff** -- only scrape ads posted within the last N days (default: 14)
- **Smart pagination** -- handles promoted/featured/bumped ads correctly without stopping pagination early
- **Duplicate detection** -- skips ads already in the sheet by URL match or 90%+ description text similarity (catches reposted ads with new URLs)
- **Google Sheets output** -- auto-creates sheet tabs, formats headers, sorts by posted date, and keeps rows compact
- **Clean mode** -- option to clear all sheets and start fresh
- **GitHub Actions support** -- automate scraping on a schedule (e.g., every hour) with zero infrastructure

## How It Works

ikman.lk embeds structured JSON data in each page via `window.initialData`. The scraper extracts this JSON directly instead of parsing HTML, making it fast and reliable.

```
Listing Pages → JSON extraction → Price/age filtering
    ↓
Individual Ad Pages → Detailed property data
    ↓
Duplicate Detection → URL match + description similarity (difflib)
    ↓
Google Sheets → One tab per location, sorted by date
```

## Data Columns

| Column | Description |
|---|---|
| Title | Ad title |
| Location | Location name |
| Bedrooms | Number of bedrooms |
| Bathrooms | Number of bathrooms |
| Land Size | Land size in perches |
| House Size | House size in sqft |
| Price | Display price (e.g., Rs 35,000,000) |
| Address | Property address |
| Description | Full ad description (clipped in sheet, visible on click) |
| URL | Link to the ad on ikman.lk |
| Posted | Approximate date the ad was posted |
| Date Scraped | When the scraper collected this data |
| Status | For your own tracking |
| Notes | For your own notes |

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/randikabanura/ikman-scraper.git
cd ikman-scraper
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up Google Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **Google Sheets API** and **Google Drive API**
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > Service account**
6. Give it a name, click through the steps
7. On the service account page, go to the **Keys** tab
8. Click **Add Key > Create new key > JSON** -- this downloads the credentials file
9. Save it as `credentials.json` in the project root

### 4. Create and share a Google Sheet

1. Create a new Google Sheet
2. Click **Share** and add the service account email (found in your `credentials.json` as `client_email`, looks like `name@project.iam.gserviceaccount.com`) as an **Editor**
3. Copy the spreadsheet ID from the URL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`

### 5. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your spreadsheet ID, desired URLs, and price range.

## Usage

### Standard run (incremental)

```bash
python main.py
```

Scrapes new ads and appends them to the sheet. Existing data is preserved; duplicates are skipped.

### Clean run (fresh start)

```bash
python main.py --clean
```

Clears all sheet data before scraping.

### Custom config file

```bash
python main.py --config my_config.yaml
```

## Automated Scraping with GitHub Actions

This project includes a GitHub Actions workflow that can run the scraper automatically on a schedule -- no server required.

### How it works

The included `.github/workflows/scrape.yml` workflow runs the scraper every hour using a cron schedule. It can also be triggered manually from the **Actions** tab in your GitHub repository.

### Setup

1. Fork or push this repository to GitHub (public repos get unlimited free Actions minutes)
2. Add two **repository secrets** under **Settings > Secrets and variables > Actions**:
   - `GOOGLE_CREDENTIALS` -- the full contents of your `credentials.json` file
   - `CONFIG_YAML` -- the full contents of your `config.yaml` file
3. That's it -- the workflow will run automatically every hour

You can also set the secrets via the CLI:

```bash
gh secret set GOOGLE_CREDENTIALS < credentials.json
gh secret set CONFIG_YAML < config.yaml
```

### Manual trigger

```bash
gh workflow run scrape.yml
```

Or click **Run workflow** from the Actions tab on GitHub.

### Adjusting the schedule

Edit the cron expression in `.github/workflows/scrape.yml`:

```yaml
on:
  schedule:
    - cron: '0 * * * *'    # Every hour
    # - cron: '0 */6 * * *'  # Every 6 hours
    # - cron: '0 8 * * *'    # Daily at 8am UTC
```

## Configuration

See `config.example.yaml` for all options:

```yaml
spreadsheet_id: "YOUR_SPREADSHEET_ID"
credentials_path: "credentials.json"

urls:
  - "https://ikman.lk/en/ads/maharagama/houses-for-sale"
  - "https://ikman.lk/en/ads/boralesgamuwa/houses-for-sale"

price_filter:
  min: 15000000
  max: 80000000

similarity_threshold: 0.9
request_delay: 1.5
max_age_days: 14
max_pages: 20
```

You can also add price filters directly to URLs:

```yaml
urls:
  - "https://ikman.lk/en/ads/maharagama/houses-for-sale?money.price.minimum=20000000&money.price.maximum=50000000"
```

## Project Structure

```
├── .github/workflows/
│   └── scrape.yml          # GitHub Actions workflow (hourly cron)
├── main.py                 # CLI entry point
├── scraper.py              # Page fetching, JSON extraction, pagination
├── data_processor.py       # Data normalization and row building
├── duplicate_detector.py   # URL + description similarity matching
├── sheets.py               # Google Sheets read/write/format
├── config.example.yaml     # Sample configuration
├── requirements.txt        # Python dependencies
└── README.md
```

## Disclaimer

This project is for educational and personal use only. Please respect ikman.lk's terms of service and use reasonable request delays.

## License

MIT
