# 03 — Architecture & Plan (DRAFT, for review)

## Guiding principles
1. **The rules engine is pure, deterministic and fully tested.** No Django, no HTTP, no AI inside it. Same input → same output, every time.
2. **Correct timing beats more features.** The weather has to be sampled where the truck *will be*, *when* it will be there.
3. **The map never waits on the network.** Everything the slider needs is already on the GPU.
4. **External APIs are replaceable plug-ins.** If TomTom fails, switch to HERE. Tests run on recorded responses.
5. **AI explains decisions, it never makes them.**

---

## The flow of one request

```
Browser                         Django (ASGI, async)                         Outside world
───────                         ────────────────────                         ─────────────
form ──POST /api/trips──▶  1. Resolve places ............................▶ TomTom geocode (Photon for typing)
                           2. Get routes (truck, weight, departAt) .........▶ TomTom (fallback HERE)
                              └ <3 distinct? → via-point / avoid-area + dedupe
                           3. Build drive-time curve t(mile) from per-point times
                              └ apply Hours-of-Service → wall-clock ETA(mile) + rest stops
                           4. Drop checkpoints every 10/25/50 mi (searchsorted + interpolate)
                           5. Build corridor: buffer → H3 res-6 cells (draw) / res-5 parents (fetch)
                           6. Weather: one batched POST for all unique points .▶ Open-Meteo NBM (Redis-cached)
                           7. Classify each checkpoint (rules + load) → level + reason
                           8. Score routes → rank lexicographically → explain why
                           9. Departure advisor: re-score at +0…+24 h (no new API calls)
◀── SSE stream: routes → checkpoints+risk → recommendation → heatmap bytes
```

Results stream back in stages (Server-Sent Events). Routes appear on the map in about 1 s and the heatmap fills in after. This feels faster than one 4-second spinner, and it's cheap to do with async Django.

---

## Backend

| Concern | Choice | Why |
|---|---|---|
| Framework | **Django 5 + Django Ninja**, ASGI (uvicorn) | Ninja gives Pydantic-typed request/response schemas and auto OpenAPI docs, which is cleaner than DRF for a typed API. ASGI enables async I/O and SSE. |
| HTTP client | `httpx.AsyncClient` + `tenacity` (retry + backoff + jitter) | All slow work is waiting on APIs, so we run the calls concurrently. |
| Cache | **Redis** | Weather keyed by (model, model-run time, H3 cell), so it expires exactly when new forecast data lands. Routes keyed by a request hash, short TTL. Also hosts the API quota token-bucket and "single-flight" locks (two identical requests → one upstream call). |
| DB | Postgres (SQLite locally) | Save computed trips so each has a **shareable permalink** (`/trip/abc123`). Good for the Loom and for reviewers. |
| Geometry | numpy, shapely 2, pyproj, h3 v4, polyline, timezonefinder | Vectorised maths, no per-point Python loops. |
| **Celery?** | **No (deliberately)** | One request is ~4 outbound calls, all I/O-bound. `asyncio.gather` finishes them in seconds. Celery would add a broker, workers and polling for no benefit, and could make things slower. If we ever pre-warm popular corridors, a small `arq` or cron job is enough. Explaining this choice in the README shows judgement. |

### Code layout (ports & adapters)
```
backend/
  engine/            ← pure Python, zero Django imports, 100% unit-tested
    rules.py         risk table as data + load overrides → (level, reason)
    geometry.py      cumulative miles, interpolate-at-mile, bearings, simplify
    eta.py           drive-time curve + Hours-of-Service simulator
    sampling.py      checkpoints + mile attribution (midpoint method)
    corridor.py      buffer → H3 cells, cell → nearest route mile
    scoring.py       per-route stats, lexicographic ranking, "why" explanation
    advisor.py       departure-time sweep
  providers/         ← adapters behind small interfaces
    routing/  tomtom.py  here.py  osrm.py (dev)
    weather/  openmeteo.py
    alerts/   nws.py
  api/               ← Django Ninja views, schemas, SSE
  ai/                ← optional LLM layer (feature-flagged)
```

