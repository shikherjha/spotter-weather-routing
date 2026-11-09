// Every clock time on screen carries its zone, because routes cross time zones.

export const HOUR = 3600;
const formatters = new Map<string, Intl.DateTimeFormat>();

function parts(epochS: number, tz: string) {
  let f = formatters.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    });
    formatters.set(tz, f);
  }
  const out: Record<string, string> = {};
  for (const p of f.formatToParts(new Date(epochS * 1000))) out[p.type] = p.value;
  return out;
}

/** "9:10 PM" */
export function clock(epochS: number, tz: string): string {
  const p = parts(epochS, tz);
  return `${p.hour}:${p.minute} ${p.dayPeriod}`;
}

/** "Sat 9:10 PM MST"; drop the day or zone with the flags. */
export function when(epochS: number, tz: string, opts: { day?: boolean; zone?: boolean } = {}): string {
  const { day = true, zone = true } = opts;
  const p = parts(epochS, tz);
  return [day ? p.weekday : null, `${p.hour}:${p.minute} ${p.dayPeriod}`, zone ? p.timeZoneName : null]
    .filter(Boolean)
    .join(" ");
}

/** "Sat, Nov 7, 12:00 PM CST" */
export function longWhen(epochS: number, tz: string): string {
  const p = parts(epochS, tz);
  return `${p.weekday}, ${p.month} ${p.day}, ${p.hour}:${p.minute} ${p.dayPeriod} ${p.timeZoneName}`;
}

/** "Sun 10 AM" style tick label */
export function tick(epochS: number, tz: string, withDay: boolean): string {
  const p = parts(epochS, tz);
  const t = p.minute === "00" ? `${p.hour} ${p.dayPeriod}` : `${p.hour}:${p.minute} ${p.dayPeriod}`;
  return withDay ? `${p.weekday} ${t}` : t;
}

export function zone(epochS: number, tz: string): string {
  return parts(epochS, tz).timeZoneName;
}

export function localHour(epochS: number, tz: string): number {
  const p = parts(epochS, tz);
  return (Number(p.hour) % 12) + (p.dayPeriod === "PM" ? 12 : 0);
}

/** "22 h 54 m" */
export function duration(seconds: number): string {
  const m = Math.round(seconds / 60);
  const h = Math.floor(m / 60);
  return h ? `${h} h ${m % 60} m` : `${m} m`;
}

/** "Now", "12 h from now" or "3 h ago": a trip opened from a link can be hours old. */
export function relativeToNow(epochS: number, nowS = Date.now() / 1000): string {
  const h = (epochS - nowS) / HOUR;
  if (h > -1 && h < 0.5) return "Now"; // the slider's hours start on the hour, so this hour is "now"
  return h > 0 ? `${Math.round(h)} h from now` : `${Math.round(-h)} h ago`;
}

export function sameDay(a: number, b: number, tz: string): boolean {
  const pa = parts(a, tz);
  const pb = parts(b, tz);
  return pa.month === pb.month && pa.day === pb.day;
}

/** Wall-clock "YYYY-MM-DDTHH:mm" in `tz`, for the API's departure_local and <input type=datetime-local>. */
export function localInput(epochS: number, tz: string): string {
  const f = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const p: Record<string, string> = {};
  for (const x of f.formatToParts(new Date(epochS * 1000))) p[x.type] = x.value;
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

/** The next whole hour, as a datetime-local value in `tz` (the browser's zone by default). */
export function nextHourInput(tz = Intl.DateTimeFormat().resolvedOptions().timeZone, now: Date = new Date()): string {
  return localInput((Math.floor(now.getTime() / 1000 / HOUR) + 1) * HOUR, tz);
}

/** "Mountain time" */
export function zoneName(epochS: number, tz: string): string {
  const f = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "long" });
  const name = f.formatToParts(new Date(epochS * 1000)).find((p) => p.type === "timeZoneName")?.value ?? tz;
  return name.replace(/ (Standard|Daylight) Time$/, " time");
}
