# 02 — Research Findings (checked Nov 2026)

Items marked *(unverified)* came from secondary sources or general knowledge, not from docs we checked.

---

## 1. Routing APIs: who can give us 3 truck routes?

| API | Truck mode | Weight | Max alternatives | Per-point timing | Free tier | Verdict |
|---|---|---|---|---|---|---|
| **TomTom Routing v1** | `travelMode=truck` | `vehicleWeight` (kg) | `maxAlternatives` 0–5 | **Yes**: `extendedRouteRepresentation=travelTime,distance` gives cumulative time and distance for *every* polyline point | 20k routes/mo, no card | **Primary** |
| HERE Routing v8 | `transportMode=truck` | `vehicle[grossWeight]` | up to 6 | `spans=duration,length` | 5k truck routes/mo | **Fallback** |
| openrouteservice | `driving-hgv` | tons | 3 | per step | 2k/day | ✗ alternatives only for routes **<100 km** |
| Valhalla (Stadia) | `truck` | tons | `alternates` | per maneuver | ~10k routes/mo | ✗ no alternates when a departure time is set |
| GraphHopper | truck | fixed profile | 2 default | per point | — | ✗ truck not on free plan |
| Mapbox | no (car + `max_weight`) | — | 2 (3 total) | per segment | 100k/mo | car speeds |
| Google Routes | TRUCK (gated, "contact us") | kg | 3 | per step | 10k/mo | access-gated |
| OSRM demo | car only | — | "not guaranteed" | per segment | 1 req/s, non-commercial | dev only |

**Key finding: no provider *guarantees* 3 routes.** Each provider's docs say "fewer may be returned". Long trips often come back with 1–2 routes. So we need our own fallback:
1. **Via-point**: take route 1's midpoint, push it sideways by about 10–20% of trip length (or snap it to a parallel interstate), and route origin → via → destination.
2. **Penalty / avoid-area**: put an avoid-polygon over the middle of route 1 and re-route (TomTom `avoidAreas`, HERE `avoid[areas]`).
3. **Dedupe**: reject a candidate that shares more than about 70% of its road with an existing route, or takes more than about 1.4× the best route's time. We measure overlap as the Jaccard similarity of the H3 cells each route passes through (see §3).

**How routing engines generate alternatives (plain version)**
- *Via-node (OSRM)*: search outward from both the start and the end. Spots where the two searches meet become "via" points, and each one gives a candidate route. Keep the candidates that aren't too long or too similar.
- *Plateau (GraphHopper)*: find long stretches of road that are on both the best-from-start tree and the best-to-end tree. A long plateau is a natural corridor, such as a different interstate.
- *Penalty*: make the best route's roads artificially expensive and search again.

**Geocoding**
- Photon (komoot) for type-ahead, debounced. It's free.
- TomTom or Mapbox to resolve the final address.
- Nominatim **forbids** autocomplete, so we don't use it for that.

Sources:
- https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-route
- https://docs.here.com/routing/docs/routing-v8-truck-routing
- https://heigit.org/openrouteservice-maps-alternative-routes-roundtrips-and-more/
- https://valhalla.github.io/valhalla/api/route/api-reference/
- https://github.com/graphhopper/graphhopper/blob/master/core/src/main/java/com/graphhopper/routing/AlternativeRoute.java
- https://github.com/project-osrm/osrm-backend/issues/3905
- https://operations.osmfoundation.org/policies/nominatim/

---

## 2. Weather data

**Primary: Open-Meteo.** Free, no key, hourly forecast up to 16 days, with the variables and units we need.
- **Variables**:
  - `wind_speed_10m`, `wind_gusts_10m`, `wind_direction_10m`
  - `rain`, `showers` (rain rate = `rain + showers`; `precipitation` would also count snow)
  - `snowfall` (cm of snow; Open-Meteo assumes a 7:1 snow-to-water ratio, so treat it as approximate)
  - `weather_code`
- **Units**: request `wind_speed_unit=mph` and `precipitation_unit=inch`. Request `timeformat=unixtime` to avoid daylight-saving problems.
- **Model**: `ncep_nbm_conus`, a 2.5 km grid updated hourly. Fallback: `gfs_seamless`. Don't hard-code HRRR, which Open-Meteo retires at the end of Nov 2026.
- **Batching**: up to **1000 locations per request**, sent as a **POST** (a GET that long fails with 414).
- **Limits (the real constraint)**:
  - **Each location counts as one call**: 600/min, 5k/hour, 10k/day, non-commercial.
  - A single 1000-point POST works, but the next request then gets a 429 for about a minute.
  - Paid plan: $29/mo for 1M calls. Self-hosting is possible with Docker.
- **Cache key**: each model publishes `meta.json` with `last_run_initialisation_time`. Use (model, run time, cell) as the cache key, so the cache expires exactly when new data exists.
- **Time semantics (common mistake)**: rain, snow and gusts are values for the **preceding hour**. The 15:00 value covers 14:00–15:00.
  - For an ETA of 14:20, use the 15:00 bucket. Don't interpolate those values, because it smears out peaks.
  - Sustained wind is instantaneous, so linear interpolation is fine for it.

