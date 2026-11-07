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

export function LevelChip({ level }: { level: Level | null }) {
  if (level === null) return <span className="text-xs text-ink-2">No forecast</span>;
  return <span className={`num inline-block min-w-16 rounded px-2 py-px text-center text-xs font-bold risk-${level}`}>{LEVEL_NAMES[level]}</span>;
}

/** A small block of a risk level's colour, sized by the caller. */
export function RiskSwatch({ level, className }: { level: number; className: string }) {
  return <span aria-hidden="true" className={`block risk-${level} ${className}`} />;
}