### Exact rule semantics (written down + tested)
- Bands are half-open `[lower, upper)`, e.g. rain `[0.10, 0.25)` = Moderate. Top bands follow the brief literally: wind `≥55`, rain `>1.00`, snow `>3.0`.
- Load rules only ever **raise** the level: `final = max(weather_level, load_level)`. `>30,000` and `>40,000` are strict.
- Checkpoint level = worst of wind/rain/snow, and we record *which* one drove it (for the UI: "Severe — wind 41 mph × 44,000 lb load").
- Miles per checkpoint: midpoint-to-midpoint. The sum equals the route length exactly (asserted in tests).
- Ranking key: `(has_no_travel, no_travel_mi, severe_mi, high_mi, avg_risk, duration)`, with explicit rounding tolerances so floating-point noise never flips a decision.
- Weather at ETA: rain/snow/gust use the hour bucket that *contains* the ETA. Sustained wind is linearly interpolated.

### Testing
- **Boundary table tests** for every threshold (24.99/25/34.99/35…, 30,000/30,001 lb).
- **Property-based tests** (Hypothesis): more wind never lowers risk; more load never lowers risk; miles always sum to route length; ranking is stable under input order.
- **Golden tests**: recorded real API responses (VCR) → full pipeline → snapshot. Deterministic, offline, fast.
- Frontend: Vitest for data decoding/colour logic; Playwright smoke test (enter trip → 3 routes → slider moves).

### Resilience & honesty
- Timeouts on every call, provider fallback, 429-aware backoff.
- **Demo mode**: 3–4 pre-recorded showcase trips (e.g., a winter storm on I-80 Wyoming), so the hosted app always works, even when free quotas run out.
- `Server-Timing` response header: routing / weather / compute time in milliseconds, visible in DevTools. Numbers go in the README.

---

## Frontend

| Concern | Choice |
|---|---|
| App | React 19 + TypeScript + Vite |
| Map | MapLibre GL via `react-map-gl` + **deck.gl** overlay, OpenFreeMap basemap |
| Data fetching | TanStack Query (plus an SSE hook) |
| UI state | Zustand (selected route, slider hour, interval) |
| Styling | Tailwind + shadcn/ui |
| Charts | Small risk-profile strip under the map (risk vs miles, like an elevation profile) |
| Heavy work | Web Worker decodes the binary heatmap off the main thread |

### What the screen shows
- **Left panel**: trip form (or a natural-language box), the 3 route cards (time, Severe/High miles, avg risk, recommendation badge + one-line "why"), and the departure advisor strip ("Leave at 9 AM → 0 Severe miles").
- **Map**: routes coloured by risk segment; checkpoints (hover → ETA local time, wind/gust/rain/snow, level, reason); rest stops; heatmap hexes; NWS warning polygons.
- **Bottom**: the 0–48 h slider with play button. A **truck marker moves along each route to where it will be at that hour**, so you can *see* it driving into or out of the storm.

### Performance budget (measured and reported)
- Slider scrub: 60 fps, 0 network calls.
- Heatmap payload: ≤200 KB compressed.
- Time to first route on map: ~1 s.

---

## AI layer: "Code decides, Jev judges, the LLM writes"

Three tiers, each doing only what it's good at:

| Tier | What | Good at | Never does |
|---|---|---|---|
| **Code** (rules engine) | Risk levels, ranking, ETAs | Exact numbers, thresholds, maths | — it's the authority |
| **Jev** (TypeSafe System One) | Fast typed judgments on *unstructured* input | ~100 ms, calibrated probabilities, answers only from a closed set of options, $0.042 per 1M tokens | Generate text, do maths, compare numbers |
| **LLM** (Claude) | Writing prose; long-tail questions Jev isn't confident about | Language | Score risk or pick routes |

### Where Jev is used (and why it fits)
1. **Official alerts triage.** NWS alerts along the corridor are free text. One Jev call per alert (all questions asked together):
   - `hazard`: Choice of wind / blowing snow / **ice** / **fog-visibility** / **blowing dust** / flood / other
   - `affects_high_profile_vehicles`: Noul (a yes/no question that returns a probability)
   - `road_closure_mentioned`: Noul
   - `severity`: Score

   This catches dangers the brief's wind/rain/snow table can't see. Freezing rain is the #1 truck killer, and it isn't in the table. Shown as an **advisory layer** next to the ranking; the brief's ranking stays exactly as specified.
