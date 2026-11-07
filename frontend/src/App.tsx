import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { getTrip, planTrip } from "./api/client";
import type { Trip, TripRequest } from "./api/types";
import { DemoNote, LeaveLater, RouteList, TripLine, Verdict, WarningLink } from "./components/Answer";
import { Details } from "./components/Details";
import { MapView, type Padding } from "./components/MapView";
import { TimeSlider } from "./components/TimeSlider";
import { TripForm } from "./components/TripForm";
import { localInput } from "./lib/time";
import { useIsMobile } from "./lib/useIsMobile";
import { routeById } from "./lib/trip";
import { useUi } from "./state";

const tripFromUrl = () => new URLSearchParams(window.location.search).get("trip");

/** Rebuild the request behind a trip, so it can be edited or re-planned from a shared link. */
const requestFrom = (t: Trip): TripRequest => ({
  origin: t.origin,
  destination: t.destination,
  departure_local: localInput(t.departure, t.origin_tz),
  load_lb: t.load_lb,
  interval_mi: t.interval_mi,
  hos: t.hos,
  weather: t.weather_model === "demo-storm" ? "demo_storm" : "live",
});

export default function App() {
  const mobile = useIsMobile();
  const qc = useQueryClient();
  const { theme, panel, selected, resetView, request, setRequest } = useUi();
  const [tripId, setTripId] = useState(tripFromUrl);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    const onPop = () => setTripId(tripFromUrl());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const tripQ = useQuery({
    queryKey: ["trip", tripId],
    queryFn: () => getTrip(tripId!),
    enabled: !!tripId,
    staleTime: Infinity,
    retry: false,
  });

  const plan = useMutation({
    mutationFn: planTrip,
    onSuccess: (t, req) => {
      qc.setQueryData(["trip", t.id], t);
      setRequest(req);
      window.history.pushState(null, "", `?trip=${t.id}`);
      setTripId(t.id);
      setEditing(false);
    },
  });

  const trip = editing ? null : (tripQ.data ?? null);

  // A new trip starts on its recommended route, at "now", with the weather layer off.
  useEffect(() => {
    if (trip) resetView(trip.recommendation.route_id, 0);
  }, [trip, resetView]);

  const padding = useMemo<Padding>(
    () =>
      mobile
        ? { top: 70, bottom: 30, left: 30, right: 30 }
        : { top: 90, bottom: panel ? 520 : 150, left: !trip ? 480 : panel ? 90 : 440, right: 90 },
    [mobile, panel, trip],
  );

  const replan = (departure: number) => {
    if (!trip) return;
    plan.mutate({ ...requestFrom(trip), departure_local: localInput(departure, trip.origin_tz) });
  };
  const edit = () => {
    if (trip && !request) setRequest(requestFrom(trip));
    setEditing(true);
  };

  const loadError = tripQ.isError && !editing ? "That trip has expired. Plan it again below." : null;
  const formError = plan.error?.message ?? loadError;
  const route = trip ? routeById(trip, selected ?? trip.recommendation.route_id) : null;
  const form = (
    <TripForm initial={request ?? (trip ? requestFrom(trip) : null)} busy={plan.isPending} error={formError} onSubmit={(r) => plan.mutate(r)} />
  );
  const answer = trip && (
    <>
      <TripLine trip={trip} onEdit={edit} />
      <div className="flex flex-col gap-3.5 border-t border-rule pt-3.5">
        <DemoNote trip={trip} />
        <Verdict trip={trip} />
      </div>
    </>
  );

  if (mobile) {
    return (
      <div className="h-full overflow-y-auto bg-surface text-ink">
        {!trip ? (
          <div className="p-4">{tripQ.isLoading ? <Loading /> : form}</div>
        ) : (
          <>
            <div className="flex flex-col gap-3.5 p-4">{answer}</div>
            <div className="relative h-[340px] bg-map">
              <MapView trip={trip} padding={padding} />
              <MapButtons />
            </div>
            <div className="border-b border-rule px-4 py-2.5">
              <TimeSlider trip={trip} compact />
            </div>
            <div className="flex flex-col gap-3 p-3 pb-6">
              <RouteList trip={trip} />
              <LeaveLater trip={trip} onReplan={replan} busy={plan.isPending} />
              <WarningLink trip={trip} />
            </div>
            {panel && route && (
              <div className="fixed inset-0 z-30">
                <Details trip={trip} route={route} />
              </div>
            )}
          </>
        )}
      </div>
    );
  }

  return (
    <div className="relative h-full overflow-hidden bg-map text-ink">
      <div className="absolute inset-0">
        <MapView trip={trip} padding={padding} />
      </div>
      <MapButtons />

      {!trip && (
        <aside className="absolute top-6 left-6 z-10 max-h-[calc(100%-48px)] w-[400px] overflow-y-auto rounded-[14px] bg-surface p-6 shadow-float">
          {tripQ.isLoading ? <Loading /> : form}
        </aside>
      )}
      {plan.isPending && <Planning request={plan.variables} />}

      {trip && !panel && (
        <>
          <section aria-label="Recommendation" className="absolute top-6 left-6 z-10 flex max-h-[calc(100%-48px)] w-[360px] flex-col gap-3.5 overflow-y-auto rounded-[14px] bg-surface p-[18px] shadow-float">
            {answer}
            <RouteList trip={trip} />
            <LeaveLater trip={trip} onReplan={replan} busy={plan.isPending} />
            <WarningLink trip={trip} />
          </section>
          <section aria-label="Forecast time" className="absolute bottom-6 left-[420px] z-10 w-[min(760px,calc(100%-640px))] min-w-[440px] rounded-[14px] bg-surface py-3 pr-[18px] pl-3 shadow-float">
            <TimeSlider trip={trip} />
          </section>
          <Key />
        </>
      )}

      {trip && panel && route && (
        <div className="absolute inset-x-0 bottom-0 z-20 h-[480px]">
          <Details trip={trip} route={route} />
        </div>
      )}
    </div>
  );
}

