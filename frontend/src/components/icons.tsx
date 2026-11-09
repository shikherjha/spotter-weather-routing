// Inline stroke icons; they take the text colour unless noted.

export function WarnIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M7 1.5 L13 12.5 H1 Z" />
      <path d="M7 5.5 V8.5 M7 10.2 V10.8" />
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

/** Official-warning mark, always in the severe colour. */
export function AlertIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="var(--severe)" strokeWidth="1.6" className="shrink-0">
      <circle cx="8" cy="8" r="6.5" />
      <path d="M8 4.5 V8.5 M8 10.8 V11.4" />
    </svg>
  );
}

export function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" fill="none" stroke="var(--ink-2)" strokeWidth="1.6" className="shrink-0">
      <path d="M5 2.5 L9.5 7 L5 11.5" />
    </svg>
  );
}

export function CloseIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M3 3 L13 13 M13 3 L3 13" />
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

export function CloudIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M4.5 12 A3 3 0 0 1 4.8 6 A4 4 0 0 1 12.5 7 A2.5 2.5 0 0 1 12 12 Z" />
    </svg>
  );
}

export function ThemeIcon({ dark }: { dark: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
      {dark ? (
        <path d="M8 3V1.5M8 14.5V13M3 8H1.5M14.5 8H13M4.5 4.5l-1-1M12.5 12.5l-1-1M4.5 11.5l-1 1M12.5 3.5l-1 1M10.5 8a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z" />
      ) : (
        <path d="M13 9.5A5.5 5.5 0 016.5 3a5.5 5.5 0 106.5 6.5z" />
      )}
    </svg>
  );
}

export function TruckIcon() {
  return (
    <svg width="22" height="16" viewBox="0 0 22 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" className="shrink-0">
      <rect x="1" y="2" width="13" height="9" rx="1" />
      <path d="M14 5 H18 L21 8.5 V11 H14" />
      <circle cx="5" cy="13" r="1.8" />
      <circle cx="17" cy="13" r="1.8" />
    </svg>
  );
}

export function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" className="shrink-0">
      <circle cx="8" cy="8" r="5.5" />
      <path d="M12 12 L16 16" />
    </svg>
  );
}

export function ClockIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" fill="none" stroke="var(--ink-2)" strokeWidth="1.5" className="shrink-0">
      <circle cx="9" cy="9" r="7" />
      <path d="M9 5 V9 L12 11" />
    </svg>
  );
}

export function BackIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M10 3 L5 8 L10 13" />
    </svg>
  );
}
