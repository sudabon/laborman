import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TodayReport } from "@/components/TodayReport";
import { api } from "@/lib/api";
import { endRecordedReport, jst, mailSettings, makeBreak, makeJob, makeTask } from "@/test/fixtures";
import type { WorkDetails, WorkReport } from "@/types";

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: { open: boolean; children: ReactNode }) =>
    open ? <div role="dialog">{children}</div> : null,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      stopTask: vi.fn(),
      stopBreak: vi.fn(),
      getZacDraft: vi.fn(() => new Promise(() => {})),
      getZacRuns: vi.fn(() => new Promise(() => {})),
    },
  };
});

const startedReport: WorkReport = { ...endRecordedReport, end_time: null, status: "start_mail_created", work_duration_minutes: null };

const finishedDetails: WorkDetails = {
  tasks: [
    makeTask("t2", "JOB-B", "定例MTG", jst("10:30"), jst("12:00")),
    makeTask("t1", "JOB-A", "設計レビュー", jst("09:00"), jst("10:30")),
  ],
  breaks: [makeBreak("b1", jst("12:00"), jst("13:00"))],
  jobs: [makeJob("JOB-A", "A社保守"), makeJob("JOB-B", "社内業務")],
  salesItems: [], workKinds: [], zacDefaults: [],
};

const runningDetails: WorkDetails = {
  ...finishedDetails,
  tasks: [...finishedDetails.tasks, makeTask("t3", "JOB-A", "障害調査", jst("13:00"), null)],
};

function renderReport(details: WorkDetails, overrides: Partial<Parameters<typeof TodayReport>[0]> = {}) {
  const events: string[] = [];
  const props = {
    date: new Date(2026, 9, 9),
    report: startedReport,
    settings: mailSettings,
    details,
    onDetailsChanged: vi.fn(async () => {
      events.push("refresh");
    }),
    sentConfirmations: {},
    onSaveReport: vi.fn(async () => {}),
    onRecordStart: vi.fn(async () => {}),
    onRecordEnd: vi.fn(async () => {
      events.push("record-end");
    }),
    onSaveAttendance: vi.fn(async () => {}),
    onZacRunFinished: vi.fn(async () => {}),
    onCreateMail: vi.fn(async () => {}),
    onToggleConfirmation: vi.fn(),
    onOpenSettings: vi.fn(),
    ...overrides,
  };
  render(<TodayReport {...props} />);
  return { props, events };
}

beforeEach(() => {
  vi.mocked(api.stopTask).mockReset();
  vi.mocked(api.stopBreak).mockReset();
});

