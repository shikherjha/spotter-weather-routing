import { useId, useState } from "react";

import { parseLoad } from "../../lib/load";
import { HEIGHTS_FT, feetInches, truckSummary } from "../../lib/truck";
import { TruckIcon } from "../icons";
import { fieldBg, fieldClass } from "./fields";

export interface TruckFields {
  load: string; // as typed: "42000", "42k"
  heightFt: number;
  hazmat: boolean;
}

/** "My truck · 13′ 6″ · 42,000 lb · no hazmat", opening into its three fields. */
export function TruckPill({
  value,
  onChange,
  tinted = false,
  startOpen = false,
}: {
  value: TruckFields;
  onChange: (v: TruckFields) => void;
  tinted?: boolean;
  startOpen?: boolean;
}) {
  const [open, setOpen] = useState(startOpen);
  const id = useId();
  const load = parseLoad(value.load);
  const summary = truckSummary({ load_lb: Number.isFinite(load) ? load : 0, height_ft: value.heightFt, hazmat: value.hazmat });

  return (
    <div className={`flex flex-col rounded-[10px] ${tinted ? "bg-accent/10" : "bg-tint"}`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="flex min-h-11 items-center gap-2.5 px-3 text-left"
      >
        <TruckIcon />
        <span className="num min-w-0 flex-1 text-sm">
          <strong>My truck</strong> <span className="text-ink-2">· {Number.isFinite(load) ? summary : "set the load"}</span>
        </span>
        <span className="text-[13px] font-semibold text-accent">{open ? "Done" : "Change"}</span>
      </button>
      {open && (
        <div id={id} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-2.5 px-3 pb-3">
          <label className="flex flex-col gap-1">
            <span className="text-[13px] font-semibold">Load weight</span>
            <span className="relative">
              <input
                inputMode="decimal"
                value={value.load}
                onChange={(e) => onChange({ ...value, load: e.target.value })}
                className={`num ${fieldClass} pr-9 ${fieldBg(false)}`}
              />
              <span className="absolute top-3 right-3 text-sm text-ink-2">lb</span>
            </span>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[13px] font-semibold">Height</span>
            <select
              value={value.heightFt}
              onChange={(e) => onChange({ ...value, heightFt: Number(e.target.value) })}
              className={`num ${fieldClass} px-2 ${fieldBg(false)}`}
            >
              {HEIGHTS_FT.map((h) => (
                <option key={h} value={h}>
                  {feetInches(h)}
                </option>
              ))}
            </select>
          </label>
          <label className="col-span-2 flex min-h-11 items-center gap-2.5">
            <input
              type="checkbox"
              checked={value.hazmat}
              onChange={(e) => onChange({ ...value, hazmat: e.target.checked })}
              className="size-5 accent-[var(--accent)]"
            />
            <span className="text-sm">Hazmat load</span>
          </label>
          <p className="col-span-2 m-0 text-xs leading-[17px] text-ink-2">
            Kept on this device. Routes stay off roads with lower bridges, weight limits or hazmat bans; loads over 30,000 lb
            hit wind limits sooner.
          </p>
        </div>
      )}
    </div>
  );
}
