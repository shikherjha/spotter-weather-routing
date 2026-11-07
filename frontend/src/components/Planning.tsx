import type { TripRequest } from "../api/types";
import { cityName } from "../lib/route";

/** Shown over the map while a trip is being planned. */
export function Planning({ request }: { request: TripRequest | undefined }) {
  return (
    <section
      aria-live="polite"
      className="absolute top-6 left-[calc(50%+200px)] z-20 w-[380px] -translate-x-1/2 rounded-xl bg-surface p-4 shadow-float"
    >
      <p className="m-0 text-base font-bold">
        Planning {request ? `${cityName(request.origin.label)} → ${cityName(request.destination.label)}` : "your trip"}
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
