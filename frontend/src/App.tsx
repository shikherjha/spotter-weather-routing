import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { getTrip, planTrip } from "./api/client";
import { DEMO_WEATHER, type Stop, type Trip, type TripRequest } from "./api/types";
import { DemoNote, LeaveLater, RouteCards, RouteList, TripLine, Verdict, WarningLink } from "./components/AnswerCard";
import { Brand, Mark } from "./components/Brand";
import { Details } from "./components/details/Details";
import { TripForm } from "./components/form/TripForm";
import { DemoLink, LiveLine, MyTruck, RecentTrips, WhereTo } from "./components/home/Home";
import { LayerChips, MapKey, ThemeButton } from "./components/map/MapControls";
import { MapView, type Padding } from "./components/map/MapView";
import { Planning } from "./components/Planning";
import { Sheet } from "./components/Sheet";
import { TimeSlider } from "./components/TimeSlider";
import { useNarrowScreen } from "./hooks/useNarrowScreen";
import { demoRequest } from "./lib/demo";
import { remember, type RecentTrip } from "./lib/recent";
import { routeById } from "./lib/route";
import { localInput } from "./lib/time";
import { savedTruck } from "./lib/truck";
import { useUi } from "./state";

// Desktop layout, in px. The map's padding is derived from these so routes are framed in the visible part.
const GAP = 24;
const CARD_W = 360;
const FORM_W = 400;
const SLIDER_LEFT = GAP + CARD_W + 36;
const PANEL_H = 480;

const tripFromUrl = () => new URLSearchParams(window.location.search).get("trip");

/** The request behind a trip, so it can be edited or re-planned (also when opened from a shared link). */
const requestFrom = (t: Trip): TripRequest => ({
  origin: t.origin,
  destination: t.destination,
  departure_local: localInput(t.departure, t.origin_tz),
  load_lb: t.load_lb,
  height_ft: t.height_ft,
  hazmat: t.hazmat,
  skip_places: t.skip_places,
  interval_mi: t.interval_mi,
  hos: t.hos,
  weather: t.weather_model === DEMO_WEATHER ? DEMO_WEATHER : "live",
});

