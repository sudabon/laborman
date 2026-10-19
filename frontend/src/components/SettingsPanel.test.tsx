import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SettingsPanel } from "@/components/SettingsPanel";
import { automationSettings as baseAutomationSettings, mailSettings, makeJob } from "@/test/fixtures";
import type { AutomationSettings, Job } from "@/types";

const automationSettings: AutomationSettings = { ...baseAutomationSettings, hr_mail_subject_keyword: "[勤怠情報]" };

function renderPanel(current: AutomationSettings = automationSettings, jobs: Job[] = []) {
  const onSaveAutomationSettings = vi.fn(async () => {});
  const props = {
    settings: mailSettings,
    onSave: vi.fn(async () => {}),
    jobs,
    onCreateJob: vi.fn(),
    onUpdateJob: vi.fn(async (code: string) => makeJob(code, "")),
    onChangeJobCode: vi.fn(async (_code: string, payload: { code: string }) => makeJob(payload.code, "")),
    salesItems: [
      {
        id: "ps-10",
        job_code: "JOB-B",
        name: "社内業務（2026／10）",
        valid_month: "2026-10",
        is_closed: false,
        is_active: true,
        sort_order: 1,
      },
    ],
    workKinds: [
      { name: "プロジェクト作業", is_active: true, sort_order: 1 },
      { name: "社内業務", is_active: true, sort_order: 2 },
    ],
    onCreateSalesItem: vi.fn(async () => {}),
    onUpdateSalesItem: vi.fn(async () => {}),
    onCreateWorkKind: vi.fn(async () => {}),
    onUpdateWorkKind: vi.fn(async () => {}),
    automationSettings: current,
    onSaveAutomationSettings,
  };
  const view = render(<SettingsPanel {...props} />);
  return { props, onSaveAutomationSettings, rerender: (next: AutomationSettings) => view.rerender(<SettingsPanel {...props} automationSettings={next} />) };
}

describe("SettingsPanel hr mail conditions", () => {
  it("loads and saves the subject keyword and sender with the current break settings", async () => {
    const { onSaveAutomationSettings } = renderPanel();

    expect(screen.getByLabelText("件名キーワード")).toHaveValue("[勤怠情報]");
    fireEvent.change(screen.getByLabelText("差出人（任意）"), { target: { value: "hr@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "人事メールの条件を保存" }));

    await waitFor(() =>
      expect(onSaveAutomationSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          default_break_start: "12:00",
          default_break_end: "13:00",
          hr_mail_from: "hr@example.com",
          hr_mail_subject_keyword: "[勤怠情報]",
          zac_submit_mode: "dry_run",
        }),
      ),
    );
  });

  it("keeps hr mail conditions when saving the default break", async () => {
    const { onSaveAutomationSettings } = renderPanel({ ...automationSettings, hr_mail_from: "hr@example.com" });

    fireEvent.change(screen.getByLabelText("開始"), { target: { value: "11:45" } });
    fireEvent.click(screen.getByRole("button", { name: "既定の休憩を保存" }));

    await waitFor(() =>
      expect(onSaveAutomationSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          default_break_start: "11:45",
          default_break_end: "13:00",
          hr_mail_from: "hr@example.com",
          hr_mail_subject_keyword: "[勤怠情報]",
        }),
      ),
    );
  });

  it("shows reloaded values", () => {
    const { rerender } = renderPanel();
    rerender({ ...automationSettings, hr_mail_subject_keyword: "[勤怠]", hr_mail_from: "new@example.com" });

    expect(screen.getByLabelText("件名キーワード")).toHaveValue("[勤怠]");
    expect(screen.getByLabelText("差出人（任意）")).toHaveValue("new@example.com");
  });
});

function rowButton(name: string): HTMLElement {
  const row = screen.getByLabelText("JOB-2610 のジョブ ID").closest("tr") as HTMLElement;
  return within(row).getByRole("button", { name });
}

describe("SettingsPanel job master", () => {
  const job: Job = { ...makeJob("JOB-2610", "A社保守"), zac_search_text: "A社 保守" };

  it("changes the job ID by creating a new job", async () => {
    const { props } = renderPanel(automationSettings, [job]);

    fireEvent.change(screen.getByLabelText("JOB-2610 のジョブ ID"), { target: { value: " JOB-2611 " } });
    fireEvent.click(rowButton("保存"));

    await waitFor(() =>
      expect(props.onChangeJobCode).toHaveBeenCalledWith("JOB-2610", {
        code: "JOB-2611",
        name: "A社保守",
        zac_search_text: "A社 保守",
        zac_work_category: "",
      }),
    );
    expect(props.onUpdateJob).not.toHaveBeenCalled();
    expect(await screen.findByText("JOB-2611 を作成し、JOB-2610 を無効にしました")).toBeInTheDocument();
  });

  it("updates other fields in place when the job ID is unchanged", async () => {
    const { props } = renderPanel(automationSettings, [job]);

    fireEvent.change(screen.getByLabelText("JOB-2610 の表示名"), { target: { value: "A社保守（改）" } });
    fireEvent.click(rowButton("保存"));

    await waitFor(() =>
      expect(props.onUpdateJob).toHaveBeenCalledWith("JOB-2610", {
        name: "A社保守（改）",
        zac_search_text: "A社 保守",
        zac_work_category: "",
        series_name: null,
        valid_month: null,
      }),
    );
    expect(props.onChangeJobCode).not.toHaveBeenCalled();
  });

  it("shows the error when the new job ID already exists", async () => {
    const { props } = renderPanel(automationSettings, [job]);
    props.onChangeJobCode.mockRejectedValueOnce(new Error("ジョブ ID JOB-2611 はすでに登録されています"));

    fireEvent.change(screen.getByLabelText("JOB-2610 のジョブ ID"), { target: { value: "JOB-2611" } });
    fireEvent.click(rowButton("保存"));

    expect(await screen.findByText("ジョブ ID JOB-2611 はすでに登録されています")).toBeInTheDocument();
  });
});

