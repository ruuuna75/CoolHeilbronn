# Cool Heilbronn

## Green City Hackathon Heilbronn 2026 · Team Apfelschorle 

Data Analysis: Amane Aoyama, Reina Takahashi, Ryuta Sasaki

Web Development: Benita Stoilova, Runa Shirata

### Topic: Heat Mitigation in the City of Heilbronn - What causes heat islands and how can the city deal with them? 

A website that shows where Heilbronn heats up: a temperature heatmap, a discomfort-index (DI) map, the analysis of what explains the temperature differences, and proposed solutions against urban heat. 
 

## Technology

Python, Flask, HTML, CSS

### Run the application

Run `app.py` using Python. App makes itsel available on `localhost:5000`.
Make sure to install the required packages.


## Data

| File | Content |
| --- | --- |
| `data/alles_kid_temp.csv` | Data from walking sensors, 61,410 readings, 1 - 3 Sept 2026 (about 10:30 - 14:20 local time) |
| `data/OSEM_Bike_Data_cleaned.csv` | Data from bike sensors, 54,979 readings, 5 Aug - 4 Sep 2026 |

Both files are loaded together, so the maps use **110,258 measurements** (shown in the box at the bottom right of each map).

### Check out the original datasets 

Walking sensors: https://cloud.reedu.de/s/X9x2XE9a9xCxLm8 (Green City Summer School 2026)

Bike sensors: https://api.atrai.bike (API use: https://hackathon.greencity.hn/resources/bike-data)  (Green City senseBox:bike campaign)

### Data columns of interest

| Column | Meaning |
| --- | --- |
| `timestamp` | Time of measurement (ISO 8601) |
| `latitude` | WGS84 latitude |
| `longitude` | WGS84 longitude |
| `temperature_c` | Air temperature in °C |
| `humidity` | Relative humidity in %  |


## How the maps work

### Temperature map (ΔT)

The measurements were recorded on different days and at different times, so raw temperatures would mostly show *when* someone measured, not *where* it is hot. The map therefore compares every measurement with the expected temperature of its own ride:

1. **Split into rides.** A gap of more than 30 minutes starts a new ride (145 rides).
2. **Expected temperature of a ride.** For rides of 30 minutes or less it is the ride's average.For longer rides it is a straight-line time trend, which removes the normal warming or cooling of the air during a long ride.
 3. **ΔT = measured temperature − expected temperature.** ΔT > 0 means hotter than normal for that
   ride at that moment.**Averag- per grid cell** of about 110 m × 75 m (0.001°), so a place that was passed many times
    does not look hotter just because it has more points.
5. **Colours** go from blue (cooler) through white (0) to red (hotter). The scale is ± the 95thpercentile of the cell values, so a few outliers do not wash out the colours.
 

Layers (toggle top right): **Hotspots** (smooth glow where ΔT > 0), **ΔT per area** (click a do ΔT, measured average, number of measurements and rides, time range) and a thinned-out **sample of single points** (display only, off by default).


### Discomfort Index map

The Discomfort Index describes how the heat *feels*. It uses temperature **and** humidity:

DI = 0.81 · T + 0.01 · RH · (0.99 · T − 14.3) + 46.3  (T in °C, RH in %)

| DI | Meaning |
| --- | --- |
| below 75 | comfortable |
| 75 to below 80 | slightly unpleasant |
| 80 and above | high alert |

It uses the same measurements and the same grid cells as the temperature map, so both maps show dots at the same places. Layers: **DI heatmap** (only areas with DI ≥ 75), **DI per area**, **only DI ≥ 80**, **only DI 75–80**. Road-surface layers appear automatically if the data has `Surface Asphalt / Compacted / Paving / Sett` columns (the current files do not).


### Map and analysis report use different methods

| | Maps | Analysis report |
| --- | --- | --- |
| Trip / ride split | gap > 30 min | gap > 5 min |
| Expected temperature | average (≤ 30 min) or time trend (> 30 min) | straight-line time trend |
| Walking sensors | all readings, one ride per recording | only the 2 Sept walk; each device track cut into 10-minute pieces |
| Grid cell | about 110 m × 75 m | 100 m |
| Cells shown | every cell with data | only cells visited on at least 2 trips |
| Unit | ΔT in °C | anomaly in K |

The maps are for visual exploration. **The numbers in the findings below come from the analysis report**, which is the stricter method.

Known limits of the maps:

- ΔT is relative to each ride, not absolute. A ride that stays in one district shows no difference.
- Within one ride, time and place change together, so the hotspot ranking depends on how the expected temperature is calculated. Treat the hotspots as candidates.
- The walking-sensor data has no device ID, and sensors walking side by side read 1–2 K apart (see the report). The maps do not separate the devices, so ΔT from the walking data can reflect which device walked where.


## View the full analysis report

Full report: [`analysis_report.pdf`](static/analysis_report.pdf)


## Statement of AI use

Due to the competition format, Generative AI has been used extensively but responsibly, especially in code development. The team claims responsibility for any overlooked errors.