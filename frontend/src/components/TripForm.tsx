import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { searchPlaces } from "../api/client";
import type { Place, TripRequest } from "../api/types";
import { localInput, nextHourInput } from "../lib/time";

const DEMO: Pick<TripRequest, "origin" | "destination" | "load_lb"> = {
  origin: { label: "Dallas, Texas, United States", lat: 32.7767, lon: -96.797 },
  destination: { label: "Denver, Colorado, United States", lat: 39.7392, lon: -104.9903 },
  load_lb: 42000,
};

const field = "h-11 w-full rounded-lg border border-[#C3C9D1] bg-surface px-3 text-[15px] text-ink dark:border-rule";

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

      <PlaceInput label="From" value={origin} onChange={setOrigin} placeholder="City or address" />
      <PlaceInput label="To" value={destination} onChange={setDestination} placeholder="City or address" />

      <div className="grid grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] gap-2.5">
        <label className="flex flex-col gap-1">
          <span className="text-[13px] font-semibold">Leave</span>
          <input type="datetime-local" required value={departure} onChange={(e) => setDeparture(e.target.value)} className={`num ${field} px-2`} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[13px] font-semibold">Load weight</span>
          <span className="relative">
            <input inputMode="numeric" value={load} onChange={(e) => setLoad(e.target.value)} className={`num ${field} pr-9`} />
            <span className="absolute top-3 right-3 text-sm text-ink-2">lb</span>
          </span>
        </label>
      </div>
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
              onClick={() => setEvery(n)}
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
}: {
  label: string;
  value: Place | null;
  onChange: (p: Place | null) => void;
  placeholder: string;
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
        className={field}
      />
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
