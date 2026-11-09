import { useId, useRef, type ReactNode } from "react";

const DRAG_PX = 40; // how far a drag must go to move the sheet

/**
 * The phone's bottom sheet: down shows the answer over the map, up fills the screen below the top bar.
 * Drag or tap the handle to move it; the content decides what each height shows.
 */
export function Sheet({
  up = false,
  onUp,
  label,
  children,
}: {
  up?: boolean;
  /** Leave out for a sheet that stays at its content's height. */
  onUp?: (up: boolean) => void;
  label: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section
      aria-label={label}
      className={`absolute inset-x-0 bottom-0 z-20 flex flex-col rounded-t-[18px] bg-surface shadow-[0_-4px_18px_rgb(0_0_0/0.14)] ${
        up ? "h-[calc(100%-76px)]" : "max-h-[50%]"
      }`}
    >
      {onUp ? (
        <Handle up={up} onUp={onUp} controls={id} />
      ) : (
        <span aria-hidden="true" className="mx-auto my-[11px] h-[5px] w-10 shrink-0 rounded-full bg-rule" />
      )}
      <div id={id} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {children}
      </div>
    </section>
  );
}

function Handle({ up, onUp, controls }: { up: boolean; onUp: (up: boolean) => void; controls: string }) {
  const start = useRef<number | null>(null);
  const dragged = useRef(false);
  return (
    <button
      type="button"
      aria-label="More details"
      aria-expanded={up}
      aria-controls={controls}
      onPointerDown={(e) => {
        start.current = e.clientY;
        dragged.current = false;
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerUp={(e) => {
        const from = start.current;
        start.current = null;
        if (from === null || Math.abs(e.clientY - from) < DRAG_PX) return;
        dragged.current = true;
        const wantUp = e.clientY < from;
        if (wantUp !== up) onUp(wantUp); // dragging further the way it already is does nothing
      }}
      // A tap (or Enter / Space) toggles; a drag has already been handled.
      onClick={() => {
        if (dragged.current) dragged.current = false;
        else onUp(!up);
      }}
      className="grid h-11 w-full shrink-0 touch-none place-items-center"
    >
      <span className="h-[5px] w-10 rounded-full bg-rule" />
    </button>
  );
}
