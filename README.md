# Cool Heilbronn – Urban Heat Map

Green City Hackathon 2026 · Topic: Climate Change – Mitigation (Green Capital Heilbronn)

A Flask website that shows a temperature heatmap of Heilbronn, the analysis findings,
and proposed solutions against urban heat.

![Map preview](docs/map_preview.png)

## Run it locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

| Page | URL |
| --- | --- |
| Home (key numbers) | `/` |
| Heatmap (with time filter) | `/map` |
| Data Analysis | `/analysis` |
| Proposed Solutions | `/solutions` |
| Map only (used inside `/map`) | `/map/view` |

## Data format

All datasets are converted to one CSV with these columns:

| Column | Example | Meaning |
| --- | --- | --- |
| `latitude` | `49.1427` | WGS84 latitude |
| `longitude` | `9.2185` | WGS84 longitude |
| `temperature_c` | `28.4` | Air temperature in °C |
| `timestamp` | `2025-07-15T14:30:00` | Time of measurement (ISO 8601) |
| `source` | `sensebox_bike` | Dataset name (not used on the map) |

**The map uses only `timestamp`, `latitude`, `longitude` and `temperature_c`.**
All other columns are dropped when the CSV is loaded (`COLUMNS` in `viz/heatmap.py`).
Common alternative names (`lat`, `lon`, `temp`, `temperature`, …) are renamed automatically.

`data/sample_temperature.csv` contains **invented sample data** for Day 1
(made by `scripts/make_sample_data.py`). Replace it with the cleaned real data:

```bash
# either overwrite data/sample_temperature.csv, or:
DATA_CSV=data/real_temperature.csv python app.py
```

## How the map works

- Measurements are averaged per small area (about 100 m × 100 m), so a street with
  many bike measurements does not look hotter just because it has more points.
- Colours go from blue (cool) to red (hot); the °C legend is in the top right.
- Layers (toggle top right): smooth **Heatmap**, **Average per area** (click a dot for
  average / min / max / number of measurements / time range), and **All measurements**.
- `/map?start=...&end=...` filters by time (the form on the page sets these).

Export the map as a standalone HTML file:

```bash
python -m viz.heatmap        # writes static/maps/heatmap.html
```

The map loads Leaflet and the OpenStreetMap background from the internet, so the
laptop needs a connection during the demo.

## Project structure

```
app.py                  Flask routes (Web Development)
viz/heatmap.py          Map: load data, build/export heatmap (Data Visualization)
templates/              HTML pages (base layout + 4 pages)
static/css/style.css    Styling
static/maps/            Exported map HTML
data/                   CSV data
scripts/                Helper scripts (sample data generator)
```

Interface between visualization and web:
`load_temperature_data()` → `filter_by_time()` → `heatmap_html(df)` / `summary_stats(df)`.

## Next steps (Day 2)

- [ ] Replace sample CSV with the cleaned real data (Summerschool Heat Islands, senseBox:bike, senseBox:home)
- [ ] Check measurement locations and temperature values on the map
- [ ] Mark top hotspots with names; tune colour scale and legend
- [ ] Analysis page: hotspot list, charts (`viz/charts.py`), findings text
- [ ] Solutions page: one card per solution with what / where / why