**Other APIs checked and rejected**
- Tomorrow.io: 500/day.
- Visual Crossing: 1k records/day.
- OWM One Call: needs a card, 1 point per call, mm only.
- WeatherAPI: 3-day horizon on free, no batching.
- NWS api.weather.gov: free, but precip and snow come in **6-hour buckets**, which is too coarse for in/hr thresholds. We **do** use NWS `/alerts/active` to overlay official High Wind / Winter Storm warnings as extra context.
- Gridded HRRR/RRFS GRIB on AWS: technically possible, but far too much work for an assessment. We mention it as how this would scale.

**Domain nuances**
- NWS High Wind Warning: sustained ≥40 mph **or gusts** ≥58 mph. Wyoming DOT blow-over closures are driven by **gusts**. The brief just says "wind", so we classify on sustained wind (to match the brief), always show gusts, and offer a "gust-aware" toggle.
- Forecast skill drops with lead time. Convective rain timing is shaky beyond 6–12 h; wind and large-scale snow hold up better. We show a confidence badge based on lead time.

Sources:
- https://open-meteo.com/en/docs
- https://open-meteo.com/en/pricing
- https://www.weather.gov/documentation/services-web-api
- https://www.weather.gov/car/Warning_Criteria
- https://wyoroad.info/highway/definitions.html

---

## 3. Geospatial: H3 (the "Uber blocks" algorithm)

**What H3 is.** Uber's open-source system divides the whole Earth into **hexagons** at 16 sizes, and every hexagon has a 64-bit ID. To find which hexagon a point is in, you call one function (`latlng_to_cell`). Uber built it for pricing and dispatch: "how many riders and drivers are in this area right now?"

**Why hexagons.** A hexagon's 6 neighbours are all the same distance from its centre. A square has 2 different neighbour distances (side and diagonal). That makes "the area within X miles of the route" look even, and neighbour smoothing behaves well.

| Res | Edge | Area | Our use |
|---|---|---|---|
| 4 | 26 km | 1,770 km² | — |
| 5 | 9.9 km | 253 km² | **weather sampling grid** (close to forecast-model detail; saves API calls) |
| 6 | 3.7 km | 36 km² | **rendered heatmap cells** |
| 7 | 1.4 km | 5 km² | route-overlap fingerprint / checkpoint cache key |

**Why not S2 or geohash.** S2 (Google) uses squares. Geohash cells change size a lot with latitude and use string IDs. H3 has integer IDs, uniform cells, and deck.gl renders it natively.

**Important rendering detail.** deck.gl's `H3HexagonLayer` falls back to a slow drawing mode for resolution 5 or coarser, mixed resolutions, or pentagons. So we **render at a single resolution (6)** and never send compacted cells.

**Corridor construction**
- Project the route to metres, buffer it (Shapely), convert back to lat/lng, then fill it with H3 cells using "overlap" mode.
- Never buffer in degrees: a degree of longitude shrinks as you go north.
- Then each cell gets its nearest route mile, so it knows "when the truck is closest to me".

**Cell counts** (1,500-mile route, ±15 mi corridor)
- About 400 cells at res 5, which is what we fetch.
- About 2,700 cells at res 6, which is what we draw.

**Polyline maths**
- Vectorised haversine with `numpy.cumsum` gives cumulative miles.
- `np.searchsorted` finds the checkpoint at mile *d* in O(log n), then we interpolate inside that segment.
- Douglas–Peucker (`shapely.simplify`) shrinks geometry before it's sent to the browser.
- Haversine error is about 0.5% (roughly 7 mi over 1,500 mi), which is fine. `pyproj.Geod` is available if we need exact figures.

Sources:
- https://www.uber.com/blog/h3/
- https://h3geo.org/docs/core-library/restable
- https://h3geo.org/docs/api/regions
- https://uber.github.io/h3-py/api_quick.html
- https://deck.gl/docs/api-reference/geo-layers/h3-hexagon-layer

---

## 4. Frontend rendering (40% of the grade)

**Stack**
- **MapLibre GL** (free vector map) with an **OpenFreeMap** basemap (no key, no limits).
- **deck.gl** draws our data on the GPU. It's Uber's library; kepler.gl is built on it.

**How the slider gets to 60 fps**
1. Download all 49 hours of the heatmap **once**, as compact byte arrays (one byte per cell per hour).
2. Moving the slider makes **no network call**. It only changes which hour's colour each hexagon shows (`updateTriggers`).
3. Option B, if needed: give each cell-hour its own row and let the GPU filter by hour (`DataFilterExtension`). Then the CPU does no work at all.

**Layers**
- `PathLayer` draws the routes, coloured by risk along their length.
- `ScatterplotLayer` draws the checkpoints.
- `H3HexagonLayer` draws the heatmap.
- `TripsLayer` animates a truck icon to *where it will be* at the slider's time.

**Rejected: Leaflet + leaflet.heat.** It redraws on the CPU on every change, looks blurry, and isn't hexagon-accurate.

