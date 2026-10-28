"""Temperature map for Cool Heilbronn – relative to the time of measurement.

Problem: the bike rides were recorded on different days and at different times
(early morning ~18 °C, afternoon ~35 °C). Mapping raw temperatures would show
*when* someone rode, not *where* it is hot.

Solution: every measurement is compared with its own ride.

    ΔT = measured temperature − expected temperature of that ride at that moment

* Ride  = continuous recording without a gap of more than 30 minutes.
* Short rides (≤ 30 min): expected temperature = the ride's average.
* Long rides (> 30 min): expected temperature = a straight-line trend over time,
  so the normal warming (morning) or cooling (evening) during the ride is removed.

ΔT > 0 → hotter than its surroundings at that moment (possible hotspot)
ΔT < 0 → cooler than its surroundings at that moment

Interface for the web team (unchanged):
    df = load_temperature_data()                 # both cleaned CSVs in data/
    df = filter_by_time(df, start, end)          # optional
    html = heatmap_html(df)                      # full HTML page of the map
    export_heatmap(df, "static/maps/heatmap.html")

Run directly to export the map:  python -m viz.heatmap
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import branca.colormap as cm
import folium
import numpy as np
import pandas as pd
from folium.plugins import HeatMap

ROOT = Path(__file__).resolve().parent.parent
def _pick(*names: str) -> Path:
    """First file that exists in data/ (so both the cleaned and original names work)."""
    for n in names:
        if (ROOT / "data" / n).exists():
            return ROOT / "data" / n
    return ROOT / "data" / names[0]


DEFAULT_CSVS = [
    _pick("alles_kid_temp_clean.csv", "alles_kid_temp.csv"),
    _pick("OSEM_Bike_Data_cleaned.csv"),
]
DEFAULT_EXPORT = ROOT / "static" / "maps" / "heatmap.html"

HEILBRONN_CENTER = (49.1427, 9.2109)
# Only measurements inside this box are used (the bike data also contains trips far away).
HEILBRONN_BOUNDS = {"lat": (49.08, 49.20), "lon": (9.13, 9.30)}

COLUMNS = ["timestamp", "latitude", "longitude", "temperature_c", "humidity"]

# Column names in the source files → names used here.
ALIASES = {
    "lat": "latitude",
    "lon": "longitude",
    "lng": "longitude",
    "long": "longitude",
    "longtitude": "longitude",
    "temperature": "temperature_c",
    "temp": "temperature_c",
    "temp_c": "temperature_c",
    "time": "timestamp",
    "datetime": "timestamp",
    "date": "timestamp",
    "createdat": "timestamp",
    "rel. humidity": "humidity",
    "rel_humidity": "humidity",
    "relative humidity": "humidity",
}

# Times in the files are UTC (openSenseMap standard). Shown in Heilbronn local time.
LOCAL_TZ = "Europe/Berlin"

RIDE_GAP = pd.Timedelta("30min")     # a longer gap starts a new ride
LONG_RIDE = pd.Timedelta("30min")    # longer rides get the time-trend correction
MIN_RIDE_POINTS = 1                  # keep every measurement

# Diverging colours: cooler than surroundings (blue) → hotter (red)
DELTA_COLORS = ["#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b"]

MAX_RAW_POINTS = 4000
GRID_DEG = 0.001          # ~110 m × 75 m grid cell
MIN_CELL_POINTS = 1       # every measurement appears on the map


# ───────────────────────────── loading ─────────────────────────────

def load_temperature_data(paths: str | Path | Iterable[str | Path] = DEFAULT_CSVS) -> pd.DataFrame:
    """Read one or more cleaned CSVs, keep Heilbronn only, and add ΔT per ride."""
    if isinstance(paths, (str, Path)):
        paths = [paths]

    frames = []
    for path in paths:
        df = _read_one(path)
        df = add_ride_ids(df)
        df = add_relative_temperature(df)
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    # Unique ride id across files
    df["ride"] = df["source"] + "#" + df["ride"].astype(str)
    return df.sort_values("timestamp").reset_index(drop=True)


def _read_one(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={c: ALIASES.get(c.strip().lower(), c.strip().lower()) for c in df.columns})

    missing = [c for c in ["timestamp", "latitude", "longitude", "temperature_c"] if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing column(s) {missing}.")
    if "humidity" not in df.columns:
        df["humidity"] = np.nan

    # Keep road-surface columns if the file has them (used by the DI map)
    extra = [c for c in df.columns if c.startswith("surface ")]
    df = df[COLUMNS + extra].copy()
    df["timestamp"] = _parse_timestamps(df["timestamp"])
    for col in ("latitude", "longitude", "temperature_c", "humidity"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["timestamp", "latitude", "longitude", "temperature_c"])
    lat0, lat1 = HEILBRONN_BOUNDS["lat"]
    lon0, lon1 = HEILBRONN_BOUNDS["lon"]
    df = df[df["latitude"].between(lat0, lat1) & df["longitude"].between(lon0, lon1)]
    df = df[df["temperature_c"].between(-40, 60)]
    df["source"] = Path(path).stem
    return df.sort_values("timestamp").reset_index(drop=True)


def _parse_timestamps(values: pd.Series) -> pd.Series:
    """Parse ISO timestamps (with or without 'Z') as UTC → Heilbronn local time."""
    ts = pd.to_datetime(values, format="ISO8601", errors="coerce", utc=True)
    return ts.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)


# ───────────────────────────── ΔT per ride ─────────────────────────────

def add_ride_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Split the recording into rides (gap > 30 min = new ride)."""
    df = df.sort_values("timestamp").copy()
    df["ride"] = (df["timestamp"].diff() > RIDE_GAP).cumsum()
    return df


