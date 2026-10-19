import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportCalendar } from "@/components/ReportCalendar";
import { endRecordedReport } from "@/test/fixtures";
import type { WorkReport } from "@/types";

function report(workDate: string, overrides: Partial<WorkReport> = {}): WorkReport {
  return { ...endRecordedReport, id: workDate, work_date: workDate, status: "end_mail_created", ...overrides };
}

function dayButton(day: number): HTMLElement {
  return screen.getByRole("button", { name: new RegExp(`^2026/10/${day} `) });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 13, 10, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ReportCalendar zac status", () => {
  it("shows zac済 / 要対応 and highlights past weekdays not registered in zac", () => {
    render(
      <ReportCalendar
        month={new Date(2026, 9, 1)}
        selectedDate={new Date(2026, 9, 13)}
        reports={[
          report("2026-10-06", { zac_registered_at: "2026-10-07T00:20:00Z", zac_status: "registered" }),
          report("2026-10-07", { zac_status: "needs_action" }),
          report("2026-10-08"),
          report("2026-10-09", { attendance_kind: "leave", attendance_source: "manual" }),
        ]}
        onMonthChange={vi.fn()}
        onSelectDate={vi.fn()}
        onOpenToday={vi.fn()}
      />,
    );

    expect(dayButton(6)).toHaveTextContent("zac済");
    expect(dayButton(6).className).not.toContain("border-accent ");
    expect(dayButton(7)).toHaveTextContent("要対応");
    // 終業メール作成済みでも zac 未登録の過去の平日は強調する
    expect(dayButton(8)).toHaveTextContent("zac未登録");
    expect(dayButton(8).className).toContain("border-accent");
    // 休暇の日は zac 未登録として扱わない
    expect(dayButton(9)).not.toHaveTextContent("zac");
    // 未来の日・土日は表示しない
    expect(dayButton(14)).not.toHaveTextContent("zac");
    expect(dayButton(10)).not.toHaveTextContent("zac");
  });
});