**Payload size**
- 2,700 cells × 49 h × 3 variables ≈ 400 KB as bytes, roughly 100–200 KB after gzip.
- Row-by-row JSON would be about 4 MB.

Sources:
- https://deck.gl/docs/developer-guide/performance
- https://deck.gl/docs/api-reference/extensions/data-filter-extension
- https://deck.gl/docs/api-reference/geo-layers/trips-layer
- https://openfreemap.org/

---

## 5. Industry practice and the trucking domain

**Spotter.ai** sells an "AI platform" for US trucking (TMS, dispatch, fuel, driver app). So the right product voice is practical and operator-first: **Go / Delay / Reroute**.

**Competitors doing this**
- Trimble PC*MILER Weather / CoPilot checks hazards at the truck's *planned time*, which is the same idea as ours.
- Drive Weather and Green Route Weather show a forecast at each point at arrival time.

**FMCSA Hours-of-Service (big correctness win)**
- A driver may drive 11 h after 10 h off.
- Nothing after the 14th hour on duty.
- A 30-min break is required after 8 h of driving.
- A 1,500-mile trip is about 25 h of driving, which really means **2+ days**.
- If we ignore this, every checkpoint after the first day gets weather for the **wrong time**, off by 10+ hours.

**Real-world nuance (put it in the README, don't change the rules)**
- In real crosswinds, **light or empty** trailers blow over first; WYDOT targets "lightly loaded" vehicles.
- The brief's rules say heavier = worse. We implement the brief exactly and note the difference.
- **Crosswind** = wind × |sin(wind direction − road direction)|. We show it as context.

**Algorithm ideas**
- *Departure-time optimisation*: re-score the same routes for departures at +0, +1, … +24 h. This uses forecast data we already downloaded, so it costs no extra API calls.
- *Lexicographic ranking* (the brief's) is safety first and easy to explain. We present it clearly and also show the time trade-off.

**AI in fleet products today**
- Samsara Agent Studio.
- Motive AI agents (Oct 2026).
- Uber Freight Insights AI *(unverified)*.

Sources:
- https://spotter.ai
- https://developer.trimblemaps.com/restful-apis/routing/route-reports/weather-alerts/
- https://www.fmcsa.dot.gov/regulations/hours-service/summary-hours-service-regulations
- https://www.sciencedirect.com/science/article/pii/S2046043022000028
- https://gomotive.com/motive-launches-new-ai-products-at-vision-25-to-power-the-next-era-of-physical-operations/

---

## 6. Jev (TypeSafe AI) — typed decision model

**What it is.** A "System One" model. You send it a **state** (text, JSON or an image) plus typed **questions**, and it returns typed answers with calibrated probabilities. It does **not** generate text.

**Question types**
- **Choice**: pick from up to 255 options. Returns the choice, the probabilities and a confidence.
- **Score**: 2–10 ordered levels.
- **Noul**: a yes/no question; returns P(yes).
- **Box**: find a region in an image.

**API**
- `POST https://api.typesafe.ai/v1/systemone`.
- All questions in one request run in parallel; the only limit is the 64k-token context.

**Speed and cost**
- About 100 ms per call.
- $0.042 per 1M input tokens; output is free.
- No free tier was listed.

**SDKs**
- Python: `typesafe-sdk`, which has an async client.
- Pydantic AI: `pydantic-ai-slim[typesafe]`, where the fields of a Pydantic model become the questions.
- JavaScript: `@typesafe-ai/sdk`, server-side only. The key must never be sent to the browser.

**Getting free-text values out**
- **Fixed sets.** Turn every function argument into a closed-set Choice and add a "was this stated?" Noul. The call's confidence is the lowest confidence of all its parts.
- **Open values** (numbers, places):
  1. Code finds candidates, using regex, a geocoder or NER.
  2. Jev picks the right candidate.
  3. Code normalises the value.
- **Dates.** Ask for the parts as Choices (month/day/weekday/relative offset), then let code do the calendar maths.

**Confidence**
- Confidence measures how spread out the answer's probabilities are. It is not the chance of being correct.
- Act on Nouls above 0.7 or below 0.3, and treat the middle band as "ask the user".
- Use stricter thresholds for riskier actions.

**Known weak spots**
- Can't calculate or count, and can't compare dates.
- Biased toward the first option.
- "Context rot" when given irrelevant detail.
- Can be steered by adversarial text.
- Prefers named categories over raw numbers.

**Images**
- Beta: needs the `TypeSafe-Danger-Zone-Images` header.
- PNG or JPEG only, 280–1568 px per side.

**Pin a model version** (`jev-1.14.0`); `jev-latest` changes over time.

Sources:
- https://docs.typesafe.ai/introduction
- https://docs.typesafe.ai/models.md
- https://docs.typesafe.ai/cookbooks/function_calling.md
- https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook.md
- https://docs.typesafe.ai/confidence.md
- https://docs.typesafe.ai/model-jaggedness.md
- https://docs.typesafe.ai/images.md
- https://pydantic.dev/docs/ai/models/typesafe/
- https://www.langchain.com/blog/building-a-harness-with-jev
