import type { Level } from "../api/types";
import { LEVEL_NAMES } from "../lib/risk";

/** Route letter in a US-highway shield. Blue = the route you picked. */
export function Shield({ id, on, size = 22, outlined = false }: { id: string; on: boolean; size?: number; outlined?: boolean }) {
  return (
    <svg width={size} height={(size * 30) / 26} viewBox="0 0 26 30" aria-hidden="true" className="shrink-0">
      <path
        d="M2 5 Q13 0 24 5 L24 15 Q24 25 13 29 Q2 25 2 15 Z"
        fill={on ? "var(--accent)" : "var(--alt)"}
        stroke={outlined ? "var(--surface)" : "none"}
        strokeWidth={2}
      />
      <text x="13" y="20" textAnchor="middle" fontSize="14" fill="#fff" className="shield-text">
        {id}
      </text>
    </svg>
  );
}

const CHIP_TEXT = ["#15191E", "#15191E", "#15191E", "#FFFFFF", "#FFFFFF"];

export function LevelChip({ level }: { level: Level | null }) {
  if (level === null) return <span className="text-xs text-ink-2">No forecast</span>;
  return (
    <span
      className={`num inline-block min-w-16 rounded px-2 py-px text-center text-xs font-bold risk-${level}`}
      style={{ background: level < 4 ? `var(--risk-${level})` : undefined, color: CHIP_TEXT[level] }}
    >
      {LEVEL_NAMES[level]}
    </span>
  );
}

export function WarnIcon({ className = "" }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" className={className}>
      <path d="M7 1.5 L13 12.5 H1 Z" />
      <path d="M7 5.5 V8.5 M7 10.2 V10.8" />
    </svg>
  );
}

export function AlertIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="var(--severe)" strokeWidth="1.6" className="shrink-0">
      <circle cx="8" cy="8" r="6.5" />
      <path d="M8 4.5 V8.5 M8 10.8 V11.4" />
    </svg>
  );
}

export function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="7" cy="7" r="5.8" />
      <path d="M4.5 7.2 L6.3 9 L9.6 5.4" />
    </svg>
  );
}

export function PlayIcon({ playing }: { playing: boolean }) {
  return playing ? (
    <svg width="14" height="14" viewBox="0 0 10 10" aria-hidden="true">
      <path d="M2 1 H4 V9 H2 Z M6 1 H8 V9 H6 Z" fill="currentColor" />
    </svg>
  ) : (
    <svg width="14" height="14" viewBox="0 0 10 10" aria-hidden="true">
      <path d="M2.5 1 L9 5 L2.5 9 Z" fill="currentColor" />
    </svg>
  );
}

export function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M3 3 L13 13 M13 3 L3 13" />
    </svg>
  );
}
