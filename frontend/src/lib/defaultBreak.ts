import { api } from "@/lib/api";
import { isReportingWeekday, parseISODate, parseWorkTime } from "@/lib/date";

/**
 * 平日・休憩 0 件・休暇でない勤務日に、既定の休憩を追加する。追加したら true。
 * 勤務日を表示したときだけ呼ぶ（編集後の再取得で呼ぶと、削除した休憩がすぐ戻ってしまう）。
 * 祝日は区別しない。タスクと重なっても追加する（重なりは利用者が後で調整する）。
 */
export async function ensureDefaultBreak(workDate: string): Promise<boolean> {
  if (!isReportingWeekday(parseISODate(workDate))) return false;
  const breaks = await api.getBreaks(workDate);
  if (breaks.length > 0) return false;
  const [settings, report] = await Promise.all([api.getAutomationSettings(), api.getReport(workDate)]);
  if (report.attendance_kind === "leave") return false;
  await api.createBreak(workDate, {
    start_at: parseWorkTime(workDate, settings.default_break_start),
    end_at: parseWorkTime(workDate, settings.default_break_end),
  });
  return true;
}
