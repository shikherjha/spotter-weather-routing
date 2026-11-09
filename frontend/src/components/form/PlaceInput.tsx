import { useEffect, useId, useRef, useState } from "react";

import { searchPlaces } from "../../api/client";
import type { Place } from "../../api/types";
import { SearchIcon } from "../icons";
import { fieldBg, fieldClass } from "./fields";

const SEARCH_DELAY_MS = 220;

/** Type-ahead place search (ARIA combobox). The parent only hears about places picked from the list. */
export function PlaceInput({
  label,
  value,
  onChange,
  placeholder,
  tinted = false,
  check = null,
  search = false,
  autoFocus = false,
}: {
  label: string;
  value: Place | null;
  onChange: (p: Place | null) => void;
  placeholder: string;
  tinted?: boolean;
  check?: string | null;
  /** The big "Where to?" box: label read out but not shown, a search icon, larger text. */
  search?: boolean;
  autoFocus?: boolean;
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
    }, SEARCH_DELAY_MS);
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
      <label htmlFor={id} className={search ? "sr-only" : "text-[13px] font-semibold"}>
        {label}
      </label>
      {search && (
        <span className="pointer-events-none absolute top-[17px] left-3.5 text-ink">
          <SearchIcon />
        </span>
      )}
      <input
        autoFocus={autoFocus}
        id={id}
        role="combobox"
        aria-expanded={open && options.length > 0}
        aria-controls={`${id}-list`}
        aria-activedescendant={open && options.length ? `${id}-opt-${active}` : undefined}
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
        className={
          search
            ? "h-[52px] w-full rounded-xl border-[1.5px] border-ink bg-surface pr-3 pl-11 text-[17px] text-ink placeholder:text-ink-2"
            : `${fieldClass} ${fieldBg(tinted)}`
        }
      />
      {check && <span className="text-xs font-semibold text-severe">{check}</span>}
      {open && options.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="absolute top-full z-20 m-0 mt-1 w-full list-none overflow-hidden rounded-lg border border-rule bg-surface p-1 shadow-float">
          {options.map((p, i) => (
            <li
              key={`${p.label}-${p.lat}`}
              id={`${id}-opt-${i}`}
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
