"""Cool Heilbronn – Flask website (owned by the Web Development role).

Run:  python app.py   then open http://127.0.0.1:5000

To use real data instead of the sample, either replace
data/sample_temperature.csv or start with:
    DATA_CSV=data/your_file.csv python app.py
"""

import os
from functools import lru_cache
from pathlib import Path

from flask import Flask, Response, render_template, request

from viz.heatmap import filter_by_time, heatmap_html, load_temperature_data, summary_stats

ROOT = Path(__file__).resolve().parent
DATA_CSV = Path(os.environ.get("DATA_CSV", ROOT / "data" / "sample_temperature.csv"))

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


@app.route("/map/view")
def heatmap_view():
    """The Folium map itself. Embedded on /map with an <iframe>."""
    df = get_data()
    start, end = time_range_from_request()
    try:
        df = filter_by_time(df, start, end)
    except (ValueError, TypeError):
        pass
    return Response(heatmap_html(df), mimetype="text/html")


@app.route("/analysis")
def analysis():
    return render_template("analysis.html", active="analysis", stats=summary_stats(get_data()))


@app.route("/solutions")
def solutions():
    return render_template("solutions.html", active="solutions")


if __name__ == "__main__":
    app.run(debug=True)
