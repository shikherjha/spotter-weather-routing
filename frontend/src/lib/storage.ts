// Per-device memory (your truck, recent trips). Storage can be blocked, cleared or hold something
// unexpected; callers check the shape of what they read and fall back to defaults.
const PREFIX = "corridor:";

export function readJson(key: string): unknown {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as unknown) : undefined;
  } catch {
    return undefined;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Storage blocked: remembered for this visit only.
  }
}
