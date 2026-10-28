"""Discomfort Index (DI) map for the Proposed Solutions page.

DI = 0.81·T + 0.01·RH·(0.99·T − 14.3) + 46.3     (T in °C, RH in %)

    DI < 75        comfortable          (green / blue)
    75 ≤ DI < 80   slightly unpleasant  (yellow / orange)
    DI ≥ 80        high alert           (red / purple)

DI describes how people *feel* the heat, so it uses the measured (absolute)
values. Measurements from hotter days/times naturally have a higher DI.

If the CSV has the columns Surface Asphalt / Surface Compacted / Surface Paving /
Surface Sett, one toggleable layer per road surface is added automatically.

Run:  python -m viz.di_map            → static/maps/heat_index_map.html
"""

from __future__ import annotations

from pathlib import Path

import branca.colormap as cm
import folium
import numpy as np
import pandas as pd
from folium.plugins import HeatMap

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "data" / "OSEM_Bike_Data_cleaned.csv"
DEFAULT_EXPORT = ROOT / "static" / "maps" / "heat_index_map.html"

HEILBRONN_CENTER = (49.1427, 9.2109)
HEILBRONN_BOUNDS = {"lat": (49.08, 49.20), "lon": (9.13, 9.30)}

SURFACE_COLUMNS = {
    "Surface Asphalt": "Asphalt",
    "Surface Compacted": "Compacted (soil/unpaved)",
    "Surface Paving": "Paving (blocks)",
    "Surface Sett": "Sett (cobblestone)",
}

# DI scale shown on the map
DI_MIN, DI_MAX = 60.0, 90.0
DI_COLORS = ["#2b83ba", "#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#d7191c", "#7b3294"]
DI_STOPS = [60, 68, 73, 75, 78, 80, 90]

GRID_DEG = 0.001
MIN_CELL_POINTS = 3
MAX_SURFACE_POINTS = 1500     # per surface layer, keeps the page fast


def discomfort_index(temp_c: pd.Series, rel_humidity: pd.Series) -> pd.Series:
    return 0.81 * temp_c + 0.01 * rel_humidity * (0.99 * temp_c - 14.3) + 46.3


def di_category(di: float) -> str:
    if di >= 80:
        return "High alert"
    if di >= 75:
        return "Slightly unpleasant"
    return "Comfortable"


def load_di_data(path: str | Path = DEFAULT_CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={"createdAt": "timestamp", "Temperature": "temperature_c",
                            "Rel. Humidity": "humidity"})
    df["timestamp"] = (pd.to_datetime(df["timestamp"], format="ISO8601", errors="coerce", utc=True)
                         .dt.tz_convert("Europe/Berlin").dt.tz_localize(None))
    for col in ("latitude", "longitude", "temperature_c", "humidity"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude", "temperature_c", "humidity"])

    lat0, lat1 = HEILBRONN_BOUNDS["lat"]
    lon0, lon1 = HEILBRONN_BOUNDS["lon"]
    df = df[df["latitude"].between(lat0, lat1) & df["longitude"].between(lon0, lon1)].copy()

    df["di"] = discomfort_index(df["temperature_c"], df["humidity"])

    surfaces = [c for c in SURFACE_COLUMNS if c in df.columns]
    if surfaces:
        # Dominant surface = the surface column with the highest value
        df["surface"] = df[surfaces].idxmax(axis=1).map(SURFACE_COLUMNS)
    return df.reset_index(drop=True)


def _grid(df: pd.DataFrame) -> pd.DataFrame:
    g = df.assign(
        cell_lat=(df["latitude"] / GRID_DEG).round() * GRID_DEG,
        cell_lon=(df["longitude"] / GRID_DEG).round() * GRID_DEG,
    )
    out = (g.groupby(["cell_lat", "cell_lon"])
             .agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"),
                  di=("di", "mean"), temp=("temperature_c", "mean"), hum=("humidity", "mean"),
                  count=("di", "size"))
             .reset_index(drop=True))
    return out[out["count"] >= MIN_CELL_POINTS]


def _to_weight(di: float) -> float:
    return float(np.clip((di - DI_MIN) / (DI_MAX - DI_MIN), 0, 1))


