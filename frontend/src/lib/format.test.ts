import { describe, expect, it } from "vitest";

import { T0, checkpoint } from "../test/fixtures";
import { parseLoad } from "./load";
import { levelReason } from "./risk";
import { duration, relativeToNow, sameDay, when } from "./time";
import { truckNote } from "./truck";

describe("time", () => {
  it("names the zone of the place, not the viewer, including daylight time", () => {
    expect(when(T0, "America/Chicago")).toBe("Sat 12:00 PM CST");
    expect(when(T0, "America/Denver")).toBe("Sat 11:00 AM MST");
    expect(when(Date.UTC(2026, 9, 31, 17) / 1000, "America/Chicago")).toBe("Sat 12:00 PM CDT");
  });

  it("formats drive time as hours and minutes", () => {
    expect(duration(82_440)).toBe("22 h 54 m");
    expect(duration(1_800)).toBe("30 m");
  });

  it("describes a time against the real clock, so an old trip link doesn't say 'Now'", () => {
    expect(relativeToNow(T0, T0 + 600)).toBe("Now");
    expect(relativeToNow(T0, T0 + 50 * 60)).toBe("Now"); // 3:00 PM seen at 3:50 PM
    expect(relativeToNow(T0, T0 + 2 * 3600)).toBe("2 h ago");
    expect(relativeToNow(T0 + 12 * 3600, T0)).toBe("12 h from now");
    expect(relativeToNow(T0, T0 + 3 * 3600)).toBe("3 h ago");
  });

  it("compares calendar days in the given zone", () => {
    expect(sameDay(T0, T0 + 11 * 3600, "America/Chicago")).toBe(true); // 12 PM → 11 PM
    expect(sameDay(T0, T0 + 13 * 3600, "America/Chicago")).toBe(false); // → 1 AM next day
  });
});

describe("load", () => {
  it("reads pounds written several ways, and refuses anything else", () => {
    expect(parseLoad("42,000")).toBe(42000);
    expect(parseLoad("42000 lb")).toBe(42000);
    expect(parseLoad("42k")).toBe(42000);
    expect(parseLoad("42 tons")).toBeNaN();
  });
});

describe("level reasons", () => {
  it("explains a load-rule escalation in words", () => {
    expect(levelReason(checkpoint(0, 4, { drivers: ["wind"], load_escalated: true }))).toBe("Wind 45–54 mph, load over 30,000 lb");
    expect(levelReason(checkpoint(0, 3))).toBe("Snow 2–3 in/hr");
  });
});

describe("truck note", () => {
  it("says nothing for a standard truck and names what differs", () => {
    expect(truckNote(13.5, false)).toBe("");
    expect(truckNote(14, true)).toBe("14′ 0″ tall · Hazmat");
    expect(truckNote(12.5, false)).toBe("12′ 6″ tall");
  });
});
