import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ZAC_RUN_POLL_MS, ZacPanel } from "@/components/ZacPanel";
import { api, ApiError } from "@/lib/api";
import type { ZacDraft, ZacSyncRun } from "@/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      getZacDraft: vi.fn(),
      getZacRuns: vi.fn(),
      requestZacRun: vi.fn(),
      cancelZacRun: vi.fn(),
    },
  };
});

const WORK_DATE = "2026-10-09";

// 仕様書 §4.6 のレスポンス例
const specDraft: ZacDraft = {
  work_date: WORK_DATE,
  attendance: { start: "09:02", end: "18:41", source: "hr_mail" },
  breaks: [{ start: "12:00", end: "13:00" }],
  working_minutes: 519,
  entry_style: "duration",
  entries: [
    {
      job_code: "2602028",
      zac_search_text: "2602028",
      project_name: "エンジンファーム様",
      work_kind: "プロジェクト作業",
      sales_item: "プロジェクトサポート（2026／10）",
      minutes: 300,
      description: "- 設計レビュー\n- 障害調査",
      start: null,
      end: null,
    },
    {
      job_code: "2601570",
      zac_search_text: "2601570",
      project_name: "make.AI 業務",
      work_kind: "プロジェクト関連打ち合わせ",
      sales_item: "サービス開発本部 make.AI 業務",
      minutes: 210,
      description: "- 定例MTG",
      start: null,
      end: null,
    },
  ],
  issues: [
    { code: "TASK_OUTSIDE_ATTENDANCE", severity: "warning", message: "09:00開始のタスクを出勤時刻09:02に切り詰めました", ref_id: "t1" },
  ],
  registrable: true,
  auto_allowed: false,
  zac_registered_at: null,
};

function run(overrides: Partial<ZacSyncRun>): ZacSyncRun {
  return {
    id: "run-1",
    work_date: WORK_DATE,
    mode: "dry_run",
    status: "dry_run_done",
    entries: null,
    message: null,
    screenshot_path: null,
    agent_version: "0.1.0",
    started_at: "2026-10-13T00:21:00Z",
    finished_at: null,
    ...overrides,
  };
}

function renderPanel() {
  const onRunFinished = vi.fn(async () => {});
  render(<ZacPanel workDate={WORK_DATE} refreshKey="k" onRunFinished={onRunFinished} />);
  return { onRunFinished };
}

