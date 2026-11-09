import { useState, type FormEvent } from "react";

import { parseTrip } from "../../api/client";
import { DEMO_WEATHER, type Place, type TripRequest } from "../../api/types";
import { demoRequest } from "../../lib/demo";
import { MAX_LOAD_LB, parseLoad } from "../../lib/load";
import { nextHourInput } from "../../lib/time";
import { saveTruck, savedTruck } from "../../lib/truck";
import { fieldBg, fieldClass } from "./fields";
import { PlaceInput } from "./PlaceInput";
import { TruckPill, type TruckFields } from "./TruckPill";


type FieldName = "origin" | "destination" | "departure" | "load" | "interval";

export function TripForm({
  initial,
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  initial: Partial<TripRequest> | null;
  busy: boolean;
  error: string | null;
  onSubmit: (r: TripRequest) => void;
  onCancel?: () => void;
}) {
  const [origin, setOrigin] = useState<Place | null>(initial?.origin ?? null);
  const [destination, setDestination] = useState<Place | null>(initial?.destination ?? null);
  const [departure, setDeparture] = useState(initial?.departure_local ?? nextHourInput());
  const [truck, setTruck] = useState<TruckFields>(() => {
    const saved = savedTruck();
    return {
      load: String(initial?.load_lb ?? saved.load_lb),
      heightFt: initial?.height_ft ?? saved.height_ft,
      hazmat: initial?.hazmat ?? saved.hazmat,
    };
  });
  const [spacing, setSpacing] = useState<TripRequest["interval_mi"]>(initial?.interval_mi ?? 25);
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
        setTruck((t) => ({ ...t, load: String(Math.round(r.load_lb!)) }));
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
    const loadLb = parseLoad(truck.load);
    if (!(loadLb > 0 && loadLb <= MAX_LOAD_LB)) return setProblem("Enter the load in pounds, between 1 and 120,000 (for example 42000 or 42k).");
    setProblem(null);
    saveTruck({ load_lb: loadLb, height_ft: truck.heightFt, hazmat: truck.hazmat });
    onSubmit({
      origin,
      destination,
      departure_local: departure,
      load_lb: loadLb,
      height_ft: truck.heightFt,
      hazmat: truck.hazmat,
      skip_places: initial?.skip_places,
      interval_mi: spacing,
      hos,
      weather: demo ? DEMO_WEATHER : "live",
    });
  };

  const tryDemo = () => {
    const req = demoRequest({ height_ft: truck.heightFt, hazmat: truck.hazmat });
    setOrigin(req.origin);
    setDestination(req.destination);
    setTruck((t) => ({ ...t, load: String(req.load_lb) }));
    setDeparture(req.departure_local);
    setDemo(true);
    setProblem(null);
    onSubmit(req);
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
        {unsure.has("departure") && (
          <span className="text-xs leading-[17px] font-semibold text-severe">Check the leave time: we weren't sure what you meant.</span>
        )}
        <span className="text-xs leading-[17px] text-ink-2">Local time where you start.</span>
      </label>

      <TruckPill
        value={truck}
        onChange={(t) => {
          setTruck(t);
          touched("load");
        }}
        tinted={filled.has("load")}
      />

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
