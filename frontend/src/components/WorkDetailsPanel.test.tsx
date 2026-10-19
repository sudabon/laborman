import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useCallback, useEffect, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkDetailsPanel } from "@/components/WorkDetailsPanel";
import { EMPTY_WORK_DETAILS } from "@/lib/mail";
import { createFakeApi } from "@/test/fakeApi";
import type { WorkDetails } from "@/types";

const holder = vi.hoisted(() => ({ fake: null as unknown as ReturnType<typeof import("@/test/fakeApi").createFakeApi> }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: new Proxy({}, { get: (_target, key: string) => (holder.fake.api as Record<string, unknown>)[key] }),
  };
});

const WORK_DATE = "2026-10-09";
const jst = (hhmm: string) => `${WORK_DATE}T${hhmm}:00+09:00`;

function Harness() {
  const { api } = holder.fake;
  const [details, setDetails] = useState<WorkDetails>(EMPTY_WORK_DETAILS);
  const refresh = useCallback(async () => {
    setDetails({
      tasks: await api.getTasks(),
      breaks: await api.getBreaks(),
      jobs: await api.getJobs(),
      salesItems: await api.getSalesItems(),
      workKinds: await api.getWorkKinds(),
      zacDefaults: await api.getZacTaskDefaults(),
    });
  }, [api]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return (
    <WorkDetailsPanel workDate={WORK_DATE} details={details} onChanged={refresh} />
  );
}

function bodyRows(): string[][] {
  const table = screen.getByRole("table");
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) =>
      within(row)
        .getAllByRole("cell")
        .slice(0, 5)
        // ジョブ列は 1 行目（ジョブ ID）だけを比べる。作業内容・売上項目は zacOf で確かめる
        .map((cell, index) => (index === 2 ? (cell.childNodes[0]?.textContent ?? "") : (cell.textContent ?? ""))),
    );
}

beforeEach(() => {
  holder.fake = createFakeApi(WORK_DATE);
  holder.fake.state.jobs = [holder.fake.job("JOB-A", "A社保守"), holder.fake.job("JOB-B", "社内業務")];
});

function taskForm() {
  return screen.getByRole("form", { name: "タスクを追加" });
}

function fillTask(values: { job?: string; description?: string; start?: string; end?: string }) {
  const form = taskForm();
  if (values.job !== undefined) {
    fireEvent.change(within(form).getByRole("combobox", { name: "ジョブ" }), { target: { value: values.job } });
  }
  if (values.description !== undefined) {
    fireEvent.change(within(form).getByLabelText("内容"), { target: { value: values.description } });
  }
  if (values.start !== undefined) fireEvent.change(within(form).getByLabelText("開始"), { target: { value: values.start } });
  if (values.end !== undefined) fireEvent.change(within(form).getByLabelText("終了"), { target: { value: values.end } });
}

