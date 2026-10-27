"""Temperature map for Cool Heilbronn.

Only four columns are used: timestamp, latitude, longitude, temperature_c.
Every other column in the CSV is ignored on purpose.

Interface for the web team:
    df = load_temperature_data("data/sample_temperature.csv")
    df = filter_by_time(df, start, end)          # optional
    html = heatmap_html(df)                      # full HTML page of the map
    export_heatmap(df, "static/maps/heatmap.html")

Run directly to export the map:  python -m viz.heatmap
"""

from __future__ import annotations

from pathlib import Path

import branca.colormap as cm
import folium
import pandas as pd
from folium.plugins import HeatMap

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "data" / "sample_temperature.csv"
DEFAULT_EXPORT = ROOT / "static" / "maps" / "heatmap.html"

HEILBRONN_CENTER = (49.1427, 9.2109)

# The only columns the map is allowed to use.
COLUMNS = ["timestamp", "latitude", "longitude", "temperature_c"]

# Accept a few common spellings from other datasets.
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
}

# Cool (blue) to hot (red). Same colours are used in the legend.
TEMP_COLORS = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"]

# Size of one grid cell for averaging (about 110 m north-south, 80 m east-west).
GRID_DEG = 0.001


def load_temperature_data(path: str | Path = DEFAULT_CSV) -> pd.DataFrame:
    """Read a CSV and keep only timestamp, latitude, longitude, temperature_c."""
    df = pd.read_csv(path)
    df = df.rename(columns={c: ALIASES.get(c.strip().lower(), c.strip().lower()) for c in df.columns})

    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing column(s) {missing}. Expected {COLUMNS}.")

    df = df[COLUMNS].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in ("latitude", "longitude", "temperature_c"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna()
    # Drop impossible values (bad GPS fix or broken sensor).
    df = df[df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)]
    df = df[df["temperature_c"].between(-40, 60)]
    return df.sort_values("timestamp").reset_index(drop=True)


def filter_by_time(df: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Keep rows with start <= timestamp <= end. Empty/None bounds are ignored."""
    if start:
        df = df[df["timestamp"] >= pd.to_datetime(start)]
    if end:
        df = df[df["timestamp"] <= pd.to_datetime(end)]
    return df


def aggregate_to_grid(df: pd.DataFrame, cell_deg: float = GRID_DEG) -> pd.DataFrame:
    """Average the measurements per small grid cell.

    Without this, places with many measurements (e.g. a busy bike route)
    would look hotter on the heat layer just because they have more points.
    """
    g = df.assign(
        cell_lat=(df["latitude"] / cell_deg).round() * cell_deg,
        cell_lon=(df["longitude"] / cell_deg).round() * cell_deg,
    )
    out = (
        g.groupby(["cell_lat", "cell_lon"])
        .agg(
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
            temp_mean=("temperature_c", "mean"),
            temp_min=("temperature_c", "min"),
            temp_max=("temperature_c", "max"),
            count=("temperature_c", "size"),
            first=("timestamp", "min"),
            last=("timestamp", "max"),
        )
        .reset_index(drop=True)
    )
    return out


def build_heatmap(df: pd.DataFrame, show_raw_points: bool = False) -> folium.Map:
    """Build the Folium map from timestamp/latitude/longitude/temperature_c."""
    if df.empty:
        m = folium.Map(location=HEILBRONN_CENTER, zoom_start=13, tiles="OpenStreetMap")
        folium.Marker(HEILBRONN_CENTER, popup="No data for the selected time range").add_to(m)
        return m

    cells = aggregate_to_grid(df)
    # Scale colours to the area averages, so differences between places stand out.
    vmin = float(cells["temp_mean"].min())
    vmax = float(cells["temp_mean"].max())
    if vmax - vmin < 0.1:
        vmax = vmin + 0.1

    colormap = cm.LinearColormap(TEMP_COLORS, vmin=vmin, vmax=vmax)
    colormap.caption = "Average temperature (°C)"

    m = folium.Map(location=HEILBRONN_CENTER, zoom_start=14, tiles="OpenStreetMap", control_scale=True)

    # Layer 1: smooth heat layer (one point per grid cell, weighted by temperature)
    heat_points = [
        [r.latitude, r.longitude, (r.temp_mean - vmin) / (vmax - vmin)]
        for r in cells.itertuples()
    ]
    HeatMap(
        heat_points,
        name="Heatmap",
        min_opacity=0.3,
        radius=22,
        blur=18,
        gradient={0.0: TEMP_COLORS[0], 0.25: TEMP_COLORS[1], 0.5: TEMP_COLORS[2],
                  0.75: TEMP_COLORS[3], 1.0: TEMP_COLORS[4]},
    ).add_to(m)

    # Layer 2: colour-coded cells with details on click
    cell_layer = folium.FeatureGroup(name="Average per area (click for details)")
    for r in cells.itertuples():
        popup = (
            f"<b>{r.temp_mean:.1f} °C</b> average<br>"
            f"Min {r.temp_min:.1f} °C · Max {r.temp_max:.1f} °C<br>"
            f"{r.count} measurement(s)<br>"
            f"{r.first:%d.%m.%Y %H:%M} – {r.last:%d.%m.%Y %H:%M}"
        )
        folium.CircleMarker(
            location=[r.latitude, r.longitude],
            radius=6,
            color=colormap(r.temp_mean),
            weight=1,
            fill=True,
            fill_color=colormap(r.temp_mean),
            fill_opacity=0.85,
            popup=folium.Popup(popup, max_width=250),
            tooltip=f"{r.temp_mean:.1f} °C",
        ).add_to(cell_layer)
    cell_layer.add_to(m)

    # Layer 3 (hidden by default): every single measurement
    raw_layer = folium.FeatureGroup(name="All measurements", show=show_raw_points)
    for r in df.itertuples():
        folium.CircleMarker(
            location=[r.latitude, r.longitude],
            radius=2,
            color=colormap(min(max(r.temperature_c, vmin), vmax)),
            fill=True,
            fill_opacity=0.9,
            weight=0,
            tooltip=f"{r.temperature_c:.1f} °C · {r.timestamp:%d.%m.%Y %H:%M}",
        ).add_to(raw_layer)
    raw_layer.add_to(m)

    colormap.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.fit_bounds([[df["latitude"].min(), df["longitude"].min()],
                  [df["latitude"].max(), df["longitude"].max()]])
    return m


def heatmap_html(df: pd.DataFrame) -> str:
    """Return the map as a complete HTML page (for Flask or an iframe)."""
    return build_heatmap(df).get_root().render()


def summary_stats(df: pd.DataFrame) -> dict:
    """Key numbers for the website (min, max, average, time range)."""
    if df.empty:
        return {"count": 0}
    return {
        "count": int(len(df)),
        "min": round(float(df["temperature_c"].min()), 1),
        "max": round(float(df["temperature_c"].max()), 1),
        "mean": round(float(df["temperature_c"].mean()), 1),
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
    print(f"Exported map with {len(data)} measurements to {out}")