def build_di_map(df: pd.DataFrame) -> folium.Map:
    m = folium.Map(location=HEILBRONN_CENTER, zoom_start=14, tiles="OpenStreetMap", control_scale=True)
    if df.empty:
        return m

    colormap = cm.LinearColormap(DI_COLORS, index=DI_STOPS, vmin=DI_MIN, vmax=DI_MAX)
    colormap.caption = "Discomfort Index (DI)"

    cells = _grid(df)

    # Layer 1: DI heatmap of uncomfortable areas only.
    # Leaflet.heat ADDS overlapping points, so feeding every cell would turn all dense
    # routes purple. Only DI ≥ 75 is used: weight 0 at DI 75 → 1 at DI 85.
    uncomfortable = cells[cells["di"] >= 75]
    HeatMap(
        [[r.latitude, r.longitude, float(np.clip((r.di - 75) / 10, 0.05, 1))]
         for r in uncomfortable.itertuples()],
        name="DI heatmap (uncomfortable areas, DI ≥ 75)",
        min_opacity=0.25, radius=22, blur=18,
        gradient={0.2: "#ffffbf", 0.45: "#fdae61", 0.7: "#d7191c", 1.0: "#7b3294"},
    ).add_to(m)

    # Layer 2: DI per area with category
    area = folium.FeatureGroup(name="DI per area (click for details)")
    for r in cells.itertuples():
        color = colormap(min(max(r.di, DI_MIN), DI_MAX))
        folium.CircleMarker(
            [r.latitude, r.longitude], radius=5, color=color, fill=True, fill_color=color,
            fill_opacity=0.85, weight=1,
            tooltip=f"DI {r.di:.1f} – {di_category(r.di)}",
            popup=folium.Popup(
                f"<b>DI {r.di:.1f}</b> ({di_category(r.di)})<br>"
                f"Avg. temperature {r.temp:.1f} °C<br>Avg. humidity {r.hum:.0f} %<br>"
                f"{r.count} measurement(s)", max_width=240),
        ).add_to(area)
    area.add_to(m)

    # Layer 3: one layer per DI category (useful to show only the critical places)
    for name, lo, hi, show in [("Only DI ≥ 80 (high alert)", 80, 999, False),
                               ("Only DI 75–80 (slightly unpleasant)", 75, 80, False)]:
        layer = folium.FeatureGroup(name=name, show=show)
        for r in cells[(cells["di"] >= lo) & (cells["di"] < hi)].itertuples():
            folium.CircleMarker([r.latitude, r.longitude], radius=6, color=colormap(min(r.di, DI_MAX)),
                                fill=True, fill_opacity=0.9, weight=1,
                                tooltip=f"DI {r.di:.1f}").add_to(layer)
        layer.add_to(m)

    # Layer 4: road surface layers (only if the data has surface columns)
    if "surface" in df.columns:
        for surface in SURFACE_COLUMNS.values():
            sub = df[df["surface"] == surface]
            if sub.empty:
                continue
            step = max(1, len(sub) // MAX_SURFACE_POINTS)
            layer = folium.FeatureGroup(name=f"Surface: {surface} (mean DI {sub['di'].mean():.1f})", show=False)
            for r in sub.iloc[::step].itertuples():
                folium.CircleMarker([r.latitude, r.longitude], radius=3,
                                    color=colormap(min(max(r.di, DI_MIN), DI_MAX)),
                                    fill=True, fill_opacity=0.9, weight=0,
                                    tooltip=f"{surface} · DI {r.di:.1f}").add_to(layer)
            layer.add_to(m)

    colormap.add_to(m)
    m.get_root().html.add_child(folium.Element(
        '<div style="position:fixed;bottom:60px;left:10px;z-index:9999;background:#fff;'
        'padding:8px 10px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);'
        'font:13px/1.5 sans-serif">'
        '<b>Discomfort Index</b><br>'
        '<span style="color:#1a9641">●</span> &lt; 75 comfortable<br>'
        '<span style="color:#fdae61">●</span> 75–80 slightly unpleasant<br>'
        '<span style="color:#d7191c">●</span> ≥ 80 high alert</div>'))
    folium.LayerControl(collapsed=False).add_to(m)
    m.fit_bounds([[df["latitude"].min(), df["longitude"].min()],
                  [df["latitude"].max(), df["longitude"].max()]])
    return m


def di_summary(df: pd.DataFrame) -> dict:
    cats = df["di"].apply(di_category).value_counts(normalize=True) * 100
    return {
        "count": int(len(df)),
        "di_mean": round(float(df["di"].mean()), 1),
        "di_max": round(float(df["di"].max()), 1),
        "share": {k: round(float(v), 1) for k, v in cats.items()},
        "has_surface": "surface" in df.columns,
    }


def export_di_map(df: pd.DataFrame, path: str | Path = DEFAULT_EXPORT) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_di_map(df).save(str(path))
    return path


if __name__ == "__main__":
    data = load_di_data()
    out = export_di_map(data)
    print(f"Exported DI map ({len(data)} measurements) → {out}")
    print(di_summary(data))
    if "surface" not in data.columns:
        print("Note: no 'Surface ...' columns in this CSV → road surface layers were skipped.")
