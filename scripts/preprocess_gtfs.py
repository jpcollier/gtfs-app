#!/usr/bin/env python3
"""Convert static GTFS feeds into compact JSON for scheduled-service animation.

The script intentionally uses only the Python standard library so the initial
project is easy to run. It reads a configurable list of GTFS zip files/URLs,
chooses one valid weekday service date, samples trips, and emits per-agency
route geometry plus timestamped trip stop positions that the browser can
interpolate between.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]


def parse_time(value: str) -> Optional[int]:
    """Parse GTFS HH:MM:SS, allowing hours beyond 24 for after-midnight trips."""
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, s = (int(p) for p in parts)
        return h * 3600 + m * 60 + s
    except ValueError:
        return None


def read_gtfs_csv(zf: zipfile.ZipFile, name: str) -> List[dict]:
    try:
        with zf.open(name) as raw:
            text = (line.decode("utf-8-sig") for line in raw)
            return list(csv.DictReader(text))
    except KeyError:
        return []


def yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def choose_weekday_service(calendar_rows: List[dict], exception_rows: List[dict]) -> str:
    """Pick a weekday with broad scheduled service, accounting for exceptions.

    Preference is given to the Monday with the most active services in the
    calendar range. If calendar.txt is missing, fall back to the weekday with the
    most service_id additions in calendar_dates.txt.
    """
    if calendar_rows:
        starts = [parse_date(r["start_date"]) for r in calendar_rows if r.get("start_date")]
        ends = [parse_date(r["end_date"]) for r in calendar_rows if r.get("end_date")]
        start, end = min(starts), max(ends)
        exceptions = {(r.get("service_id"), r.get("date")): r.get("exception_type") for r in exception_rows}
        best = None
        d = start
        while d <= end:
            if d.weekday() < 5:
                key = ["monday", "tuesday", "wednesday", "thursday", "friday"][d.weekday()]
                ds = yyyymmdd(d)
                active = 0
                for row in calendar_rows:
                    sid = row.get("service_id")
                    in_range = row.get("start_date", "99999999") <= ds <= row.get("end_date", "00000000")
                    runs = in_range and row.get(key) == "1"
                    exc = exceptions.get((sid, ds))
                    if exc == "1":
                        runs = True
                    elif exc == "2":
                        runs = False
                    active += int(runs)
                if not best or active > best[0]:
                    best = (active, ds)
            d += timedelta(days=1)
        if best:
            return best[1]
    counts = defaultdict(int)
    for row in exception_rows:
        if row.get("exception_type") == "1" and row.get("date"):
            try:
                if parse_date(row["date"]).weekday() < 5:
                    counts[row["date"]] += 1
            except ValueError:
                pass
    if counts:
        return max(counts.items(), key=lambda kv: kv[1])[0]
    return yyyymmdd(date.today())


def active_services(calendar_rows: List[dict], exception_rows: List[dict], service_date: str) -> set:
    d = parse_date(service_date)
    weekday = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][d.weekday()]
    active = set()
    for row in calendar_rows:
        if row.get("start_date", "99999999") <= service_date <= row.get("end_date", "00000000") and row.get(weekday) == "1":
            active.add(row.get("service_id"))
    for row in exception_rows:
        if row.get("date") == service_date:
            if row.get("exception_type") == "1":
                active.add(row.get("service_id"))
            elif row.get("exception_type") == "2":
                active.discard(row.get("service_id"))
    return active


def download_if_needed(agency: dict, cache_dir: Path) -> Path:
    if agency.get("local_zip"):
        return (ROOT / agency["local_zip"]).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{agency['id']}.zip"
    if not target.exists():
        print(f"Downloading {agency['name']} -> {target}")
        urllib.request.urlretrieve(agency["feed_url"], target)
    return target


def point_at_fraction(points: List[Tuple[float, float]], fraction: float) -> Tuple[float, float]:
    if not points:
        return (0, 0)
    if len(points) == 1:
        return points[0]
    fraction = max(0.0, min(1.0, fraction))
    seg_lengths = []
    total = 0.0
    for a, b in zip(points, points[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        seg_lengths.append(length)
        total += length
    if total == 0:
        return points[0]
    target = total * fraction
    acc = 0.0
    for i, length in enumerate(seg_lengths):
        if acc + length >= target:
            t = (target - acc) / length if length else 0
            ax, ay = points[i]
            bx, by = points[i + 1]
            return (ax + (bx - ax) * t, ay + (by - ay) * t)
        acc += length
    return points[-1]


def process_agency(agency: dict, zip_path: Path, output_dir: Path, trip_limit: int) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        routes = {r["route_id"]: r for r in read_gtfs_csv(zf, "routes.txt")}
        trips = read_gtfs_csv(zf, "trips.txt")
        stops = {s["stop_id"]: (float(s["stop_lon"]), float(s["stop_lat"])) for s in read_gtfs_csv(zf, "stops.txt") if s.get("stop_lon") and s.get("stop_lat")}
        calendar = read_gtfs_csv(zf, "calendar.txt")
        calendar_dates = read_gtfs_csv(zf, "calendar_dates.txt")
        service_date = agency.get("service_date") or choose_weekday_service(calendar, calendar_dates)
        services = active_services(calendar, calendar_dates, service_date) if calendar or calendar_dates else {t.get("service_id") for t in trips}
        selected_trips = [t for t in trips if t.get("service_id") in services and t.get("shape_id")][:trip_limit]
        selected_trip_ids = {t["trip_id"] for t in selected_trips}
        trip_to_route = {t["trip_id"]: t.get("route_id") for t in selected_trips}
        trip_to_shape = {t["trip_id"]: t.get("shape_id") for t in selected_trips}
        shape_ids = set(trip_to_shape.values())

        shapes_by_id = defaultdict(list)
        for row in read_gtfs_csv(zf, "shapes.txt"):
            if row.get("shape_id") in shape_ids:
                shapes_by_id[row["shape_id"]].append(row)
        shapes = {}
        for sid, rows in shapes_by_id.items():
            rows.sort(key=lambda r: int(float(r.get("shape_pt_sequence") or 0)))
            shapes[sid] = [(float(r["shape_pt_lon"]), float(r["shape_pt_lat"])) for r in rows if r.get("shape_pt_lon") and r.get("shape_pt_lat")]

        stop_times = defaultdict(list)
        for row in read_gtfs_csv(zf, "stop_times.txt"):
            if row.get("trip_id") in selected_trip_ids:
                t = parse_time(row.get("departure_time") or row.get("arrival_time") or "")
                if t is not None and row.get("stop_id") in stops:
                    stop_times[row["trip_id"]].append((int(row.get("stop_sequence") or 0), t, stops[row["stop_id"]]))

    anim_trips = []
    route_shape_ids = set()
    for trip_id, rows in stop_times.items():
        rows.sort(key=lambda x: x[0])
        if len(rows) < 2:
            continue
        shape_id = trip_to_shape[trip_id]
        shape = shapes.get(shape_id, [])
        route_shape_ids.add(shape_id)
        # Fractions are approximated by stop order. This is robust across feeds
        # without requiring shape_dist_traveled, and can later be upgraded.
        samples = []
        denom = max(1, len(rows) - 1)
        for idx, (_, seconds, fallback_xy) in enumerate(rows):
            lon, lat = point_at_fraction(shape, idx / denom) if shape else fallback_xy
            samples.append([seconds, round(lon, 6), round(lat, 6)])
        anim_trips.append({"id": trip_id, "route_id": trip_to_route[trip_id], "shape_id": shape_id, "samples": samples})

    visible_shapes = [{"id": sid, "points": [[round(x, 6), round(y, 6)] for x, y in shapes.get(sid, [])]} for sid in sorted(route_shape_ids) if shapes.get(sid)]
    all_points = [pt for s in visible_shapes for pt in s["points"]] or [sample[1:] for t in anim_trips for sample in t["samples"]]
    bounds = {
        "min_lon": min(p[0] for p in all_points), "min_lat": min(p[1] for p in all_points),
        "max_lon": max(p[0] for p in all_points), "max_lat": max(p[1] for p in all_points),
    }
    payload = {"id": agency["id"], "name": agency["name"], "city": agency["city"], "service_date": service_date,
               "bounds": bounds, "routes": [{"id": rid, "short_name": r.get("route_short_name", "")} for rid, r in routes.items()],
               "shapes": visible_shapes, "trips": anim_trips}
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{agency['id']}.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    return {"id": agency["id"], "name": agency["name"], "city": agency["city"], "file": f"data/{agency['id']}.json", "service_date": service_date}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/agencies.json")
    parser.add_argument("--output", default="public/data")
    parser.add_argument("--cache", default="data/feeds")
    parser.add_argument("--limit", type=int, default=None, help="Override trips sampled per agency")
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text())
    manifest = []
    for agency in cfg["agencies"]:
        zip_path = download_if_needed(agency, ROOT / args.cache)
        manifest.append(process_agency(agency, zip_path, ROOT / args.output, args.limit or cfg.get("sample_limit_trips_per_agency", 1200)))
    (ROOT / args.output / "manifest.json").write_text(json.dumps({"agencies": manifest}, indent=2))
    print(f"Wrote {len(manifest)} agencies to {args.output}")


if __name__ == "__main__":
    main()
