// Truck size choices on the form, and how they read back.
export const HEIGHTS_FT = [12.5, 13, 13.5, 14, 14.5, 15];
export const DEFAULT_HEIGHT_FT = 13.5; // a standard US van trailer

export const feetInches = (ft: number) => `${Math.floor(ft)}′ ${Math.round((ft % 1) * 12)}″`;

/** "14′ 0″ tall · Hazmat", or "" for a standard truck. */
export function truckNote(heightFt: number, hazmat: boolean): string {
  const parts = [];
  if (heightFt !== DEFAULT_HEIGHT_FT) parts.push(`${feetInches(heightFt)} tall`);
  if (hazmat) parts.push("Hazmat");
  return parts.join(" · ");
}
