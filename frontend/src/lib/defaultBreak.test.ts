import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/lib/api";
import { ensureDefaultBreak } from "@/lib/defaultBreak";
import { automationSettings, endRecordedReport, makeBreak } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      getBreaks: vi.fn(),
      getReport: vi.fn(),
      getAutomationSettings: vi.fn(),
      createBreak: vi.fn(),
    },
  };
});

const FRIDAY = "2026-10-09";
const SATURDAY = "2026-10-10";

beforeEach(() => {
  vi.mocked(api.getBreaks).mockResolvedValue([]);
  vi.mocked(api.getReport).mockResolvedValue(endRecordedReport);
  vi.mocked(api.getAutomationSettings).mockResolvedValue(automationSettings);
  vi.mocked(api.createBreak).mockReset();
});

describe("ensureDefaultBreak", () => {
  it("adds the default break on a weekday without breaks", async () => {
    await expect(ensureDefaultBreak(FRIDAY)).resolves.toBe(true);
    expect(api.createBreak).toHaveBeenCalledWith(FRIDAY, {
      start_at: "2026-10-09T03:00:00.000Z",
      end_at: "2026-10-09T04:00:00.000Z",
    });
  });

  it("does nothing on weekends", async () => {
    await expect(ensureDefaultBreak(SATURDAY)).resolves.toBe(false);
    expect(api.getBreaks).not.toHaveBeenCalledWith(SATURDAY);
    expect(api.createBreak).not.toHaveBeenCalled();
  });

  it("does nothing when a break already exists", async () => {
    vi.mocked(api.getBreaks).mockResolvedValue([makeBreak("b1", "2026-10-09T12:30:00+09:00", "2026-10-09T13:30:00+09:00")]);
    await expect(ensureDefaultBreak(FRIDAY)).resolves.toBe(false);
    expect(api.createBreak).not.toHaveBeenCalled();
  });

  it("does nothing on a leave day", async () => {
    vi.mocked(api.getReport).mockResolvedValue({ ...endRecordedReport, attendance_kind: "leave", attendance_source: "manual" });
    await expect(ensureDefaultBreak(FRIDAY)).resolves.toBe(false);
    expect(api.createBreak).not.toHaveBeenCalled();
  });

  it("propagates other errors", async () => {
    vi.mocked(api.createBreak).mockRejectedValue(new ApiError(500, "server error"));
    await expect(ensureDefaultBreak(FRIDAY)).rejects.toThrow("server error");
  });
});