2. **Type-as-you-go trip input.** "Dallas to Denver tomorrow 6am, 42k lbs, avoid tolls" fills the form *live* while typing (~100 ms per call):
   - Code finds candidates: a regex for weight, a date parser, Photon place suggestions.
   - Jev picks *which* candidate is origin vs destination.
   - Jev answers closed-set fields: interval 10/25/50, tolls, "was this stated?".
   - Low-confidence fields get highlighted for the user to confirm.
3. **"Ask this trip" intent routing** (TypeSafe's own function-calling pattern):
   - Questions like "what if I leave at 9?", "worst stretch on route B?", "why not route A?" go to a Jev Choice that picks one of our tools.
   - Its arguments are closed-set Choices too: route A/B/C, hour offset 0–48.
   - Our engine computes the answer and a **template** phrases it, so there's no free text and no hallucination.
   - Only when Jev isn't confident ("none of these fit") does it fall back to Claude with tool-calling.
4. **Briefing fact-check.** When Claude writes the driver briefing, Jev checks each sentence against the result JSON ("is this claim supported?"). Unsupported sentences are dropped; our numeric check also runs.
5. *(Experimental, flagged)* **Road-camera check.** A state DOT camera frame plus the Noul "is the road snow-covered?". Image support is still beta at TypeSafe (it needs an opt-in header), so this stays off by default.

### Guardrails we follow (from Jev's documented weak spots)
- **Never give Jev raw numbers to compare.** Code converts them to named buckets first.
- Jev slightly favours the first option in a list, so we use neutral option order.
- **Pin the model version** (`jev-1.14.0`) so thresholds don't drift.
- **Act only on confident answers.** A Noul (yes/no question) counts as yes when its probability is ≥0.7 and as no when it's ≤0.3; anything in between goes to the user to confirm.
- **Jev runs server-side only.** The API key never reaches the browser.
- **Prompt-injection safety.** Jev's answers come from a closed set, so injected text in an alert or input can't produce an arbitrary action.

### Type safety end to end
- Pydantic models (Django Ninja) → OpenAPI → generated TypeScript types (`openapi-typescript`) on the frontend.
- Jev questions are declared as typed Pydantic models too (`pydantic-ai-slim[typesafe]` or `typesafe-sdk`).
- One source of truth for every shape, from API → backend → UI.

UI label: *"Decision computed by rules. AI used for reading alerts and your input."*

---

## Hosting & delivery
- **Backend + Redis + Postgres**: Railway. **Frontend**: Vercel (or Django serves the built SPA for one origin; we'll decide at deploy).
- Docker Compose for local dev; GitHub Actions: ruff, mypy, pytest, vitest, Playwright.
- README: architecture diagram, rule decisions table, trade-offs (Celery, H3, API choice), perf numbers, how to run.

## Build order
| Phase | What | Done when |
|---|---|---|
| 0 | Repo, Docker, CI, API keys | `make dev` runs both apps |
| 1 | `engine/` + tests | all rule/scoring/ETA tests green, no network |
| 2 | Providers + API + cache + SSE | real trip returns ranked JSON |
| 3 | Map, routes, checkpoints, cards | the core assessment is fully met |
| 4 | Heatmap + slider + truck animation | 60 fps measured |
| 5 | HOS toggle, departure advisor, NWS alerts | extras that improve correctness |
| 6 | AI layer | flagged, with fallback |
| 7 | Deploy, README, Loom | live URL |

Phases 1–4 are the assessment. 5–6 are what makes it stand out. **No deadline: all phases are in scope**, but we still build in this order: nothing in 5–6 starts before 1–4 are solid.

## Open decisions
1. ~~Deadline~~: none, so all phases are in scope.
2. **API keys**:
   - TomTom: required.
   - TypeSafe (Jev): console.typesafe.ai; no free tier listed, but it's very cheap.
   - Anthropic: for the briefing and fallback.
   - HERE: optional.
3. **Wind**: classify on sustained wind (literal brief, our default) or the worse of sustained/gust?
