"""Generate SAMPLE temperature data for Heilbronn (Day 1 placeholder).

The values are invented. They follow the shared team format so the real,
cleaned data can replace this file without code changes:

    latitude, longitude, temperature_c, timestamp, source

Run:  python scripts/make_sample_data.py
"""

import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)

OUT = Path(__file__).resolve().parent.parent / "data" / "sample_temperature.csv"

# Rough reference points in Heilbronn. Positive offset = warmer than average.
SPOTS = [
    # (lat, lon, offset_c)
    (49.1427, 9.2185, +3.0),   # Marktplatz / old town (sealed surfaces)
    (49.1405, 9.2105, +2.2),   # Hauptbahnhof area
    (49.1460, 9.2230, +1.8),   # Allee / city ring
    (49.1520, 9.2050, +1.5),   # industrial area north
    (49.1365, 9.2205, -1.5),   # Neckar riverbank
    (49.1440, 9.2290, -2.5),   # Stadtgarten (park)
    (49.1300, 9.2350, -3.0),   # Wartberg / green edge
]


def base_temperature(ts: datetime) -> float:
    """Simple daily cycle: coolest ~05:00, warmest ~15:00."""
    hour = ts.hour + ts.minute / 60
    return 24 + 7 * math.sin((hour - 9) / 24 * 2 * math.pi)


def local_offset(lat: float, lon: float) -> float:
    """Blend the hotspot offsets by distance (inverse distance weighting)."""
    num = den = 0.0
    for s_lat, s_lon, off in SPOTS:
        d = math.hypot(lat - s_lat, (lon - s_lon) * 0.65) + 1e-4
        w = 1 / d**2
        num += w * off
        den += w
    return num / den


rows = []
start = datetime(2025, 7, 15, 6, 0)

# 1) Fixed home stations ("senseBox:home"-like), every 30 minutes for 2 days
stations = [(lat + random.uniform(-0.002, 0.002), lon + random.uniform(-0.002, 0.002))
            for lat, lon, _ in SPOTS]
for lat, lon in stations:
    t = start
    while t < start + timedelta(days=2):
        temp = base_temperature(t) + local_offset(lat, lon) + random.gauss(0, 0.4)
        rows.append((lat, lon, temp, t, "sample_home"))
        t += timedelta(minutes=30)

# 2) Bike rides ("senseBox:bike"-like): random walks through the city
for ride in range(12):
    t = start + timedelta(hours=random.uniform(0, 44))
    lat, lon = random.choice(SPOTS)[:2]
    for _ in range(80):
        lat += random.gauss(0, 0.0008)
        lon += random.gauss(0, 0.0012)
        lat = min(max(lat, 49.120), 49.165)
        lon = min(max(lon, 9.185), 9.255)
        temp = base_temperature(t) + local_offset(lat, lon) + random.gauss(0, 0.6)
        rows.append((lat, lon, temp, t, "sample_bike"))
        t += timedelta(seconds=20)

df = pd.DataFrame(rows, columns=["latitude", "longitude", "temperature_c", "timestamp", "source"])
df["latitude"] = df["latitude"].round(6)
df["longitude"] = df["longitude"].round(6)
df["temperature_c"] = df["temperature_c"].round(1)
df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%dT%H:%M:%S")
df = df.sort_values("timestamp").reset_index(drop=True)

OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False)
print(f"Wrote {len(df)} rows to {OUT}")