beforeEach(() => {
  vi.mocked(api.getZacDraft).mockReset().mockResolvedValue(specDraft);
  vi.mocked(api.getZacRuns).mockReset().mockResolvedValue([]);
  vi.mocked(api.requestZacRun).mockReset();
  vi.mocked(api.cancelZacRun).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ZacPanel", () => {
  it("shows the draft from the API with entries, working time and issues", async () => {
    vi.mocked(api.getZacRuns).mockResolvedValue([
      run({ status: "dry_run_done", screenshot_path: "/Users/me/Library/Logs/laborman-agent/screenshots/x.png" }),
    ]);
    renderPanel();

    expect(await screen.findByTestId("zac-summary")).toHaveTextContent(
      "出退勤 09:02–18:41 / 実働 8:39 / 入力 8:30 / 休憩 12:00–13:00",
    );
    const table = screen.getByRole("table", { name: "zac に入力する内容" });
    const rows = within(table).getAllByRole("row").slice(1).map((row) => row.textContent);
    expect(rows).toEqual([
      "プロジェクト作業2602028エンジンファーム様プロジェクトサポート（2026／10）5:00- 設計レビュー\n- 障害調査",
      "プロジェクト関連打ち合わせ2601570make.AI 業務サービス開発本部 make.AI 業務3:30- 定例MTG",
    ]);
    expect(screen.getByRole("list", { name: "検証結果" })).toHaveTextContent("09:00開始のタスクを出勤時刻09:02に切り詰めました");
    expect(screen.getByText(/警告があるため auto では保存せず/)).toBeInTheDocument();
    expect(screen.getByTestId("zac-latest-run")).toHaveTextContent("最終実行：10/13 09:21 dry_run・入力のみ（保存なし）");
    expect(screen.getByTestId("zac-latest-run")).toHaveTextContent("screenshots/x.png");
  });

  it("emphasizes BREAK_MISSING as stopping the registration", async () => {
    vi.mocked(api.getZacDraft).mockResolvedValue({
      ...specDraft,
      breaks: [],
      issues: [{ code: "BREAK_MISSING", severity: "error", message: "休憩が記録されていません", ref_id: null }],
      registrable: false,
    });
    renderPanel();

    const issues = await screen.findByRole("list", { name: "検証結果" });
    expect(issues).toHaveTextContent("zac 登録を中止しました。業務明細に休憩を記録してください。");
    expect(screen.getByText("エラーがあるため zac には保存しません。")).toBeInTheDocument();
  });

  it("explains that the request imports the HR mail when attendance is missing", async () => {
    vi.mocked(api.getZacDraft).mockResolvedValue({
      ...specDraft,
      attendance: null,
      entries: [],
      issues: [{ code: "ATTENDANCE_MISSING", severity: "error", message: "出退勤（人事メール）が未取込です", ref_id: null }],
      registrable: false,
    });
    renderPanel();

    expect(
      await screen.findByText("「この日を zac に登録」を押すと、人事メールから出退勤を取り込んでから zac に入力します。"),
    ).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "この日を zac に登録" })).toBeEnabled());
  });

  it("requests a run for the shown day and shows it as pending with a cancel action", async () => {
    vi.mocked(api.requestZacRun).mockImplementation(async () => {
      vi.mocked(api.getZacRuns).mockResolvedValue([run({ id: "req-1", status: "requested" })]);
      return run({ id: "req-1", status: "requested" });
    });
    vi.mocked(api.cancelZacRun).mockImplementation(async () => {
      vi.mocked(api.getZacRuns).mockResolvedValue([run({ id: "req-1", status: "cancelled" })]);
      return run({ id: "req-1", status: "cancelled" });
    });
    renderPanel();

    const button = await screen.findByRole("button", { name: "この日を zac に登録" });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    expect(await screen.findByRole("status")).toHaveTextContent("依頼中（10/13 09:21）");
    expect(api.requestZacRun).toHaveBeenCalledWith(WORK_DATE);
    expect(button).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "依頼を取り消す" }));
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(api.cancelZacRun).toHaveBeenCalledWith("req-1");
    expect(button).toBeEnabled();
  });

  it("shows a 409 conflict message", async () => {
    vi.mocked(api.requestZacRun).mockRejectedValue(new ApiError(409, "この日の zac 登録はすでに依頼中または実行中です"));
    renderPanel();

    const button = await screen.findByRole("button", { name: "この日を zac に登録" });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    expect(await screen.findByRole("alert")).toHaveTextContent("すでに依頼中または実行中です");
  });

  it("disables the request on a registered day", async () => {
    vi.mocked(api.getZacDraft).mockResolvedValue({ ...specDraft, zac_registered_at: "2026-10-13T00:22:00Z" });
    renderPanel();

    expect(await screen.findByText("zac に登録済みです（10/13 09:22）")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "この日を zac に登録" })).toBeDisabled();
  });

  it("polls while running and reports when the run finishes", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    vi.mocked(api.getZacRuns).mockResolvedValue([run({ status: "running" })]);
    const { onRunFinished } = renderPanel();
    expect(await screen.findByRole("status")).toHaveTextContent("実行中（10/13 09:21 開始）");

    vi.mocked(api.getZacRuns).mockResolvedValue([run({ status: "succeeded" })]);
    vi.mocked(api.getZacDraft).mockResolvedValue({ ...specDraft, zac_registered_at: "2026-10-13T00:22:00Z" });
    await act(async () => {
      vi.advanceTimersByTime(ZAC_RUN_POLL_MS);
    });

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(screen.getByTestId("zac-latest-run")).toHaveTextContent("保存完了");
    expect(onRunFinished).toHaveBeenCalledTimes(1);
  });
});
