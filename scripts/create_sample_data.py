#!/usr/bin/env python3
"""Create tiny synthetic processed data so the app runs before GTFS downloads."""
import json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "data"
OUT.mkdir(parents=True, exist_ok=True)
CITIES = [
    ("nyc_sample", "MTA New York City Transit", "New York"),
    ("cta_sample", "Chicago Transit Authority", "Chicago"),
    ("la_sample", "LA Metro", "Los Angeles"),
    ("mbta_sample", "MBTA", "Boston"),
]
manifest = []
for ci, (aid, name, city) in enumerate(CITIES):
    shapes, trips = [], []
    for s in range(10):
        points = []
        for i in range(34):
            angle = (i / 33) * math.tau + s * 0.35
            radius = 0.08 + s * 0.012
            lon = -0.12 + math.cos(angle) * radius + ci * 0.01
            lat = math.sin(angle * (1 + s % 3 * 0.12)) * radius * 0.72
            points.append([round(lon, 6), round(lat, 6)])
        sid = f"shape_{s}"
        shapes.append({"id": sid, "points": points})
        for t in range(18):
            start = 5 * 3600 + s * 900 + t * 1800
            samples = []
            for idx, p in enumerate(points[::4]):
                samples.append([start + idx * 420, p[0], p[1]])
            trips.append({"id": f"trip_{s}_{t}", "route_id": f"R{s}", "shape_id": sid, "samples": samples})
    payload = {
        "id": aid, "name": name, "city": city, "service_date": "2026-06-24",
        "bounds": {"min_lon": -0.24, "min_lat": -0.18, "max_lon": 0.24, "max_lat": 0.18},
        "routes": [{"id": f"R{s}", "short_name": str(s)} for s in range(10)],
        "shapes": shapes, "trips": trips,
    }
    (OUT / f"{aid}.json").write_text(json.dumps(payload, separators=(",", ":")))
    manifest.append({"id": aid, "name": name, "city": city, "file": f"data/{aid}.json", "service_date": "2026-06-24"})
(OUT / "manifest.json").write_text(json.dumps({"agencies": manifest}, indent=2))
print(f"Wrote sample data for {len(manifest)} agencies to {OUT}")
