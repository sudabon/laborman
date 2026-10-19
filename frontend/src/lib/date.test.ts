import { describe, expect, it } from "vitest";

import { formatWorkTime, parseWorkTime, workMinutesBetween } from "./date";

const workDate = "2026-10-09";

describe("parseWorkTime", () => {
  it.each([
    ["09:00", "2026-10-09T00:00:00.000Z"],
    ["9:05", "2026-10-09T00:05:00.000Z"],
    ["00:00", "2026-10-08T15:00:00.000Z"],
    ["24:00", "2026-10-09T15:00:00.000Z"],
    ["25:15", "2026-10-09T16:15:00.000Z"],
    ["29:59", "2026-10-09T20:59:00.000Z"],
  ])("treats %s as a time on the work date (Asia/Tokyo)", (input, expected) => {
    expect(parseWorkTime(workDate, input)).toBe(expected);
  });

  it("rejects 30:00 and later", () => {
    expect(() => parseWorkTime(workDate, "30:00")).toThrow();
    expect(() => parseWorkTime(workDate, "31:10")).toThrow();
  });

  it.each(["", "9", "0900", "09:60", "09:5", "ab:cd", "-1:00", "09:00:00"])("rejects invalid format %j", (input) => {
    expect(() => parseWorkTime(workDate, input)).toThrow();
  });
});

describe("formatWorkTime", () => {
  it("formats times on the work date as HH:MM", () => {
    expect(formatWorkTime(workDate, "2026-10-09T00:00:00Z")).toBe("09:00");
    expect(formatWorkTime(workDate, "2026-10-08T15:00:00Z")).toBe("00:00");
  });

  it("formats times after midnight with 24+ hours", () => {
    expect(formatWorkTime(workDate, "2026-10-09T15:00:00Z")).toBe("24:00");
    expect(formatWorkTime(workDate, "2026-10-09T16:15:00+00:00")).toBe("25:15");
    expect(formatWorkTime(workDate, "2026-10-10T01:15:00+09:00")).toBe("25:15");
  });

  it("round-trips with parseWorkTime", () => {
    for (const value of ["00:00", "09:30", "23:59", "24:00", "29:59"]) {
      expect(formatWorkTime(workDate, parseWorkTime(workDate, value))).toBe(value);
    }
  });

  it("truncates seconds", () => {
    expect(formatWorkTime(workDate, "2026-10-09T00:00:59Z")).toBe("09:00");
  });
});

describe("workMinutesBetween", () => {
  it("counts whole minutes as displayed", () => {
    expect(workMinutesBetween("2026-10-09T00:00:40Z", "2026-10-09T01:30:10Z")).toBe(90);
  });
});
