# System Maintenance: Market Metadata Refresh & Data Hygiene

TWS Robot includes a metadata-only System Maintenance workflow for keeping index universes and market-event context fresh without touching trading execution paths.

## What it maintains

- S&P 500, STI, and HSI constituent CSV files
- Market events through the existing market-events service
- Validation reports and backups

## Safety boundaries

The maintenance workflow must not place orders, change strategy behavior, start/stop strategies, modify autonomous trading configuration, or bypass emergency-stop controls.

Allowed writes are limited to:

- `data/*_constituents.csv`
- `data/backups/constituents/...`
- `reports/maintenance/...`
- Existing market-event rows through `data.market_events`

## Web console

Open:

```text
/maintenance
```

Available actions:

- **Dry Run All** — fetches proposed metadata and writes reports without replacing files
- **Dry Run Constituents** — previews S&P 500/STI/HSI constituent changes
- **Apply Constituents Refresh** — backs up and replaces constituent files only after validation passes
- **Refresh Market Events** — calls the existing event service for portfolio/strategy symbols
- **Validate Metadata Only** — validates current local metadata files

## CLI

Dry-run is the safe default unless `--apply` is passed.

```bash
python -m web.maintenance run --dry-run
python -m web.maintenance run --task sp500_constituents --dry-run
python -m web.maintenance run --task hsi_constituents --apply
python -m web.maintenance run --task market_events --apply --symbol AAPL --symbol MSFT
python -m web.maintenance validate
```

Legacy wrappers remain available:

```bash
python scripts/refresh_sp500_constituents.py
python deployment_scripts/refresh_hsi_constituents.py
```

## Validation rules

Constituent refreshes are rejected before file replacement when:

- Required columns are missing
- Row count is below the configured market threshold
- Symbols are blank or duplicated
- Symbol format does not match market-specific rules
- Count change is greater than 25%, unless explicitly allowed

A warning is recorded when count change is greater than 10%.

Default minimum counts:

| Universe | Minimum rows |
| --- | ---: |
| S&P 500 | 450 |
| STI | 25 |
| HSI | 70 |

## Reports and backups

Each run writes both JSON and Markdown reports:

```text
reports/maintenance/maintenance_*.json
reports/maintenance/maintenance_*.md
```

Apply mode creates timestamped backups before replacing any existing constituent file:

```text
data/backups/constituents/YYYYMMDD_HHMMSS/<filename>.csv
```

## Recommended cadence

Run manually every 2–3 days, or daily if desired, preferably outside active market hours. Because this is metadata-only, it is designed not to interfere with paper/live trading paths, but off-peak operation is still cleaner.