function MapButtons() {
  const { weatherOn, setWeather, theme, toggleTheme } = useUi();
  return (
    <div className="absolute top-6 right-6 z-10 flex gap-2 max-md:top-2.5 max-md:right-2.5">
      <button
        type="button"
        aria-pressed={weatherOn}
        onClick={() => setWeather(!weatherOn)}
        className={`flex h-10 items-center gap-2 rounded-[10px] border border-rule px-3.5 text-sm font-semibold shadow-float max-md:h-9 max-md:px-3 ${weatherOn ? "bg-ink text-surface" : "bg-surface text-ink"}`}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M4.5 12 A3 3 0 0 1 4.8 6 A4 4 0 0 1 12.5 7 A2.5 2.5 0 0 1 12 12 Z" />
        </svg>
        Weather
      </button>
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
        className="grid size-10 place-items-center rounded-[10px] border border-rule bg-surface text-ink shadow-float max-md:size-9"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
          {theme === "light" ? (
            <path d="M13 9.5A5.5 5.5 0 016.5 3a5.5 5.5 0 106.5 6.5z" />
          ) : (
            <path d="M8 3V1.5M8 14.5V13M3 8H1.5M14.5 8H13M4.5 4.5l-1-1M12.5 12.5l-1-1M4.5 11.5l-1 1M12.5 3.5l-1 1M10.5 8a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z" />
          )}
        </svg>
      </button>
    </div>
  );
}

function Key() {
  return (
    <div className="num absolute right-6 bottom-9 z-10 flex flex-col items-end gap-1 text-xs text-ink-2 max-lg:hidden">
      <span className="flex items-center gap-1.5 rounded bg-surface/85 px-1.5">
        <span className="size-2.5 rounded-full border-2 border-surface bg-ink" /> Break or rest stop
      </span>
      <span className="flex items-center gap-1.5 rounded bg-surface/85 px-1.5">
        <span className="size-2 rounded-full border-2 border-ink-2 bg-surface" /> Weather checked at each dot
      </span>
    </div>
  );
}

function Loading() {
  return <p className="m-0 text-sm text-ink-2">Loading your trip…</p>;
}

function Planning({ request }: { request: TripRequest | undefined }) {
  const name = (p: { label: string } | undefined) => p?.label.split(",")[0] ?? "";
  return (
    <section
      aria-live="polite"
      className="absolute top-6 left-1/2 z-20 w-[380px] -translate-x-1/2 rounded-xl bg-surface p-4 shadow-float max-md:top-auto max-md:bottom-4 md:left-[calc(50%+200px)]"
    >
      <p className="m-0 text-base font-bold">
        Planning {name(request?.origin)} → {name(request?.destination)}
      </p>
      <p className="m-0 mt-1 text-[13px] leading-5 text-ink-2">
        Finding truck routes and checking the forecast along each one. This usually takes 5 to 10 seconds.
      </p>
      <span className="mt-3 block h-1 overflow-hidden rounded-full bg-rule">
        <span className="block h-1 w-1/3 animate-[slide_1.2s_ease-in-out_infinite] rounded-full bg-accent" />
      </span>
    </section>
  );
}
