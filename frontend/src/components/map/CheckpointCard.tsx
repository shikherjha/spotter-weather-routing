import type { Checkpoint, Trip } from "../../api/types";
import { LEVEL_NAMES, hazard, levelReason, mainReading } from "../../lib/risk";
import { duration, when } from "../../lib/time";
import { CloseIcon } from "../icons";
import { LevelChip } from "../ui";

/** The card that opens from a pin or checkpoint: when you'd be there, the reading, and why it got its level. */
export function CheckpointCard({
  trip,
  routeId,
  cp,
  onClose,
  onStops,
}: {
  trip: Trip;
  routeId: string;
  cp: Checkpoint;
  onClose: () => void;
  onStops: () => void;
}) {
  const reason = levelReason(cp);
  return (
    <div
      role="dialog"
      aria-label={`Route ${routeId}, mile ${Math.round(cp.mile)}`}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
      className="flex w-64 flex-col gap-2 p-3.5 font-sans text-ink"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[15px] font-bold">{cp.level ? hazard(cp) : (cp.place ?? `Mile ${Math.round(cp.mile)}`)}</span>
        <div className="flex items-center gap-1">
          <LevelChip level={cp.level} />
          <button type="button" aria-label="Close" onClick={onClose} className="grid size-8 place-items-center text-ink-2">
            <CloseIcon size={12} />
          </button>
        </div>
      </div>
      <p className="num m-0 text-sm leading-5">
        Route {routeId}, mile {Math.round(cp.mile)}
        {cp.place ? ` near ${cp.place}` : ""}. You'd be here <strong>{when(cp.eta, cp.tz)}</strong>, {duration(cp.eta - trip.departure)} after you
        leave.
      </p>
      <p className="num m-0 text-sm leading-5">{mainReading(cp)}.</p>
      {reason && cp.level !== null && (
        <p className="m-0 text-[13px] leading-5 text-ink-2">
          Why {LEVEL_NAMES[cp.level]}: {reason.toLowerCase()}.
        </p>
      )}
      <button type="button" onClick={onStops} className="self-start text-sm font-semibold text-accent">
        All stops on Route {routeId}
      </button>
    </div>
  );
}
