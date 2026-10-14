# Data Automation Toolkit

Python scripts for web data collection, public catalog audits, accessibility checks and report generation. Built and run from an Android phone with Termux.

I write these scripts with AI coding assistants and test every result myself before using it.

## Scripts

| Folder | Script | What it does |
|---|---|---|
| `secop/` | `secop_scraper.py` | Pulls upcoming public procurement processes from Colombia's SECOP II open data API, ranks them by urgency and resolves a contact number per company. |
| `secop/` | `secop_proponentes.py`, `resolver_proponentes.py` | Fetches the companies that bid on each process and resolves their contact details. |
| `catalog_audit/` | `catalog_scraper.py` | Finds Shopify and WooCommerce stores by niche and flags real catalog errors from their public product data, ignoring blocks and false positives. |
| `catalog_audit/` | `recheck_leads.py`, `recheck_pending.py`, `recheck_woocommerce.py` | Re-verify stores against their live catalog so stale results are never used. |
| `catalog_audit/` | `verify_store.py` | Opens the flagged product pages like a customer would and confirms each error. |
| `catalog_audit/` | `catalog_analysis.py`, `deliverables.py` | Compute catalog metrics and compare each store against its niche; generate Excel files and a PDF sector report. |
| `wcag_audit/` | `wcag_audit.py` | Runs Google PageSpeed accessibility audits on stores and maps failures to WCAG criteria with fix guidance. |
| `agency_finder/` | `agency_finder.py` | Finds marketing agencies by type and city and extracts their public contact details. |
| `reddit/` | `reddit_leads.py` | Collects CV-help posts across subreddits through the official Reddit API (OAuth app credentials), validates them with an LLM and exports CSV and HTML. |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add your own keys
python catalog_audit/catalog_scraper.py
```

Keys are read from environment variables or a local `.env` file. Without them the scripts use the `YOUR_..._KEY` placeholders. Never commit your `.env`.

Output column names and some messages are in Spanish because the data targets the Colombian market. Sales message text is left as `[SALES MESSAGE PLACEHOLDER]`. Store lists in the examples are replaced by `example.com`.
