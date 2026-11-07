# 01 — The Problem, in Plain Language

Source: `reference/fs-assessment-spotter.pdf` (Spotter — Full Stack Developer assessment).

## What we are building
A **React + Django** web app. A truck driver types:
- where they start and where they're going
- when they leave (date + time)
- how heavy the load is (lbs)

The app answers one question: **"Which of 3 routes should I take, given the weather I'll actually hit and how heavy I am?"**

## The pipeline (what has to happen, in order)
1. **Get 3 routes** from a routing API (we don't build routing ourselves).
2. **Drop checkpoints** along each route every 10, 25 or 50 miles (the user picks the spacing).
3. **Work out when the truck gets to each checkpoint.** This is the key detail: we need the weather at *that time*, not the weather now.
4. **Get the forecast** for each checkpoint at its arrival time.
5. **Give each checkpoint a risk level** (Low → Moderate → High → Severe → No Travel) from wind, rain and snow, then apply the load-weight rules.
6. **Score each route** and recommend one using a fixed priority order.
7. **Show it all on a map**: routes, checkpoints, risk colours, ETAs, summaries.
8. **Weather heatmap** over the area around the routes (the "corridor"), with a **0–48 hour slider** that has to scrub smoothly.

## The rules (exactly as given)
| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | <25 | 25–34 | 35–44 | 45–54 | ≥55 |
| Rain (in/hr) | <0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow (in/hr) | <0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

Load rules (these override the wind level):
- wind ≥55 mph → No Travel, whatever the load
- wind 45–54 mph **and** load >30,000 lb → No Travel
- wind 35–44 mph **and** load >40,000 lb → Severe

Checkpoint risk = the **worst** of wind, rain and snow (after the load rules).

Route ranking, in strict order (only move to the next rule on a tie):
1. fewest Severe miles → 2. fewest High miles → 3. lowest average risk → 4. shortest travel time

## Ambiguities we must resolve on purpose (reviewers will check these)
| # | Ambiguity | Our decision (draft) |
|---|---|---|
| A1 | Rain 0.25 sits in both Moderate and High; same for 0.50 and 1.00, and for snow 1.0 and 2.0 | Lower bound inclusive, upper bound exclusive: `[0.10, 0.25)` is Moderate, so 0.25 is High. Top bands as written: wind ≥55 is No Travel; rain/snow need `> 1.00` / `> 3.0`, so exactly 1.00 is Severe. One table-driven function, with unit tests on every boundary. |
| A2 | Where does No Travel rank? The ranking rules only mention Severe and High | No Travel is a **hard gate**: any route with a No Travel mile ranks below every route without one, and the UI flags it. If all 3 have No Travel, recommend the one with the fewest No-Travel miles and say "consider delaying departure". |
| A3 | What "miles" a checkpoint covers | Each checkpoint stands for the stretch around it (half the spacing before and after; the end segments are clipped). Severe miles = the sum of those stretches. |
| A4 | "Average risk" | Distance-weighted mean of the numeric levels (Low=0 … No Travel=4), so long stretches count more than short ones. |
| A5 | Rule 4 says "travel time" but the intro says "balance" risk and time | Keep the strict order (it's what the brief specifies). Also show the trade-off ("Route B is +38 min but 0 Severe miles") so the balance is visible. |
| A6 | Trips longer than 48 h, or arrivals beyond the forecast horizon | Forecast APIs go further than 48 h (Open-Meteo: 7–16 days). The slider covers 0–48 h as asked; checkpoints use whatever horizon is available and get a lower confidence label further out. |
| A7 | Truck ETA vs car ETA | Car routing is too optimistic for a truck. Use a truck profile where the API has one, cap speed, and **include mandatory rest breaks** (FMCSA Hours-of-Service) on long trips; otherwise the weather is fetched for the wrong time. |
| A8 | Time zones | The departure is entered in the origin's local time and stored in UTC; ETAs are shown in each checkpoint's local zone. |
| A9 | Wind: sustained or gusts | The rule table says "wind". Classify on sustained wind (to match the table) and show gusts as extra context; make it a config flag. |

## How we're graded (this decides where effort goes)
- **40%** routes, weather, risk and recommendation logic → correctness, tests, clear rules
- **40%** UI, map and heatmap smoothness/performance → GPU rendering, slider with zero network calls
- **15%** code quality
- **5%** docs + Loom

> "Prioritize correctness and clarity over extra features." — the brief

So: every "extra" has to make the core better (more correct ETAs, a smoother map, clearer explanation). Novelty for its own sake doesn't count.

## Side note
`~/Downloads/fuel-prices-for-be-assessment.csv` (8,151 truck-stop fuel prices) belongs to a **different** Spotter assessment (backend fuel-stop optimisation). This brief doesn't use it. We leave it out unless we decide fuel stops are a worthwhile extra (likely not, given the "no extra features" line).