describe("TodayReport", () => {
  it("replaces the free-text business report with a read-only tasks preview", async () => {
    const writeText = vi.fn(async () => {});
    Object.assign(navigator, { clipboard: { writeText } });
    renderReport(finishedDetails);

    expect(screen.queryByLabelText("業務報告")).not.toBeInTheDocument();
    const preview = screen.getByLabelText("業務明細プレビュー");
    expect(preview).toHaveAttribute("readonly");
    expect(preview).toHaveValue("09:00 - 10:30 JOB-A 設計レビュー\n10:30 - 12:00 JOB-B 定例MTG\n12:00 - 13:00 休憩");

    fireEvent.click(screen.getByRole("button", { name: "コピー" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("09:00 - 10:30 JOB-A 設計レビュー\n10:30 - 12:00 JOB-B 定例MTG\n12:00 - 13:00 休憩"));
  });

  it("records the end directly when nothing is running", async () => {
    const { props } = renderReport(finishedDetails);

    fireEvent.click(screen.getByRole("button", { name: "終業を記録" }));

    await waitFor(() => expect(props.onRecordEnd).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.stopTask).not.toHaveBeenCalled();
  });

  it("stops the running task before recording the end when confirmed", async () => {
    vi.mocked(api.stopTask).mockImplementation(async () => {
      events.push("stop-task");
      return runningDetails.tasks[2];
    });
    const { props, events } = renderReport(runningDetails);

    fireEvent.click(screen.getByRole("button", { name: "終業を記録" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("進行中のタスクを終業時刻で終了しますか？");
    expect(props.onRecordEnd).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "終了して終業を記録" }));

    await waitFor(() => expect(events).toEqual(["stop-task", "refresh", "record-end"]));
    expect(api.stopTask).toHaveBeenCalledWith("t3");
    expect(props.onRecordEnd).toHaveBeenCalledWith({ note: "", work_style: "remote" });
  });

  it("stops a running break when confirmed", async () => {
    const details = { ...finishedDetails, breaks: [makeBreak("b2", jst("15:00"), null)] };
    const { props } = renderReport(details);

    fireEvent.click(screen.getByRole("button", { name: "終業を記録" }));
    fireEvent.click(screen.getByRole("button", { name: "終了して終業を記録" }));

    await waitFor(() => expect(props.onRecordEnd).toHaveBeenCalledTimes(1));
    expect(api.stopBreak).toHaveBeenCalledWith("b2");
  });

  it("changes nothing when the confirmation is cancelled", () => {
    const { props } = renderReport(runningDetails);

    fireEvent.click(screen.getByRole("button", { name: "終業を記録" }));
    fireEvent.click(screen.getByRole("button", { name: "取り消す" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.stopTask).not.toHaveBeenCalled();
    expect(props.onRecordEnd).not.toHaveBeenCalled();
    expect(props.onDetailsChanged).not.toHaveBeenCalled();
  });

  it("shows attendance as 未取込 separately from the punch times", () => {
    renderReport(finishedDetails);

    expect(screen.getByTestId("attendance-summary")).toHaveTextContent("未取込");
    expect(screen.getByText("始業時刻（打刻）")).toBeInTheDocument();
  });

  it("shows imported attendance with its source and import time", () => {
    renderReport(finishedDetails, {
      report: {
        ...startedReport,
        attendance_start_at: jst("08:29"),
        attendance_end_at: jst("18:38"),
        attendance_source: "hr_mail",
        attendance_imported_at: "2026-10-13T09:20:00+09:00",
      },
    });

    expect(screen.getByTestId("attendance-summary")).toHaveTextContent("08:29 – 18:38");
    expect(screen.getByText("人事メール・取込 10/13 09:20")).toBeInTheDocument();
  });

  it("shows 休暇 for a leave day", () => {
    renderReport(finishedDetails, {
      report: { ...startedReport, attendance_kind: "leave", attendance_source: "manual" },
    });

    expect(screen.getByTestId("attendance-summary")).toHaveTextContent("休暇");
    expect(screen.getByText("手入力", { selector: "p" })).toBeInTheDocument();
  });

  it("saves manually entered attendance with source manual", async () => {
    const { props } = renderReport(finishedDetails);

    fireEvent.click(screen.getByRole("button", { name: "手入力" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("出勤"), { target: { value: "09:00" } });
    fireEvent.change(within(dialog).getByLabelText("退勤"), { target: { value: "18:30" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));

    await waitFor(() =>
      expect(props.onSaveAttendance).toHaveBeenCalledWith({
        start_at: new Date(jst("09:00")).toISOString(),
        end_at: new Date(jst("18:30")).toISOString(),
        source: "manual",
        kind: "work",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("saves a leave day without times", async () => {
    const { props } = renderReport(finishedDetails);

    fireEvent.click(screen.getByRole("button", { name: "手入力" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByLabelText("休暇"));
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));

    await waitFor(() =>
      expect(props.onSaveAttendance).toHaveBeenCalledWith({ start_at: null, end_at: null, source: "manual", kind: "leave" }),
    );
  });

  it("requires both times for a work day", async () => {
    const { props } = renderReport(finishedDetails);

    fireEvent.click(screen.getByRole("button", { name: "手入力" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("出勤"), { target: { value: "09:00" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("出勤・退勤を入力してください");
    expect(props.onSaveAttendance).not.toHaveBeenCalled();
  });
});
