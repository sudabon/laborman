import type { Job, ZacSalesItem, ZacTaskDefault, ZacWorkKind } from "@/types";

// シリーズの案件が勤務日の年月に未登録のとき、候補に出す仮のジョブ ID の接頭辞
export const UNRESOLVED_SERIES_PREFIX = "series:";

export function workMonth(workDate: string): string {
  return workDate.slice(0, 7);
}

/**
 * ジョブの候補を作る。月ごとの案件（シリーズ）は勤務日の年月の案件 1 件にまとめ、
 * その月の案件が未登録なら、保存できない仮の候補を出す。
 */
export function collapseSeries(jobs: Job[], workDate: string): Job[] {
  const month = workMonth(workDate);
  const seen = new Set<string>();
  const result: Job[] = [];
  for (const job of jobs) {
    if (!job.series_name) {
      result.push(job);
      continue;
    }
    if (seen.has(job.series_name)) continue;
    seen.add(job.series_name);
    const current = jobs.find((item) => item.series_name === job.series_name && item.valid_month === month);
    result.push(
      current ?? {
        ...job,
        code: `${UNRESOLVED_SERIES_PREFIX}${job.series_name}`,
        name: `${job.series_name}（${month} の案件が未登録）`,
        valid_month: month,
      },
    );
  }
  return result;
}

export function unresolvedSeriesMessage(jobCode: string, workDate: string): string | null {
  if (!jobCode.startsWith(UNRESOLVED_SERIES_PREFIX)) return null;
  const [year, month] = workMonth(workDate).split("-");
  const series = jobCode.slice(UNRESOLVED_SERIES_PREFIX.length);
  return `${year} 年 ${Number(month)} 月の ${series} の案件が未登録です。zac の選択肢を取り込んでください`;
}

export function salesItemsOf(jobCode: string, salesItems: ZacSalesItem[], selectedId?: string | null): ZacSalesItem[] {
  return salesItems.filter((item) => item.job_code === jobCode && (item.is_active || item.id === selectedId));
}

/**
 * 売上項目の初期値：① 勤務日の年月の項目（計上済みを除く）→ ② そのジョブで前回使った項目
 * （別の月の項目は除く）→ ③ 選択肢が 1 つならそれ → ④ 空。
 */
export function defaultSalesItemId(
  jobCode: string,
  workDate: string,
  salesItems: ZacSalesItem[],
  defaults: ZacTaskDefault[],
): string {
  const month = workMonth(workDate);
  const candidates = salesItems.filter((item) => item.job_code === jobCode && item.is_active && !item.is_closed);
  const forMonth = candidates.find((item) => item.valid_month === month);
  if (forMonth) return forMonth.id;
  const lastId = defaults.find((item) => item.job_code === jobCode)?.sales_item_id;
  const last = candidates.find((item) => item.id === lastId);
  if (last && (last.valid_month === null || last.valid_month === month)) return last.id;
  if (candidates.length === 1 && (candidates[0].valid_month === null || candidates[0].valid_month === month)) {
    return candidates[0].id;
  }
  return "";
}

/** 作業内容の初期値：① そのジョブで前回使った作業内容 → ② ジョブの既定の作業内容 → ③ 空。 */
export function defaultWorkKind(
  jobCode: string,
  jobs: Job[],
  workKinds: ZacWorkKind[],
  defaults: ZacTaskDefault[],
): string {
  const active = new Set(workKinds.filter((kind) => kind.is_active).map((kind) => kind.name));
  const last = defaults.find((item) => item.job_code === jobCode)?.work_kind;
  if (last && active.has(last)) return last;
  const fallback = jobs.find((job) => job.code === jobCode)?.zac_work_category ?? "";
  return active.has(fallback) ? fallback : "";
}

export function salesItemLabel(item: ZacSalesItem): string {
  return item.is_closed ? `${item.name}（売上計上済）` : item.name;
}
