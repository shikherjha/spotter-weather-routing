import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { parseTrip, searchPlaces } from "../api/client";
import type { Place, TripRequest } from "../api/types";
import { localInput, nextHourInput } from "../lib/time";

const DEMO: Pick<TripRequest, "origin" | "destination" | "load_lb"> = {
  origin: { label: "Dallas, Texas, United States", lat: 32.7767, lon: -96.797 },
  destination: { label: "Denver, Colorado, United States", lat: 39.7392, lon: -104.9903 },
  load_lb: 42000,
};

const field = "h-11 w-full rounded-lg border border-[#C3C9D1] px-3 text-[15px] text-ink dark:border-rule";
// Fields filled from the typed sentence are tinted until the driver touches them.
const bg = (filled: boolean) => (filled ? "bg-accent/10" : "bg-surface");

type FieldName = "origin" | "destination" | "departure" | "load" | "interval";

export function TripForm({
  initial,
  busy,
  error,
  onSubmit,
}: {
  initial: TripRequest | null;
  busy: boolean;
  error: string | null;
  onSubmit: (r: TripRequest) => void;
}) {
  const [origin, setOrigin] = useState<Place | null>(initial?.origin ?? null);
  const [destination, setDestination] = useState<Place | null>(initial?.destination ?? null);
  const [departure, setDeparture] = useState(initial?.departure_local ?? nextHourInput());
  const [load, setLoad] = useState(initial ? String(initial.load_lb) : "40000");
  const [interval, setEvery] = useState<TripRequest["interval_mi"]>(initial?.interval_mi ?? 25);
  const [hos, setHos] = useState(initial?.hos ?? true);
  const [demo, setDemo] = useState(initial?.weather === "demo_storm");
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
        setEvery(r.interval_mi);
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

  const loadNum = Number(load.replace(/[^\d.]/g, ""));

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!origin || !destination) return setProblem("Pick a start and an end from the suggestions.");
    if (!Number.isFinite(loadNum) || loadNum <= 0 || loadNum > 120000) return setProblem("Enter a load between 1 and 120,000 lb.");
    setProblem(null);
    onSubmit({
      origin,
      destination,
      departure_local: departure,
      load_lb: loadNum,
      interval_mi: interval,
      hos,
      weather: demo ? "demo_storm" : "live",
    });
  };

  const tryDemo = () => {
    setOrigin(DEMO.origin);
    setDestination(DEMO.destination);
    setLoad(String(DEMO.load_lb));
    setDemo(true);
    setProblem(null);
    // Leave on the next hour, Dallas time, so the storm meets the truck as designed.
    const leave = localInput((Math.floor(Date.now() / 3_600_000) + 1) * 3600, "America/Chicago");
    setDeparture(leave);
    onSubmit({ ...DEMO, departure_local: leave, interval_mi: 25, hos: true, weather: "demo_storm" });
  };

  const message = problem ?? error;

  return (
    <form onSubmit={submit} aria-label="Plan a trip" className="flex flex-col gap-4">
      <h1 className="m-0 text-[22px] leading-7 font-bold">Plan a trip</h1>

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
            className={`${field} min-w-0 flex-1 bg-surface`}
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
            className={`num ${field} px-2 ${bg(filled.has("departure"))}`}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[13px] font-semibold">Load weight</span>
          <span className="relative">
            <input
              inputMode="numeric"
              value={load}
              onChange={(e) => {
                setLoad(e.target.value);
                touched("load");
              }}
              className={`num ${field} pr-9 ${bg(filled.has("load"))}`}
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

      <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
        <legend className="mb-1.5 p-0 text-[13px] font-semibold">Check the weather every</legend>
        <div className="grid grid-cols-3 gap-1 rounded-[10px] bg-tint p-[3px]">
          {([10, 25, 50] as const).map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={interval === n}
              onClick={() => {
                setEvery(n);
                touched("interval");
              }}
              className={`num h-10 rounded-[7px] text-sm ${interval === n ? "bg-surface font-bold shadow-sm" : ""}`}
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

function PlaceInput({
  label,
  value,
  onChange,
  placeholder,
  tinted = false,
  check = null,
}: {
  label: string;
  value: Place | null;
  onChange: (p: Place | null) => void;
  placeholder: string;
  tinted?: boolean;
  check?: string | null;
}) {
  const id = useId();
  const [text, setText] = useState(value?.label ?? "");
  const [options, setOptions] = useState<Place[]>([]);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const typed = useRef(false);

  // Show the picked place's full name whenever the parent sets a new one.
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    if (value) setText(value.label);
  }

  useEffect(() => {
    if (!typed.current || text.trim().length < 2) {
      setOptions([]);
      return;
    }
    const ctl = new AbortController();
    const t = window.setTimeout(() => {
      searchPlaces(text.trim(), ctl.signal)
        .then((found) => {
          setOptions(found);
          setActive(0);
          setOpen(true);
        })
        .catch(() => undefined);
    }, 220);
    return () => {
      window.clearTimeout(t);
      ctl.abort();
    };
  }, [text]);

  const choose = (p: Place) => {
    typed.current = false;
    onChange(p);
    setOpen(false);
  };

  return (
    <div className="relative flex flex-col gap-1">
      <label htmlFor={id} className="text-[13px] font-semibold">
        {label}
      </label>
      <input
        id={id}
        role="combobox"
        aria-expanded={open && options.length > 0}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder={placeholder}
        value={text}
        onChange={(e) => {
          typed.current = true;
          setText(e.target.value);
          if (value) onChange(null);
        }}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (!open || !options.length) return;
          if (e.key === "ArrowDown") setActive((a) => Math.min(options.length - 1, a + 1));
          else if (e.key === "ArrowUp") setActive((a) => Math.max(0, a - 1));
          else if (e.key === "Enter") choose(options[active]);
          else if (e.key === "Escape") setOpen(false);
          else return;
          e.preventDefault();
        }}
        className={`${field} ${bg(tinted)}`}
      />
      {check && <span className="text-xs font-semibold text-severe">{check}</span>}
      {open && options.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="absolute top-full z-20 m-0 mt-1 w-full list-none overflow-hidden rounded-lg border border-rule bg-surface p-1 shadow-float">
          {options.map((p, i) => (
            <li
              key={`${p.label}-${p.lat}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(p);
              }}
              className={`cursor-pointer rounded-md px-2.5 py-2 text-sm ${i === active ? "bg-tint" : ""}`}
            >
              {p.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
