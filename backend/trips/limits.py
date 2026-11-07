"""Planning limits and tuning values, in one place."""

MAX_LEAD_DAYS = 5  # forecasts further out aren't decision-grade
TRUCK_MAX_MPH = 65.0  # cap for car-speed providers (a typical governed truck speed)
CORRIDOR_HALF_WIDTH_MI = 15.0  # the heatmap covers this far either side of every route
CHECKPOINT_RES = 7  # H3 cell (~1.2 km) whose forecast a checkpoint uses; routes share cells
HEATMAP_HOURS = 49  # the slider's 0..48 h
HEATMAP_ANCHOR_LEAD_H = 12  # leaving later than this from now: the slider starts at departure, not now
ADVISOR_HOURS = range(0, 25)  # departures the advisor re-scores: now .. +24 h
# Forecast locations per trip. Open-Meteo is fetched in batches of 500 and every location counts
# against the free quota, so long trips get a coarser corridor rather than more requests.
WEATHER_POINT_BUDGET = 900
ROUTE_CACHE_S = 30 * 60
TRIP_CACHE_S = 24 * 3600
POINTS_WAIT_S = 5.0  # NWS place/zone lookups, counted from when they start (alongside the forecast)
WARNINGS_WAIT_S = 8.0  # alert fetch plus triage; each alert's Jev call has its own shorter limit