describe("WorkDetailsPanel", () => {
  it("adds tasks by entering start and end times", async () => {
    render(<Harness />);
    await screen.findByText("まだ記録がありません");

    fillTask({ job: "JOB-A", description: "設計レビュー", start: "09:00", end: "10:30" });
    fireEvent.click(within(taskForm()).getByRole("button", { name: "追加" }));

    await waitFor(() => expect(bodyRows()).toEqual([["09:00", "10:30", "JOB-A", "設計レビュー", "1:30"]]));
    // 秒を持たない時刻で保存する
    expect(holder.fake.state.tasks[0].start_at).toBe("2026-10-09T00:00:00.000Z");
    expect(holder.fake.state.tasks[0].end_at).toBe("2026-10-09T01:30:00.000Z");
    // 次の開始に今回の終了を入れ、内容と終了は空にする
    expect(within(taskForm()).getByLabelText("開始")).toHaveValue("10:30");
    expect(within(taskForm()).getByLabelText("終了")).toHaveValue("");
    expect(within(taskForm()).getByLabelText("内容")).toHaveValue("");

    fillTask({ job: "JOB-B", description: "定例MTG", end: "25:15" });
    fireEvent.click(within(taskForm()).getByRole("button", { name: "追加" }));
    await waitFor(() => expect(bodyRows()[1]).toEqual(["10:30", "25:15", "JOB-B", "定例MTG", "14:45"]));
    expect(holder.fake.state.tasks[1].end_at).toBe("2026-10-09T16:15:00.000Z");
  });

  it("does not show stopwatch or break start buttons", async () => {
    render(<Harness />);
    await screen.findByText("まだ記録がありません");

    for (const name of ["タスク開始", "停止", "休憩開始", "休憩終了", /再開/, /既定の休憩を追加/]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("rejects an invalid time without calling the API", async () => {
    render(<Harness />);
    await screen.findByText("まだ記録がありません");

    fillTask({ job: "JOB-A", start: "9時", end: "10:00" });
    fireEvent.click(within(taskForm()).getByRole("button", { name: "追加" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("HH:MM 形式");
    expect(holder.fake.state.tasks).toHaveLength(0);
  });

  it("saves a task that overlaps a break without an error", async () => {
    await holder.fake.api.createBreak(WORK_DATE, { start_at: jst("12:00"), end_at: jst("13:00") });
    render(<Harness />);
    await waitFor(() => expect(bodyRows()).toHaveLength(1));

    fillTask({ job: "JOB-A", start: "11:30", end: "12:30" });
    fireEvent.click(within(taskForm()).getByRole("button", { name: "追加" }));

    await waitFor(() => expect(bodyRows()).toHaveLength(2));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("adds and edits a break", async () => {
    render(<Harness />);
    await screen.findByText("まだ記録がありません");

    fireEvent.click(screen.getByRole("button", { name: "休憩を追加" }));
    const form = screen.getByRole("group", { name: "休憩を追加" });
    fireEvent.change(within(form).getByLabelText("開始"), { target: { value: "12:00" } });
    fireEvent.change(within(form).getByLabelText("終了"), { target: { value: "13:00" } });
    fireEvent.click(within(form).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(bodyRows()).toEqual([["12:00", "13:00", "(休憩)", "", "1:00"]]));

    fireEvent.click(screen.getByRole("button", { name: "12:00 の休憩を編集" }));
    const edit = screen.getByRole("group", { name: "行を編集" });
    fireEvent.change(within(edit).getByLabelText("開始"), { target: { value: "12:30" } });
    fireEvent.change(within(edit).getByLabelText("終了"), { target: { value: "13:30" } });
    fireEvent.click(within(edit).getByRole("button", { name: "保存" }));

    await waitFor(() => expect(bodyRows()).toEqual([["12:30", "13:30", "(休憩)", "", "1:00"]]));
    expect(holder.fake.state.breaks).toHaveLength(1);
  });

  it("rejects 30:00 for a break without calling the API", async () => {
    render(<Harness />);
    await screen.findByText("まだ記録がありません");

    fireEvent.click(screen.getByRole("button", { name: "休憩を追加" }));
    const form = screen.getByRole("group", { name: "休憩を追加" });
    fireEvent.change(within(form).getByLabelText("開始"), { target: { value: "29:00" } });
    fireEvent.change(within(form).getByLabelText("終了"), { target: { value: "30:00" } });
    fireEvent.click(within(form).getByRole("button", { name: "保存" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("29:59 まで");
    expect(holder.fake.state.breaks).toHaveLength(0);
  });

  describe("zac の売上項目・作業内容", () => {
    const salesItem = (id: string, jobCode: string, name: string, validMonth: string | null, isClosed = false) => ({
      id,
      job_code: jobCode,
      name,
      valid_month: validMonth,
      is_closed: isClosed,
      is_active: true,
      sort_order: 0,
    });

    beforeEach(() => {
      const { state, job } = holder.fake;
      state.jobs = [
        { ...job("2602028", "エンジンファーム様"), zac_work_category: "プロジェクト作業" },
        { ...job("2602061", "bizoceanAPPs開発(26/09)"), series_name: "bizoceanAPPs開発", valid_month: "2026-09" },
        { ...job("2602062", "bizoceanAPPs開発(26/10)"), series_name: "bizoceanAPPs開発", valid_month: "2026-10" },
        job("2600901", "社内管理業務"),
      ];
      state.salesItems = [
        salesItem("ps-09", "2602028", "プロジェクトサポート（2026／09）", "2026-09", true),
        salesItem("ps-10", "2602028", "プロジェクトサポート（2026／10）", "2026-10"),
        salesItem("bz-10", "2602062", "bizoceanAPPs開発(26/10)", "2026-10"),
        salesItem("rd-1", "2600901", "社内管理業務", null),
        salesItem("rd-2", "2600901", "外部研修", null),
      ];
      state.workKinds = [
        { name: "プロジェクト作業", is_active: true, sort_order: 1 },
        { name: "プロジェクト関連打ち合わせ", is_active: true, sort_order: 2 },
      ];
      state.zacDefaults = [{ job_code: "2600901", work_kind: "プロジェクト関連打ち合わせ", sales_item_id: "rd-2" }];
    });

    const form = () => taskForm();
    const salesSelect = () => within(form()).getByLabelText("売上項目");
    const kindSelect = () => within(form()).getByLabelText("作業内容");

    it("fills defaults from the work month and the job, and saves them", async () => {
      render(<Harness />);
      await screen.findByText("まだ記録がありません");

      fillTask({ job: "2602028" });
      fireEvent.mouseDown(await screen.findByRole("option", { name: /2602028/ }));
      expect(salesSelect()).toHaveValue("ps-10");
      expect(kindSelect()).toHaveValue("プロジェクト作業");
      // 計上済みの項目は選べるが初期値にはならない
      expect(within(salesSelect()).getByRole("option", { name: "プロジェクトサポート（2026／09）（売上計上済）" })).toBeInTheDocument();

      fillTask({ description: "設計レビュー", start: "09:00", end: "10:00" });
      fireEvent.click(within(form()).getByRole("button", { name: "追加" }));

      await waitFor(() => expect(holder.fake.state.tasks).toHaveLength(1));
      expect(holder.fake.state.tasks[0]).toMatchObject({ job_code: "2602028", sales_item_id: "ps-10", work_kind: "プロジェクト作業" });
      expect(await screen.findByTestId("task-zac")).toHaveTextContent("プロジェクト作業 / プロジェクトサポート（2026／10）");
    });

    it("uses the last used values for a job with kind-of-work sales items", async () => {
      render(<Harness />);
      await screen.findByText("まだ記録がありません");

      fillTask({ job: "2600901" });
      fireEvent.mouseDown(await screen.findByRole("option", { name: /2600901/ }));
      expect(salesSelect()).toHaveValue("rd-2");
      expect(kindSelect()).toHaveValue("プロジェクト関連打ち合わせ");

      fireEvent.change(salesSelect(), { target: { value: "rd-1" } });
      fillTask({ start: "09:00", end: "10:00" });
      fireEvent.click(within(form()).getByRole("button", { name: "追加" }));
      await waitFor(() => expect(holder.fake.state.tasks[0]?.sales_item_id).toBe("rd-1"));
    });

    it("shows a monthly series as one candidate resolved by the work month", async () => {
      render(<Harness />);
      await screen.findByText("まだ記録がありません");

      fillTask({ job: "bizocean" });
      const options = await screen.findAllByRole("option", { name: /bizoceanAPPs開発/ });
      expect(options).toHaveLength(1);
      expect(options[0]).toHaveTextContent("2602062");
      // 候補は mousedown で選ぶ（入力欄の blur より先に確定させるため）
      fireEvent.mouseDown(options[0]);
      expect(salesSelect()).toHaveValue("bz-10");
    });

    it("does not save when the series has no job for the work month", async () => {
      holder.fake.state.jobs = holder.fake.state.jobs.filter((job) => job.code !== "2602062");
      render(<Harness />);
      await screen.findByText("まだ記録がありません");

      fillTask({ job: "bizocean" });
      const option = await screen.findByRole("option", { name: /2026-10 の案件が未登録/ });
      fireEvent.mouseDown(option);
      fillTask({ start: "09:00", end: "10:00" });
      fireEvent.click(within(form()).getByRole("button", { name: "追加" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("2026 年 10 月の bizoceanAPPs開発 の案件が未登録です");
      expect(holder.fake.state.tasks).toHaveLength(0);
    });
  });
});