def add_relative_temperature(df: pd.DataFrame) -> pd.DataFrame:
    """Add expected_c (ride baseline) and delta_t (measured − expected)."""
    parts = []
    for _, ride in df.groupby("ride"):
        if len(ride) < MIN_RIDE_POINTS:
            continue
        ride = ride.copy()
        duration = ride["timestamp"].max() - ride["timestamp"].min()
        if duration > LONG_RIDE:
            minutes = (ride["timestamp"] - ride["timestamp"].min()).dt.total_seconds() / 60
            slope, intercept = np.polyfit(minutes, ride["temperature_c"], 1)
            ride["expected_c"] = intercept + slope * minutes
        else:
            ride["expected_c"] = ride["temperature_c"].mean()
        ride["delta_t"] = ride["temperature_c"] - ride["expected_c"]
        parts.append(ride)
    if not parts:
        return df.iloc[0:0].assign(expected_c=[], delta_t=[])
    return pd.concat(parts)


def filter_by_time(df: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Keep rows with start <= timestamp <= end. Empty/None bounds are ignored."""
    if start:
        df = df[df["timestamp"] >= pd.to_datetime(start)]
    if end:
        df = df[df["timestamp"] <= pd.to_datetime(end)]
    return df


def aggregate_to_grid(df: pd.DataFrame, cell_deg: float = GRID_DEG) -> pd.DataFrame:
    """Average ΔT per grid cell, so busy routes don't dominate."""
    g = df.assign(
        cell_lat=(df["latitude"] / cell_deg).round() * cell_deg,
        cell_lon=(df["longitude"] / cell_deg).round() * cell_deg,
    )
    out = (
        g.groupby(["cell_lat", "cell_lon"])
        .agg(
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
            delta_mean=("delta_t", "mean"),
            temp_mean=("temperature_c", "mean"),
            count=("delta_t", "size"),
            rides=("ride", "nunique"),
            first=("timestamp", "min"),
            last=("timestamp", "max"),
        )
        .reset_index(drop=True)
    )
    return out[out["count"] >= MIN_CELL_POINTS]


# ───────────────────────────── map ─────────────────────────────

def build_heatmap(df: pd.DataFrame, show_raw_points: bool = False) -> folium.Map:
    """Map of ΔT (temperature compared with the same ride at the same time)."""
    if df.empty:
        m = folium.Map(location=HEILBRONN_CENTER, zoom_start=13, tiles="OpenStreetMap")
        folium.Marker(HEILBRONN_CENTER, popup="No data for the selected time range").add_to(m)
        return m

    cells = aggregate_to_grid(df)
    # Symmetric scale around 0, robust against outliers
    lim = float(np.nanpercentile(np.abs(cells["delta_mean"]), 95))
    lim = max(round(lim * 2) / 2, 0.5)

    colormap = cm.LinearColormap(DELTA_COLORS, vmin=-lim, vmax=lim)
    colormap.caption = "ΔT: temperature vs. ride baseline (°C)"

    m = folium.Map(location=HEILBRONN_CENTER, zoom_start=14, tiles="OpenStreetMap", control_scale=True)

    # Layer 1: smooth heat layer – only places hotter than their surroundings
    hot = cells[cells["delta_mean"] > 0]
    HeatMap(
        [[r.latitude, r.longitude, min(r.delta_mean / lim, 1.0)] for r in hot.itertuples()],
        name="Hotspots (ΔT > 0, warmer than ride baseline)",
        min_opacity=0.25,
        radius=22,
        blur=18,
        gradient={0.2: "#fddbc7", 0.5: DELTA_COLORS[3], 1.0: DELTA_COLORS[4]},
    ).add_to(m)

    # Layer 2: ΔT per grid cell with details on click
    cell_layer = folium.FeatureGroup(name="ΔT per area (click for details)")
    for r in cells.itertuples():
        value = min(max(r.delta_mean, -lim), lim)
        popup = (
            f"<b>{r.delta_mean:+.1f} °C</b> vs. ride baseline<br>"
            f"Measured average: {r.temp_mean:.1f} °C<br>"
            f"{r.count} measurement(s) from {r.rides} ride(s)<br>"
            f"{r.first:%d.%m.%Y %H:%M} – {r.last:%d.%m.%Y %H:%M}"
        )
        folium.CircleMarker(
            location=[r.latitude, r.longitude],
            radius=6,
            color=colormap(value),
            weight=1,
            fill=True,
            fill_color=colormap(value),
            fill_opacity=0.85,
            popup=folium.Popup(popup, max_width=260),
            tooltip=f"{r.delta_mean:+.1f} °C",
        ).add_to(cell_layer)
    cell_layer.add_to(m)

    # Layer 3 (hidden): single measurements, thinned out evenly
    step = max(1, len(df) // MAX_RAW_POINTS)
    raw = df.iloc[::step]
    raw_name = "All measurements" if step == 1 else f"Sample of single points (every {step}th, display only)"
    raw_layer = folium.FeatureGroup(name=raw_name, show=show_raw_points)
    for r in raw.itertuples():
        folium.CircleMarker(
            location=[r.latitude, r.longitude],
            radius=2,
            color=colormap(min(max(r.delta_t, -lim), lim)),
            fill=True,
            fill_opacity=0.9,
            weight=0,
            tooltip=f"{r.delta_t:+.1f} °C (measured {r.temperature_c:.1f} °C) · {r.timestamp:%d.%m.%Y %H:%M}",
        ).add_to(raw_layer)
    raw_layer.add_to(m)

    colormap.add_to(m)
    add_count_box(m, df, "ΔT = measured − expected temperature of the same ride at that moment")
    folium.LayerControl(collapsed=False).add_to(m)
    m.fit_bounds([[df["latitude"].min(), df["longitude"].min()],
                  [df["latitude"].max(), df["longitude"].max()]])
    return m


def add_count_box(m: folium.Map, df: pd.DataFrame, note: str = "") -> None:
    """Small box: how many measurements (per file) the map is based on."""
    per_source = " · ".join(f"{k}: {v:,}" for k, v in df.groupby("source").size().items())
    m.get_root().html.add_child(folium.Element(
        '<div style="position:fixed;bottom:60px;right:10px;z-index:9999;background:#fff;'
        'padding:6px 10px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);'
        f'font:12px/1.4 sans-serif;max-width:320px"><b>{len(df):,} measurements</b><br>'
        f'{per_source}<br><span style="color:#666">{note}</span></div>'))


def heatmap_html(df: pd.DataFrame) -> str:
    """Return the map as a complete HTML page (for Flask or an iframe)."""
    return build_heatmap(df).get_root().render()


def hotspot_table(df: pd.DataFrame, n: int = 10, min_rides: int = 2) -> pd.DataFrame:
    """Top-n hottest grid cells, measured on at least `min_rides` different rides."""
    cells = aggregate_to_grid(df)
    cells = cells[cells["rides"] >= min_rides]
    return cells.nlargest(n, "delta_mean")[["latitude", "longitude", "delta_mean", "temp_mean", "count", "rides"]]


def summary_stats(df: pd.DataFrame) -> dict:
    """Key numbers for the website."""
    if df.empty:
        return {"count": 0}
    return {
        "count": int(len(df)),
        "rides": int(df["ride"].nunique()),
        "min": round(float(df["temperature_c"].min()), 1),
        "max": round(float(df["temperature_c"].max()), 1),
        "mean": round(float(df["temperature_c"].mean()), 1),
        "delta_max": round(float(aggregate_to_grid(df)["delta_mean"].max()), 1),
        "start": df["timestamp"].min(),
        "end": df["timestamp"].max(),
    }


def export_heatmap(df: pd.DataFrame, path: str | Path = DEFAULT_EXPORT) -> Path:
    """Save the map as a standalone HTML file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_heatmap(df).save(str(path))
    return path


if __name__ == "__main__":
    data = load_temperature_data()
    out = export_heatmap(data)
    print(f"Exported ΔT map: {len(data)} measurements, {data['ride'].nunique()} rides → {out}")
