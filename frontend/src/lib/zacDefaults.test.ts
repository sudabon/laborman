import { describe, expect, it } from "vitest";

import {
  collapseSeries,
  defaultSalesItemId,
  defaultWorkKind,
  unresolvedSeriesMessage,
} from "@/lib/zacDefaults";
import { makeJob } from "@/test/fixtures";
import type { Job, ZacSalesItem, ZacWorkKind } from "@/types";

const item = (id: string, jobCode: string, name: string, validMonth: string | null, isClosed = false): ZacSalesItem => ({
  id,
  job_code: jobCode,
  name,
  valid_month: validMonth,
  is_closed: isClosed,
  is_active: true,
  sort_order: 0,
});

const SALES: ZacSalesItem[] = [
  item("ps-09", "2602028", "プロジェクトサポート（2026／09）", "2026-09", true),
  item("ps-10", "2602028", "プロジェクトサポート（2026／10）", "2026-10"),
  item("ps-11", "2602028", "プロジェクトサポート（2026／11）", "2026-11"),
  item("rd-1", "2600901", "社内管理業務", null),
  item("rd-2", "2600901", "外部研修", null),
  item("ai", "2601570", "サービス開発本部 make.AI 業務", null),
  item("bz-10", "2602062", "bizoceanAPPs開発(26/10)", "2026-10"),
];

const series = (code: string, month: string): Job => ({
  ...makeJob(code, `bizoceanAPPs開発(${month.slice(2, 4)}/${month.slice(5)})`),
  series_name: "bizoceanAPPs開発",
  valid_month: month,
});

describe("collapseSeries", () => {
  const jobs = [series("2602061", "2026-09"), makeJob("2601570", "make.AI"), series("2602062", "2026-10")];

  it("keeps only the job for the work month in a series", () => {
    expect(collapseSeries(jobs, "2026-10-09").map((job) => job.code)).toEqual(["2602062", "2601570"]);
  });

  it("shows an unresolved candidate when the month is missing", () => {
    const collapsed = collapseSeries(jobs, "2026-12-01");
    expect(collapsed[0].code).toBe("series:bizoceanAPPs開発");
    expect(collapsed[0].name).toBe("bizoceanAPPs開発（2026-12 の案件が未登録）");
    expect(unresolvedSeriesMessage(collapsed[0].code, "2026-12-01")).toBe(
      "2026 年 12 月の bizoceanAPPs開発 の案件が未登録です。zac の選択肢を取り込んでください",
    );
    expect(unresolvedSeriesMessage("2601570", "2026-12-01")).toBeNull();
  });
});

describe("defaultSalesItemId", () => {
  it("prefers the item for the work month", () => {
    expect(defaultSalesItemId("2602028", "2026-10-09", SALES, [])).toBe("ps-10");
    expect(defaultSalesItemId("2602028", "2026-11-02", SALES, [{ job_code: "2602028", work_kind: null, sales_item_id: "ps-10" }])).toBe("ps-11");
  });

  it("never defaults to a closed item", () => {
    expect(defaultSalesItemId("2602028", "2026-09-30", SALES, [])).toBe("");
  });

  it("uses the last used item when there is no month item", () => {
    expect(defaultSalesItemId("2600901", "2026-10-09", SALES, [{ job_code: "2600901", work_kind: null, sales_item_id: "rd-2" }])).toBe("rd-2");
    expect(defaultSalesItemId("2600901", "2026-10-09", SALES, [])).toBe("");
  });

  it("uses the only item", () => {
    expect(defaultSalesItemId("2601570", "2026-10-09", SALES, [])).toBe("ai");
  });

  it("does not carry over another month's item", () => {
    expect(defaultSalesItemId("2602062", "2026-11-02", SALES, [{ job_code: "2602062", work_kind: null, sales_item_id: "bz-10" }])).toBe("");
  });
});

describe("defaultWorkKind", () => {
  const kinds: ZacWorkKind[] = [
    { name: "プロジェクト作業", is_active: true, sort_order: 1 },
    { name: "プロジェクト関連打ち合わせ", is_active: true, sort_order: 2 },
    { name: "廃止した作業内容", is_active: false, sort_order: 3 },
  ];
  const jobs = [{ ...makeJob("2602028", "x"), zac_work_category: "プロジェクト作業" }];

  it("prefers the last used work kind, then the job default", () => {
    expect(defaultWorkKind("2602028", jobs, kinds, [{ job_code: "2602028", work_kind: "プロジェクト関連打ち合わせ", sales_item_id: null }])).toBe("プロジェクト関連打ち合わせ");
    expect(defaultWorkKind("2602028", jobs, kinds, [])).toBe("プロジェクト作業");
    expect(defaultWorkKind("2602028", jobs, kinds, [{ job_code: "2602028", work_kind: "廃止した作業内容", sales_item_id: null }])).toBe("プロジェクト作業");
    expect(defaultWorkKind("9999999", jobs, kinds, [])).toBe("");
  });
});
