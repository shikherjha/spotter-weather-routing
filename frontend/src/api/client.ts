import type { ParsedTrip, Place, Trip, TripRequest } from "./types";

export class ApiError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.");
  }
  if (res.ok) return (await res.json()) as T;
  const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
  const detail = body?.detail;
  // Validation errors arrive as a list of field problems; show the first in plain words.
  if (Array.isArray(detail)) throw new ApiError(String(detail[0]?.msg ?? "Please check the trip details."));
  throw new ApiError(typeof detail === "string" ? detail : `Something went wrong (${res.status}).`);
}

export const planTrip = (req: TripRequest) =>
  call<Trip>("/trips", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(req) });

export const getTrip = (id: string) => call<Trip>(`/trips/${encodeURIComponent(id)}`);

export const searchPlaces = (q: string, signal?: AbortSignal) =>
  call<Place[]>(`/places?q=${encodeURIComponent(q)}`, { signal });

export const parseTrip = (text: string) =>
  call<ParsedTrip>("/parse", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text, tz: Intl.DateTimeFormat().resolvedOptions().timeZone }),
  });
