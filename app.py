"""Cool Heilbronn – Flask website (owned by the Web Development role).

Run:  python app.py   then open http://127.0.0.1:5000

Uses the real senseBox:bike CSVs in data/ (the same files as the DI map):
    data/alles_kid_temp_clean.csv  (or alles_kid_temp.csv)
    data/OSEM_Bike_Data_cleaned.csv
If none of them exist, the invented sample is used.
To use other file(s):
    DATA_CSV=data/a.csv:data/b.csv python app.py       (separate files with ":")
"""

import os
from functools import lru_cache
from pathlib import Path

from flask import Flask, Response, render_template, request

from viz.heatmap import (
    DEFAULT_CSVS,
    filter_by_time,
    heatmap_html,
    load_temperature_data,
    summary_stats,
)

ROOT = Path(__file__).resolve().parent
SAMPLE_CSV = ROOT / "data" / "sample_temperature.csv"  # invented Day 1 sample


def _pick_data_files() -> tuple[Path, ...]:
    env = os.environ.get("DATA_CSV")
    if env:
        return tuple(Path(p) for p in env.split(os.pathsep) if p)
    real = [p for p in DEFAULT_CSVS if p.exists()]
    return tuple(real) if real else (SAMPLE_CSV,)


DATA_FILES = _pick_data_files()
DATA_LABEL = " + ".join(p.name for p in DATA_FILES)

app = Flask(__name__)


def _signature() -> tuple[tuple[str, ...], tuple[float, ...]]:
    """File paths + modification times. A changed file means a new cache key."""
    return (tuple(str(p) for p in DATA_FILES),
            tuple(p.stat().st_mtime for p in DATA_FILES))


@lru_cache(maxsize=4)
def _load(paths: tuple, mtimes: tuple):
    return load_temperature_data(paths)


def get_data():
    """Load all CSVs once and reload automatically when a file changes."""
    return _load(*_signature())


def time_range_from_request():
    """Read ?start=...&end=... (from <input type="datetime-local">)."""
    return request.args.get("start", "").strip(), request.args.get("end", "").strip()


@app.route("/")
def home():
    df = get_data()
    return render_template("index.html", active="home", stats=summary_stats(df), data_file=DATA_LABEL)


@app.route("/map")
def heatmap_page():
    df = get_data()
    start, end = time_range_from_request()
    error = None
    try:
        selected = filter_by_time(df, start, end)
    except (ValueError, TypeError):
        error = "Could not read the selected time range. Showing all data."
        start = end = ""
        selected = df
    stats = summary_stats(df)
    return render_template(
        "map.html",
        active="map",
        start=start,
        end=end,
        error=error,
        stats=summary_stats(selected),
        min_time=stats.get("start"),
        max_time=stats.get("end"),
        data_file=DATA_LABEL,
    )


@lru_cache(maxsize=32)
def _map_html(paths: tuple, mtimes: tuple, start: str, end: str) -> str:
    df = _load(paths, mtimes)
    try:
        df = filter_by_time(df, start, end)
    except (ValueError, TypeError):
        pass
    return heatmap_html(df)


@app.route("/map/view")
def heatmap_view():
    """The Folium map itself. Embedded on /map with an <iframe>."""
    start, end = time_range_from_request()
    html = _map_html(*_signature(), start, end)
    return Response(html, mimetype="text/html")


@app.route("/analysis")
def analysis():
    charts_dir = Path(app.static_folder) / "charts"

    supported_extensions = {".png", ".jpg", ".jpeg", ".webp"}

    charts = sorted(
        file.name
        for file in charts_dir.iterdir()
        if file.is_file() and file.suffix.lower() in supported_extensions
    ) if charts_dir.is_dir() else []

    return render_template(
        "analysis.html",
        active="analysis",
        stats=summary_stats(get_data()),
        charts=charts,
    )

@app.route("/solutions")
def solutions():
    return render_template("solutions.html", active="solutions")


if __name__ == "__main__":
    app.run(debug=True)