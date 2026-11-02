import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import { api } from "@/lib/api";
import { buildEndBodyCore } from "@/lib/mail";
import { automationSettings, endRecordedReport, jst, mailSettings, makeBreak, makeJob, makeTask } from "@/test/fixtures";
import type { WorkDetails } from "@/types";

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: { open: boolean; children: ReactNode }) =>
    open ? <div role="dialog">{children}</div> : null,
}));

const details: WorkDetails = {
  tasks: [
    makeTask("t1", "JOB-A", "設計レビュー", jst("09:00"), jst("10:30")),
    makeTask("t2", "JOB-B", "定例MTG", jst("10:30"), jst("12:00")),
  ],
  breaks: [makeBreak("b1", jst("12:00"), jst("13:00"))],
  jobs: [makeJob("JOB-A", "A社保守"), makeJob("JOB-B", "社内業務")],
  salesItems: [], workKinds: [], zacDefaults: [],
};

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      getSettings: vi.fn(async () => mailSettings),
      getReport: vi.fn(async () => endRecordedReport),
      getMonthReports: vi.fn(async () => []),
      getTasks: vi.fn(async () => details.tasks),
      getBreaks: vi.fn(async () => details.breaks),
      getJobs: vi.fn(async () => details.jobs),
      getSalesItems: vi.fn(async () => []),
      getWorkKinds: vi.fn(async () => []),
      getZacTaskDefaults: vi.fn(async () => []),
      getAutomationSettings: vi.fn(async () => automationSettings),
      createBreak: vi.fn(async () => details.breaks[0]),
      getZacDraft: vi.fn(async () => ({
        work_date: "2026-10-09",
        attendance: null,
        breaks: [],
        working_minutes: null,
        entry_style: "duration",
        entries: [],
        issues: [],
        registrable: false,
        auto_allowed: false,
        zac_registered_at: null,
      })),
      getZacRuns: vi.fn(async () => []),
      deleteTask: vi.fn(async () => undefined),
      updateReport: vi.fn(async () => endRecordedReport),
      markMailCreated: vi.fn(async () => ({ ...endRecordedReport, status: "end_mail_created" })),
    },
  };
});

describe("App end mail", () => {
  beforeEach(() => {
    // 「本日」をフィクスチャの勤務日にそろえる（タイマーは実時間のまま）
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(jst("18:30")));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("saves the rendered end body core (with {{tasks}}) as end_mail_body", async () => {
    vi.spyOn(window, "open").mockImplementation(() => null);
    render(<App />);

    const button = await screen.findByRole("button", { name: "Outlookで終業メールを作成" });
    await waitFor(() => expect(screen.getByLabelText("業務明細プレビュー")).toHaveValue(
      "09:00 - 10:30 JOB-A 設計レビュー\n10:30 - 12:00 JOB-B 定例MTG\n12:00 - 13:00 休憩",
    ));
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    fireEvent.click(await screen.findByRole("button", { name: "Outlook on the webを開く" }));

    const expected = buildEndBodyCore(mailSettings, endRecordedReport, details);
    expect(expected).toBe("勤務区分: リモート\n業務明細:\n09:00 - 10:30 JOB-A 設計レビュー\n10:30 - 12:00 JOB-B 定例MTG\n12:00 - 13:00 休憩");
    await waitFor(() =>
      expect(api.markMailCreated).toHaveBeenCalledWith(expect.any(String), { kind: "end", end_mail_body: expected }),
    );
  });
});

describe("App default break", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(jst("18:30")));
    vi.mocked(api.createBreak).mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(api.getBreaks).mockImplementation(async () => details.breaks);
  });

  it("adds the default break when a weekday without breaks is opened, but not after edits", async () => {
    vi.mocked(api.getBreaks).mockImplementation(async () => []);
    render(<App />);

    await waitFor(() => expect(api.createBreak).toHaveBeenCalledTimes(1));
    expect(api.createBreak).toHaveBeenCalledWith("2026-10-09", {
      start_at: "2026-10-09T03:00:00.000Z",
      end_at: "2026-10-09T04:00:00.000Z",
    });

    // 編集後の再取得では、休憩が 0 件のままでも追加しない
    const deleteButton = await screen.findByRole("button", { name: "09:00 のタスクを削除" });
    const callsBefore = vi.mocked(api.getBreaks).mock.calls.length;
    fireEvent.click(deleteButton);
    await waitFor(() => expect(api.deleteTask).toHaveBeenCalledWith("t1"));
    await waitFor(() => expect(vi.mocked(api.getBreaks).mock.calls.length).toBeGreaterThan(callsBefore));
    expect(api.createBreak).toHaveBeenCalledTimes(1);
  });

  it("does not add a break when one already exists", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "12:00 の休憩を編集" });
    expect(api.createBreak).not.toHaveBeenCalled();
  });
});

describe("App job list refresh", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(jst("18:30")));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(api.getJobs).mockImplementation(async () => details.jobs);
  });

  it("reloads jobs when the tab becomes visible again", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "12:00 の休憩を編集" });
    const callsBefore = vi.mocked(api.getJobs).mock.calls.length;

    // 別のタブや zac の選択肢の取り込みで追加されたジョブ
    vi.mocked(api.getJobs).mockImplementation(async () => [...details.jobs, makeJob("JOB-C", "新規案件")]);
    const visibility = vi.spyOn(document, "visibilityState", "get");
    visibility.mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    expect(api.getJobs).toHaveBeenCalledTimes(callsBefore);

    visibility.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    await waitFor(() => expect(vi.mocked(api.getJobs).mock.calls.length).toBeGreaterThan(callsBefore));
    visibility.mockRestore();
  });
});
