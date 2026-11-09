import { useState, type FormEvent } from "react";

import { parseTrip } from "../../api/client";
import { DEMO_WEATHER, type Place, type TripRequest } from "../../api/types";
import { MAX_LOAD_LB, parseLoad } from "../../lib/load";
import { nextHourInput } from "../../lib/time";
import { DEFAULT_HEIGHT_FT, HEIGHTS_FT, feetInches } from "../../lib/truck";
import { fieldBg, fieldClass } from "./fields";
import { PlaceInput } from "./PlaceInput";

const DEMO: Pick<TripRequest, "origin" | "destination" | "load_lb"> = {
  origin: { label: "Dallas, Texas, United States", lat: 32.7767, lon: -96.797 },
  destination: { label: "Denver, Colorado, United States", lat: 39.7392, lon: -104.9903 },
  load_lb: 42000,
};

type FieldName = "origin" | "destination" | "departure" | "load" | "interval";

export function TripForm({
  initial,
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  initial: TripRequest | null;
  busy: boolean;
  error: string | null;
  onSubmit: (r: TripRequest) => void;
  onCancel?: () => void;
}) {
  const [origin, setOrigin] = useState<Place | null>(initial?.origin ?? null);
  const [destination, setDestination] = useState<Place | null>(initial?.destination ?? null);
  const [departure, setDeparture] = useState(initial?.departure_local ?? nextHourInput());
  const [load, setLoad] = useState(initial ? String(initial.load_lb) : "40000");
  const [spacing, setSpacing] = useState<TripRequest["interval_mi"]>(initial?.interval_mi ?? 25);
  const [heightFt, setHeightFt] = useState(initial?.height_ft ?? DEFAULT_HEIGHT_FT);
  const [hazmat, setHazmat] = useState(initial?.hazmat ?? false);
  const [hos, setHos] = useState(initial?.hos ?? true);
  const [demo, setDemo] = useState(initial?.weather === DEMO_WEATHER);
  const [problem, setProblem] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [reading, setReading] = useState(false);
  const [filled, setFilled] = useState<Set<FieldName>>(new Set());
  const [unsure, setUnsure] = useState<Set<FieldName>>(new Set());
  const [readNote, setReadNote] = useState<string | null>(null);

  const touched = (f: FieldName) => {
    setFilled((s) => new Set([...s].filter((x) => x !== f)));
    setUnsure((s) => new Set([...s].filter((x) => x !== f)));
  };

  const readTyped = async () => {
    if (typed.trim().length < 3 || reading) return;
    setReading(true);
    setReadNote(null);
    try {
      const r = await parseTrip(typed.trim());
      const got = new Set<FieldName>();
      if (r.origin) {
        setOrigin(r.origin);
        got.add("origin");
      }
      if (r.destination) {
        setDestination(r.destination);
        got.add("destination");
      }
      if (r.departure_local) {
        setDeparture(r.departure_local);
        got.add("departure");
      }
      if (r.load_lb) {
        setLoad(String(Math.round(r.load_lb)));
        got.add("load");
      }
      if (r.interval_mi) {
        setSpacing(r.interval_mi);
        got.add("interval");
      }
      setFilled(got);
      setUnsure(new Set(r.unsure));
      setReadNote(
        got.size === 0
          ? "Couldn't read a trip from that. Try: Dallas to Denver tomorrow at 6 am, 42k lbs."
          : r.unsure.length
            ? "Filled in the highlighted fields. Check the ones marked below."
            : "Filled in the highlighted fields. Check them, then plan.",
      );
    } catch (e) {
      setReadNote(e instanceof Error ? e.message : "Couldn't read that.");
    } finally {
      setReading(false);
    }
  };

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!origin || !destination) return setProblem("Pick a start and an end from the suggestions.");
    const loadLb = parseLoad(load);
    if (!(loadLb > 0 && loadLb <= MAX_LOAD_LB)) return setProblem("Enter the load in pounds, between 1 and 120,000 (for example 42000 or 42k).");
    setProblem(null);
    onSubmit({
      origin,
      destination,
      departure_local: departure,
      load_lb: loadLb,
      height_ft: heightFt,
      hazmat,
      interval_mi: spacing,
      hos,
      weather: demo ? DEMO_WEATHER : "live",
    });
  };

  const tryDemo = () => {
    setOrigin(DEMO.origin);
    setDestination(DEMO.destination);
    setLoad(String(DEMO.load_lb));
    setDemo(true);
    setProblem(null);
    // Leave on the next hour, Dallas time: the simulated storm is timed from then.
    const leave = nextHourInput("America/Chicago");
    setDeparture(leave);
    onSubmit({ ...DEMO, departure_local: leave, height_ft: heightFt, hazmat, interval_mi: 25, hos: true, weather: DEMO_WEATHER });
  };

  const message = problem ?? error;

  return (
    <form onSubmit={submit} aria-label="Plan a trip" className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="m-0 text-[22px] leading-7 font-bold">Plan a trip</h1>
        {onCancel && (
          <button type="button" onClick={onCancel} className="h-9 rounded-lg border border-rule px-3 text-sm font-semibold max-lg:h-11">
            Cancel
          </button>
        )}
      </div>

      <div className="flex flex-col gap-1.5 rounded-[10px] bg-tint p-3">
        <label htmlFor="typed-trip" className="text-[13px] font-semibold">
          Type the trip <span className="font-normal text-ink-2">(optional)</span>
        </label>
        <div className="flex gap-2">
          <input
            id="typed-trip"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void readTyped();
              }
            }}
            placeholder="Dallas to Denver tomorrow after lunch, 42k lbs"
            aria-describedby="typed-note"
            className={`${fieldClass} min-w-0 flex-1 bg-surface`}
          />
          <button
            type="button"
            onClick={() => void readTyped()}
            disabled={reading || typed.trim().length < 3}
            className="h-11 shrink-0 rounded-lg border border-ink bg-surface px-3.5 text-sm font-semibold disabled:opacity-50"
          >
            {reading ? "Reading…" : "Fill in"}
          </button>
        </div>
        <span id="typed-note" aria-live="polite" className="text-xs leading-[17px] text-ink-2">
          {readNote ?? "We fill in the fields below for you to check."}
        </span>
      </div>

      <PlaceInput
        label="From"
        value={origin}
        onChange={(p) => {
          setOrigin(p);
          touched("origin");
        }}
        placeholder="City or address"
        tinted={filled.has("origin")}
        check={unsure.has("origin") ? "We couldn't find this place. Pick it from the suggestions." : null}
      />
      <PlaceInput
        label="To"
        value={destination}
        onChange={(p) => {
          setDestination(p);
          touched("destination");
        }}
        placeholder="City or address"
        tinted={filled.has("destination")}
        check={unsure.has("destination") ? "We couldn't find this place. Pick it from the suggestions." : null}
      />

      <div className="grid grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] gap-2.5">
        <label className="flex flex-col gap-1">
          <span className="text-[13px] font-semibold">Leave</span>
          <input
            type="datetime-local"
            required
            value={departure}
            onChange={(e) => {
              setDeparture(e.target.value);
              touched("departure");
            }}
            className={`num ${fieldClass} px-2 ${fieldBg(filled.has("departure"))}`}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[13px] font-semibold">Load weight</span>
          <span className="relative">
            <input
              inputMode="decimal"
              value={load}
              onChange={(e) => {
                setLoad(e.target.value);
                touched("load");
              }}
              className={`num ${fieldClass} pr-9 ${fieldBg(filled.has("load"))}`}
            />
            <span className="absolute top-3 right-3 text-sm text-ink-2">lb</span>
          </span>
        </label>
      </div>
      {unsure.has("departure") && (
        <p className="-mt-2 mb-0 text-xs leading-[17px] font-semibold text-severe">Check the leave time: we weren't sure what you meant.</p>
      )}
      <p className="-mt-2 mb-0 text-xs leading-[17px] text-ink-2">
        Leave time is local time where you start. Loads over 30,000 lb hit wind limits sooner.
      </p>

      <div className="grid grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] items-end gap-2.5">
        <label className="flex flex-col gap-1">
          <span className="text-[13px] font-semibold">Truck height</span>
          <select value={heightFt} onChange={(e) => setHeightFt(Number(e.target.value))} className={`num ${fieldClass} px-2 ${fieldBg(false)}`}>
            {HEIGHTS_FT.map((h) => (
              <option key={h} value={h}>
                {feetInches(h)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex h-11 items-center gap-2.5">
          <input type="checkbox" checked={hazmat} onChange={(e) => setHazmat(e.target.checked)} className="size-5 accent-[var(--accent)]" />
          <span className="text-sm">Hazmat load</span>
        </label>
      </div>
      <p className="-mt-2 mb-0 text-xs leading-[17px] text-ink-2">Routes stay off roads with lower bridges, weight limits or hazmat bans.</p>

      <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
        <legend className="mb-1.5 p-0 text-[13px] font-semibold">Check the weather every</legend>
        <div className="grid grid-cols-3 gap-1 rounded-[10px] bg-tint p-[3px]">
          {([10, 25, 50] as const).map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={spacing === n}
              onClick={() => {
                setSpacing(n);
                touched("interval");
              }}
              className={`num h-10 rounded-[7px] text-sm ${spacing === n ? "bg-surface font-bold shadow-sm" : ""}`}
            >
              {n} mi
            </button>
          ))}
        </div>
      </fieldset>

      <label className="flex items-start gap-3 border-y border-rule py-3">
        <input type="checkbox" checked={hos} onChange={(e) => setHos(e.target.checked)} className="mt-0.5 size-5 accent-[var(--accent)]" />
        <span className="flex flex-col gap-0.5">
          <span className="text-sm font-semibold">Include required breaks and rest</span>
          <span className="text-xs leading-[17px] text-ink-2">A 30-min break after 8 h of driving and a 10-h rest after 11 h, so arrival times are real.</span>
        </span>
      </label>

      <label className="-mt-1 flex items-center gap-3">
        <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} className="size-5 accent-[var(--accent)]" />
        <span className="text-sm">Use a simulated storm (demo)</span>
      </label>

      {message && (
        <p role="alert" className="m-0 rounded-lg bg-tint px-3 py-2 text-sm text-severe">
          {message}
        </p>
      )}

      <button type="submit" disabled={busy} className="flex h-12 items-center justify-center gap-2.5 rounded-[10px] bg-accent text-base font-bold text-accent-ink disabled:opacity-80">
        {busy && <span aria-hidden="true" className="size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent" />}
        {busy ? "Checking the weather…" : "Find the safest route"}
      </button>
      <button type="button" onClick={tryDemo} disabled={busy} className="-mt-1 self-center text-sm font-semibold text-accent disabled:opacity-60">
        Or try Dallas → Denver in a simulated storm
      </button>
    </form>
  );
}
