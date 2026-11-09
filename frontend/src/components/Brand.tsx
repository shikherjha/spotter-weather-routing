// The mark: a US route shield with the road running through it, kin to the route letters.

export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={(size * 30) / 26} viewBox="0 0 26 30" aria-hidden="true" className="shrink-0">
      <path d="M2 5 Q13 0 24 5 L24 15 Q24 25 13 29 Q2 25 2 15 Z" fill="var(--ink)" />
      <path d="M9 24 Q11 15 13 12 Q15 9 17 6" fill="none" stroke="var(--surface)" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <Mark size={26} />
      <span className="font-[Overpass] text-[22px] leading-none font-extrabold tracking-[0.2px]">Corridor</span>
      <span className="text-[13px] text-ink-2 max-sm:hidden">Weather-checked truck routes</span>
    </div>
  );
}
