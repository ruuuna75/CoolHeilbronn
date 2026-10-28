"""Cool Heilbronn – Flask website (owned by the Web Development role).

Run:  python app.py   then open http://127.0.0.1:5000

Uses data/alles_kid_temp.csv (real senseBox:bike data) if present,
otherwise the invented sample. To use another file:
    DATA_CSV=data/your_file.csv python app.py
"""

import os
from functools import lru_cache
from pathlib import Path

from flask import Flask, Response, render_template, request

from viz.heatmap import filter_by_time, heatmap_html, load_temperature_data, summary_stats

ROOT = Path(__file__).resolve().parent
REAL_CSV = ROOT / "data" / "alles_kid_temp.csv"      # senseBox:bike raw data
SAMPLE_CSV = ROOT / "data" / "sample_temperature.csv"  # invented Day 1 sample
DATA_CSV = Path(os.environ.get("DATA_CSV", REAL_CSV if REAL_CSV.exists() else SAMPLE_CSV))

app = Flask(__name__)


@lru_cache(maxsize=4)
def _load(path: str, mtime: float):
    return load_temperature_data(path)


def get_data():
    """Load the CSV once and reload it automatically when the file changes."""
    return _load(str(DATA_CSV), DATA_CSV.stat().st_mtime)


def time_range_from_request():
    """Read ?start=...&end=... (from <input type="datetime-local">)."""
    return request.args.get("start", "").strip(), request.args.get("end", "").strip()


@app.route("/")
def home():
    df = get_data()
    return render_template("index.html", active="home", stats=summary_stats(df), data_file=DATA_CSV.name)


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
        data_file=DATA_CSV.name,
    )


@lru_cache(maxsize=32)
def _map_html(path: str, mtime: float, start: str, end: str) -> str:
    df = _load(path, mtime)
    try:
        df = filter_by_time(df, start, end)
    except (ValueError, TypeError):
        pass
    return heatmap_html(df)


@app.route("/map/view")
def heatmap_view():
    """The Folium map itself. Embedded on /map with an <iframe>."""
    start, end = time_range_from_request()
    html = _map_html(str(DATA_CSV), DATA_CSV.stat().st_mtime, start, end)
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
