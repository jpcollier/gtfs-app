# GTFS Representative Day Small Multiples

A lightweight local web app for visualizing one representative day of scheduled transit service from static GTFS feeds. Each agency is rendered as a small multiple with no basemap: thin route shapes and animated vehicle-like dots interpolated from scheduled `stop_times.txt`.

## Proposed architecture

```text
config/agencies.json          # configurable top-agency list and GTFS feed URLs/local zip paths
scripts/preprocess_gtfs.py    # standard-library GTFS zip parser and animation JSON exporter
scripts/create_sample_data.py # tiny synthetic processed dataset for first-run demo
public/data/                  # browser-ready manifest and per-agency JSON files
src/main.jsx                  # React + D3 animation and small-multiple panels
src/styles.css                # minimal visual design
```

The browser never parses raw GTFS. The preprocessing step reads each feed, chooses a valid weekday service date, samples trips, keeps route shape geometry, and writes compact JSON optimized for animation.

## Data assumptions

- The initial configured agencies are a practical top-10 seed list of large U.S. operators by ridership/service prominence; edit `config/agencies.json` to change agencies or feeds.
- `calendar.txt` and `calendar_dates.txt` are used to select the weekday with the broadest service in the feed range.
- Vehicle positions are interpolated between timed stops. The first implementation approximates stop positions along the trip shape by stop order when `shape_dist_traveled` is not used; this keeps the parser simple and robust for mixed feeds.
- `--limit` or `sample_limit_trips_per_agency` keeps local processing manageable. Increase the limit as needed.

## Setup

```bash
npm install
```

## Run with included sample data

The repository includes generated synthetic processed JSON so the app works immediately without large downloads.

```bash
npm run dev
```

Open the Vite URL printed in the terminal.

## Process real GTFS feeds

Download/process all configured agencies:

```bash
python scripts/preprocess_gtfs.py --config config/agencies.json --output public/data --cache data/feeds
```

Process a smaller sample while iterating:

```bash
python scripts/preprocess_gtfs.py --limit 300
```

If a feed host rejects the default downloader or has certificate issues, the
preprocessor sends a browser-like user agent and also supports an SSL
verification bypass similar to `requests` `verify=False`:

```bash
python scripts/preprocess_gtfs.py --insecure
```

To use local GTFS zips instead of URLs, add `local_zip` to an agency entry in `config/agencies.json`, for example:

```json
{ "id": "mbta", "name": "MBTA", "city": "Boston", "local_zip": "data/feeds/mbta.zip" }
```

Then run `npm run dev` again.

## Build

```bash
npm run build
```

## Scaling notes

- Replace JSON with Parquet or tiled chunks if full feeds become too large for the browser.
- Add `shape_dist_traveled` support for more accurate shape interpolation where feeds provide it.
- Partition trips by time window to avoid loading a full day at once for very large networks.
