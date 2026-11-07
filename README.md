# Weather-Aware Truck Routing

Pick the safest truck route for the weather the truck will **actually** drive into: forecasts are sampled at each checkpoint's ETA (including mandatory Hours-of-Service rest), classified against the load-aware risk rules, and ranked.

> Work in progress. Full write-up, architecture diagram and decisions table land with the final release.

## Stack
- **Backend**: Django 6 + Django Ninja (ASGI), NumPy/Shapely/H3 engine, Redis cache
- **Frontend**: React 19 + TypeScript, MapLibre GL + deck.gl
- **Data**: TomTom truck routing, Open-Meteo (NOAA NBM) forecasts, Photon geocoding

## Run locally
```bash
cp .env.example .env        # add TOMTOM_API_KEY (optional: falls back to OSRM)
make setup                  # uv sync + npm ci
make services               # Redis + Postgres via Docker
make backend                # http://localhost:8000/api/docs
make frontend               # http://localhost:5173
make check                  # lint + types + tests
```

## Docs
- [The problem, and decisions on ambiguous rules](docs/01-problem.md)
- [Research: APIs, algorithms, industry](docs/02-research.md)
- [Architecture & plan](docs/03-architecture-plan.md)