export default function App() {
  const narrow = useNarrowScreen();
  const qc = useQueryClient();
  const panel = useUi((s) => s.panel);
  const openPanel = useUi((s) => s.openPanel);
  const selected = useUi((s) => s.selected);
  const resetView = useUi((s) => s.resetView);
  const [tripId, setTripId] = useState(tripFromUrl);
  const [editing, setEditing] = useState(false);
  // A trip being set up from home (a picked destination) or a recent trip to plan again.
  const [draft, setDraft] = useState<Partial<TripRequest> | null>(null);

  useEffect(() => {
    const onPop = () => {
      setTripId(tripFromUrl());
      setEditing(false);
      setDraft(null);
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
    onSuccess: (t, request) => {
      qc.setQueryData(["trip", t.id], t);
      remember(t, request, t.recommendation.route_id);
      window.history.pushState(null, "", `?trip=${t.id}`);
      setTripId(t.id);
      setEditing(false);
      setDraft(null);
    },
  });

  const trip = editing ? null : (tripQ.data ?? null);
  const loading = !!tripId && tripQ.isLoading && !editing;
  const expired = tripQ.isError && !editing;
  const view: "home" | "form" | "trip" = trip ? "trip" : editing || draft || expired ? "form" : "home";

  // Each trip starts on its recommended route, at the first forecast hour, with every layer off.
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
    if (narrow) return { top: 130, bottom: Math.round(window.innerHeight * 0.5) + 20, left: 40, right: 40 };
    if (!trip) return { top: 90, bottom: 90, left: GAP + FORM_W + 56, right: 90 };
    if (panel) return { top: 90, bottom: PANEL_H + 40, left: 90, right: 90 };
    return { top: 90, bottom: 150, left: GAP + CARD_W + 56, right: 90 };
  }, [narrow, panel, trip]);

  const goHome = () => {
    plan.reset();
    window.history.pushState(null, "", window.location.pathname);
    setTripId(null);
    setEditing(false);
    setDraft(null);
  };
  const openRecent = (r: RecentTrip) => {
    // Saved trips last a day; if this one has gone, the form opens with it filled in.
    setDraft(r.request);
    window.history.pushState(null, "", `?trip=${r.id}`);
    setTripId(r.id);
  };
  const replan = (departure: number) => {
    if (trip) plan.mutate({ ...requestFrom(trip), departure_local: localInput(departure, trip.origin_tz) });
  };
  const skipStop = (s: Stop) => {
    if (trip) plan.mutate({ ...requestFrom(trip), skip_places: [...trip.skip_places, [s.lat, s.lon]] });
  };
  const edit = () => {
    plan.reset();
    setEditing(true);
  };
  const cancelForm = () => {
    plan.reset();
    if (editing) setEditing(false);
    else goHome();
  };
  const demo = () => plan.mutate(demoRequest(savedTruck()));

  const route = trip ? routeById(trip, selected) : null;
  const form = (
    <TripForm
      key={tripId ?? "new"}
      initial={tripQ.data ? requestFrom(tripQ.data) : draft}
      busy={plan.isPending}
      error={plan.error?.message ?? (expired ? "That trip has expired. Check it and plan it again." : null)}
      onSubmit={(r) => plan.mutate(r)}
      onCancel={cancelForm}
    />
  );
  const home = (
    <>
      <WhereTo onPick={(p) => setDraft({ destination: p })} />
      <MyTruck />
      <RecentTrips onOpen={openRecent} />
      <DemoLink onDemo={demo} />
    </>
  );
  const answer = trip && (
    <>
      <TripLine trip={trip} onEdit={edit} onBack={goHome} />
      <div className="flex flex-col gap-3.5 border-t border-rule pt-3.5">
        <DemoNote trip={trip} />
        <Verdict trip={trip} />
      </div>
    </>
  );
  const leaveLater = trip && (
    <LeaveLater trip={trip} onReplan={replan} busy={plan.isPending} error={plan.error?.message ?? null} />
  );
  const map = <MapView trip={trip} padding={padding} onSkipStop={skipStop} skipping={plan.isPending} />;

  if (narrow) {
    return (
      <div className="relative h-full overflow-hidden bg-map text-ink">
        <div className="absolute inset-0">{map}</div>

        <div className="absolute inset-x-3 top-3 z-10 flex flex-col gap-2.5">
          {trip ? (
            <div className="rounded-[26px] bg-surface py-1.5 pr-1.5 pl-3 shadow-float">
              <TripLine trip={trip} onEdit={edit} onBack={goHome} />
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-[18px] bg-surface p-1.5 pl-3 shadow-float">
              <Mark size={22} />
              <div className="min-w-0 flex-1">{view === "home" && !loading ? <WhereTo onPick={(p) => setDraft({ destination: p })} /> : <PhoneTitle />}</div>
              <ThemeButton className="border-0 shadow-none" />
            </div>
          )}
          {view !== "form" && <LayerChips trip={trip} className="no-scrollbar -mx-3 overflow-x-auto px-3 pb-1" />}
        </div>

        {plan.isPending && view !== "form" && <Planning request={plan.variables} className="inset-x-3 top-[132px]" />}

        {loading && (
          <Sheet label="Loading">
            <p className="m-0 p-4 text-sm text-ink-2">Loading your trip…</p>
          </Sheet>
        )}
        {!loading && view === "home" && (
          <Sheet label="Your trips">
            <div className="flex flex-col gap-3 px-4 pb-5">
              <LiveLine />
              <MyTruck />
              <RecentTrips onOpen={openRecent} />
              <DemoLink onDemo={demo} />
            </div>
          </Sheet>
        )}
        {!loading && view === "form" && (
          <Sheet label="Plan a trip" up onUp={(up) => !up && cancelForm()}>
            <div className="px-4 pb-6">{form}</div>
          </Sheet>
        )}
        {trip && route && (
          <Sheet label="The answer" up={panel !== null} onUp={(up) => openPanel(up ? "stops" : null)}>
            {panel ? (
              <Details trip={trip} route={route} modal={false} />
            ) : (
              <div ref={routeList} className="flex flex-col gap-3.5 px-4 pb-5">
                <DemoNote trip={trip} />
                <Verdict trip={trip} />
                <RouteCards trip={trip} />
                {leaveLater}
                <WarningLink trip={trip} />
                <TimeSlider trip={trip} compact />
              </div>
            )}
          </Sheet>
        )}
      </div>
    );
  }

  const chipsLeft = GAP + (trip ? CARD_W : FORM_W) + GAP;
  return (
    <div className="relative h-full overflow-hidden bg-map text-ink">
      <div className="absolute inset-0">{map}</div>
      {!panel && <LayerChips trip={trip} className="absolute top-6 right-[88px] z-10 flex-wrap" style={{ left: chipsLeft }} />}
      <ThemeButton className="absolute top-6 right-6 z-10" />

      {!trip && (
        <aside
          className="absolute z-10 flex max-h-[calc(100%-48px)] flex-col gap-3.5 overflow-y-auto rounded-[14px] bg-surface p-[18px] shadow-float"
          style={{ top: GAP, left: GAP, width: FORM_W }}
        >
          {loading ? <p className="m-0 text-sm text-ink-2">Loading your trip…</p> : view === "form" ? form : (
            <>
              <Brand />
              {home}
            </>
          )}
        </aside>
      )}
      {view === "home" && !loading && (
        <div className="absolute bottom-6 left-6 z-10 rounded-full border border-rule bg-surface px-3.5 py-2 shadow-float">
          <LiveLine />
        </div>
      )}
      {plan.isPending && !trip && <Planning request={plan.variables} className="top-6 left-[calc(50%+200px)] w-[380px] -translate-x-1/2" />}

      {trip && !panel && (
        <>
          <section
            aria-label="Recommendation"
            className="absolute z-10 flex max-h-[calc(100%-48px)] flex-col gap-3.5 overflow-y-auto rounded-[14px] bg-surface p-[18px] shadow-float"
            style={{ top: GAP, left: GAP, width: CARD_W }}
          >
            {answer}
            <div ref={routeList} className="flex flex-col gap-3.5">
              <RouteList trip={trip} />
              {leaveLater}
              <WarningLink trip={trip} />
            </div>
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

function PhoneTitle() {
  return <p className="m-0 py-3 font-[Overpass] text-[17px] leading-none font-extrabold">Corridor</p>;
}
