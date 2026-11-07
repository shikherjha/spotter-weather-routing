import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { getTrip, planTrip } from "./api/client";
import { DEMO_WEATHER, type Trip, type TripRequest } from "./api/types";
import { DemoNote, LeaveLater, RouteList, TripLine, Verdict, WarningLink } from "./components/AnswerCard";
import { Details } from "./components/details/Details";
import { TripForm } from "./components/form/TripForm";
import { MapButtons, MapKey } from "./components/map/MapControls";
import { MapView, type Padding } from "./components/map/MapView";
import { Planning } from "./components/Planning";
import { TimeSlider } from "./components/TimeSlider";
import { useNarrowScreen } from "./hooks/useNarrowScreen";
import { routeById } from "./lib/route";
import { localInput } from "./lib/time";
import { useUi } from "./state";

// Desktop layout, in px. The map's padding is derived from these so routes are framed in the visible part.
const GAP = 24;
const CARD_W = 360;
const FORM_W = 400;
const SLIDER_LEFT = GAP + CARD_W + 36;
const PANEL_H = 480;
const MOBILE_MAP_H = 340;

const tripFromUrl = () => new URLSearchParams(window.location.search).get("trip");

/** The request behind a trip, so it can be edited or re-planned (also when opened from a shared link). */
const requestFrom = (t: Trip): TripRequest => ({
  origin: t.origin,
  destination: t.destination,
  departure_local: localInput(t.departure, t.origin_tz),
  load_lb: t.load_lb,
  interval_mi: t.interval_mi,
  hos: t.hos,
  weather: t.weather_model === DEMO_WEATHER ? DEMO_WEATHER : "live",
});

export default function App() {
  const narrow = useNarrowScreen();
  const qc = useQueryClient();
  const panel = useUi((s) => s.panel);
  const selected = useUi((s) => s.selected);
  const resetView = useUi((s) => s.resetView);
  const [tripId, setTripId] = useState(tripFromUrl);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    const onPop = () => {
      setTripId(tripFromUrl());
      setEditing(false);
    };
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
    onSuccess: (t) => {
      qc.setQueryData(["trip", t.id], t);
      window.history.pushState(null, "", `?trip=${t.id}`);
      setTripId(t.id);
      setEditing(false);
    },
  });

  const trip = editing ? null : (tripQ.data ?? null);

  // Each trip starts on its recommended route, at the first forecast hour, with the weather layer off.
  const shownTrip = trip?.id;
  useEffect(() => {
    if (shownTrip) resetView();
  }, [shownTrip, resetView]);

  // When the details panel closes, put focus back on the picked route rather than losing it to the page.
  const routeList = useRef<HTMLDivElement>(null);
  const hadPanel = useRef(false);
  useEffect(() => {
    if (hadPanel.current && !panel) routeList.current?.querySelector<HTMLElement>('[aria-pressed="true"]')?.focus();
    hadPanel.current = panel !== null;
  }, [panel]);

  const padding = useMemo<Padding>(() => {
    if (narrow) return { top: 70, bottom: 30, left: 30, right: 30 };
    if (!trip) return { top: 90, bottom: 90, left: GAP + FORM_W + 56, right: 90 };
    if (panel) return { top: 90, bottom: PANEL_H + 40, left: 90, right: 90 };
    return { top: 90, bottom: 150, left: GAP + CARD_W + 56, right: 90 };
  }, [narrow, panel, trip]);

  const replan = (departure: number) => {
    if (trip) plan.mutate({ ...requestFrom(trip), departure_local: localInput(departure, trip.origin_tz) });
  };
  const edit = () => {
    plan.reset();
    setEditing(true);
  };
  const cancelEdit = () => {
    plan.reset();
    setEditing(false);
  };

  const route = trip ? routeById(trip, selected) : null;
  const loadError = tripQ.isError && !editing ? "That trip has expired. Plan it again below." : null;
  const form = (
    <TripForm
      initial={tripQ.data ? requestFrom(tripQ.data) : null}
      busy={plan.isPending}
      error={plan.error?.message ?? loadError}
      onSubmit={(r) => plan.mutate(r)}
      onCancel={editing ? cancelEdit : undefined}
    />
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
  const choices = trip && (
    <div ref={routeList} className="flex flex-col gap-3.5">
      <RouteList trip={trip} />
      <LeaveLater trip={trip} onReplan={replan} busy={plan.isPending} error={plan.error?.message ?? null} />
      <WarningLink trip={trip} />
    </div>
  );

  if (narrow) {
    return (
      <div className="h-full overflow-y-auto bg-surface text-ink">
        {!trip ? (
          <div className="mx-auto max-w-xl p-4">{tripQ.isLoading ? <Loading /> : form}</div>
        ) : (
          <>
            <div className="flex flex-col gap-3.5 p-4">{answer}</div>
            <div className="relative bg-map" style={{ height: MOBILE_MAP_H }}>
              <MapView trip={trip} padding={padding} />
              <MapButtons />
            </div>
            <div className="border-b border-rule px-4 py-2.5">
              <TimeSlider trip={trip} compact />
            </div>
            <div className="p-3 pb-6">{choices}</div>
            {panel && route && (
              <div className="fixed inset-0 z-30">
                <Details trip={trip} route={route} modal />
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
        <aside className="absolute z-10 max-h-[calc(100%-48px)] overflow-y-auto rounded-[14px] bg-surface p-6 shadow-float" style={{ top: GAP, left: GAP, width: FORM_W }}>
          {tripQ.isLoading ? <Loading /> : form}
        </aside>
      )}
      {plan.isPending && !trip && <Planning request={plan.variables} />}

      {trip && !panel && (
        <>
          <section
            aria-label="Recommendation"
            className="absolute z-10 flex max-h-[calc(100%-48px)] flex-col gap-3.5 overflow-y-auto rounded-[14px] bg-surface p-[18px] shadow-float"
            style={{ top: GAP, left: GAP, width: CARD_W }}
          >
            {answer}
            {choices}
          </section>
          <section
            aria-label="Forecast time"
            className="absolute z-10 rounded-[14px] bg-surface py-3 pr-[18px] pl-3 shadow-float"
            style={{ bottom: GAP, left: SLIDER_LEFT, width: `min(760px, calc(100% - ${SLIDER_LEFT + 220}px))` }}
          >
            <TimeSlider trip={trip} />
          </section>
          <MapKey />
        </>
      )}

      {trip && panel && route && (
        <div className="absolute inset-x-0 bottom-0 z-20" style={{ height: PANEL_H }}>
          <Details trip={trip} route={route} modal={false} />
        </div>
      )}
    </div>
  );
}

function Loading() {
  return <p className="m-0 text-sm text-ink-2">Loading your trip…</p>;
}