describe("SettingsPanel zac settings", () => {
  it("saves zac settings together with the other automation settings", async () => {
    const jobs = [makeJob("JOB-A", "A社保守"), makeJob("JOB-B", "社内業務")];
    const { onSaveAutomationSettings } = renderPanel(automationSettings, jobs);

    fireEvent.change(screen.getByLabelText("実行モード"), { target: { value: "assist" } });
    fireEvent.change(screen.getByLabelText("入力形式"), { target: { value: "time_range" } });
    fireEvent.change(screen.getByLabelText("丸め単位（分）"), { target: { value: "30" } });
    fireEvent.change(screen.getByLabelText("空き時間の扱い"), { target: { value: "assign_default_job" } });
    fireEvent.change(screen.getByLabelText("既定ジョブ"), { target: { value: "JOB-B" } });
    fireEvent.change(screen.getByLabelText("空き時間の作業内容"), { target: { value: "社内業務" } });
    fireEvent.change(screen.getByLabelText("空き時間の売上項目"), { target: { value: "ps-10" } });
    fireEvent.click(screen.getByRole("button", { name: "zac 連携の設定を保存" }));

    await waitFor(() =>
      expect(onSaveAutomationSettings).toHaveBeenCalledWith({
        default_break_start: "12:00",
        default_break_end: "13:00",
        hr_mail_from: "",
        hr_mail_subject_keyword: "[勤怠情報]",
        zac_submit_mode: "assist",
        entry_style: "time_range",
        time_unit_minutes: 30,
        clip_tolerance_minutes: 15,
        gap_policy: "assign_default_job",
        default_job_code: "JOB-B",
        default_work_kind: "社内業務",
        default_sales_item_id: "ps-10",
        description_max_length: 100,
      }),
    );
  });

  it("shows reloaded zac settings", () => {
    const { rerender } = renderPanel();
    rerender({ ...automationSettings, zac_submit_mode: "auto", time_unit_minutes: 5 });

    expect(screen.getByLabelText("実行モード")).toHaveValue("auto");
    expect(screen.getByLabelText("丸め単位（分）")).toHaveValue("5");
  });
});

describe("SettingsPanel zac masters", () => {
  it("edits series and month of a job", async () => {
    const { props } = renderPanel(automationSettings, [makeJob("2602062", "bizoceanAPPs開発(26/10)")]);

    fireEvent.change(screen.getByLabelText("2602062 のシリーズ名"), { target: { value: "bizoceanAPPs開発" } });
    fireEvent.change(screen.getByLabelText("2602062 の対象年月"), { target: { value: "2026-10" } });
    const row = screen.getByLabelText("2602062 のジョブ ID").closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "保存" }));

    await waitFor(() =>
      expect(props.onUpdateJob).toHaveBeenCalledWith(
        "2602062",
        expect.objectContaining({ series_name: "bizoceanAPPs開発", valid_month: "2026-10" }),
      ),
    );
  });

  it("lists, adds and disables sales items of a job", async () => {
    const { props } = renderPanel(automationSettings, [makeJob("JOB-B", "社内業務")]);

    fireEvent.click(screen.getByRole("button", { name: "売上項目（1）" }));
    const group = screen.getByRole("group", { name: "JOB-B の売上項目" });
    expect(group).toHaveTextContent("社内業務（2026／10）");
    expect(group).toHaveTextContent("2026-10");

    fireEvent.change(within(group).getByLabelText("JOB-B に追加する売上項目"), { target: { value: " 社内業務（2026／11） " } });
    fireEvent.click(within(group).getByRole("button", { name: "売上項目を追加" }));
    await waitFor(() => expect(props.onCreateSalesItem).toHaveBeenCalledWith("JOB-B", "社内業務（2026／11）"));

    fireEvent.click(within(group).getByRole("button", { name: "無効にする" }));
    await waitFor(() => expect(props.onUpdateSalesItem).toHaveBeenCalledWith("ps-10", { is_active: false }));
  });

  it("adds and toggles work kinds", async () => {
    const { props } = renderPanel();

    fireEvent.change(screen.getByLabelText("追加する作業内容"), { target: { value: "研修等" } });
    fireEvent.click(screen.getByRole("button", { name: "作業内容を追加" }));
    await waitFor(() => expect(props.onCreateWorkKind).toHaveBeenCalledWith("研修等"));

    fireEvent.click(screen.getByRole("button", { name: "社内業務（有効）" }));
    await waitFor(() => expect(props.onUpdateWorkKind).toHaveBeenCalledWith("社内業務", { is_active: false }));
  });
});

