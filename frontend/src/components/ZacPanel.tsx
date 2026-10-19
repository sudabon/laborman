import { AlertTriangle, CircleAlert, Info, Send, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatHoursMinutes, formatShortDateTime } from "@/lib/date";
import { cn } from "@/lib/utils";
import type { ZacDraft, ZacDraftIssue, ZacRunStatus, ZacSubmitMode, ZacSyncRun } from "@/types";

type ZacPanelProps = {
  workDate: string;
  // 業務明細・出退勤が変わったら値が変わる。変わるたびにドラフトを取り直す
  refreshKey: string;
  // 実行が終わったとき（zac 保存成功日時・カレンダーの状態を取り直す）
  onRunFinished: () => Promise<void>;
};

// 依頼中・実行中の間、結果が記録されるまで取り直す間隔
export const ZAC_RUN_POLL_MS = 10_000;

export const zacRunStatusLabels: Record<ZacRunStatus, string> = {
  requested: "依頼中",
  cancelled: "取り消し",
  running: "実行中",
  succeeded: "保存完了",
  dry_run_done: "入力のみ（保存なし）",
  awaiting_user: "保存待ちのまま時間切れ",
  validation_failed: "検証エラー",
  needs_login: "サインインが必要",
  vpn_unreachable: "VPN 未接続",
  hr_mail_not_found: "人事メール未着",
  already_registered_in_zac: "zac に入力済み",
  failed: "失敗",
};

const modeLabels: Record<ZacSubmitMode, string> = {
  dry_run: "dry_run",
  assist: "assist",
  auto: "auto",
};

const issueStyles: Record<ZacDraftIssue["severity"], { tone: string; Icon: typeof Info; label: string }> = {
  error: { tone: "border-destructive/40 bg-destructive/10 text-destructive", Icon: CircleAlert, label: "エラー" },
  warning: { tone: "border-accent/50 bg-accent/15 text-accent-foreground", Icon: AlertTriangle, label: "警告" },
  info: { tone: "border-border bg-muted text-muted-foreground", Icon: Info, label: "情報" },
};

const OPEN_STATUSES: ZacRunStatus[] = ["requested", "running"];

function errorText(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

function IssueItem({ issue }: { issue: ZacDraftIssue }) {
  const { tone, Icon, label } = issueStyles[issue.severity];
  const breakMissing = issue.code === "BREAK_MISSING";
  return (
    <li className={cn("flex gap-2 rounded-md border px-3 py-2 text-sm", tone, breakMissing && "border-2 font-semibold")}>
      <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <span>
        <span className="sr-only">{label}：</span>
        {issue.message}
        {breakMissing ? "。zac 登録を中止しました。業務明細に休憩を記録してください。" : ""}
      </span>
    </li>
  );
}

// エラーが出退勤の未取込だけなら、エージェントが人事メールを取り込んでから入力する
function waitingForAttendance(draft: ZacDraft): boolean {
  const errors = draft.issues.filter((issue) => issue.severity === "error");
  return errors.length > 0 && errors.every((issue) => issue.code === "ATTENDANCE_MISSING");
}

export function ZacPanel({ workDate, refreshKey, onRunFinished }: ZacPanelProps) {
  const [draft, setDraft] = useState<ZacDraft | null>(null);
  const [runs, setRuns] = useState<ZacSyncRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hadOpenRun = useRef(false);

  const load = useCallback(async () => {
    const [nextDraft, nextRuns] = await Promise.all([api.getZacDraft(workDate), api.getZacRuns(workDate)]);
    setDraft(nextDraft);
    setRuns(nextRuns);
  }, [workDate]);

  useEffect(() => {
    void load().catch((cause) => setError(errorText(cause)));
  }, [load, refreshKey]);

  const latestRun = runs[0] ?? null;
  const openRun = runs.find((run) => OPEN_STATUSES.includes(run.status)) ?? null;

  useEffect(() => {
    if (!openRun) {
      if (hadOpenRun.current) {
        hadOpenRun.current = false;
        void onRunFinished();
      }
      return;
    }
    hadOpenRun.current = true;
    const timer = window.setInterval(() => {
      void load().catch((cause) => setError(errorText(cause)));
    }, ZAC_RUN_POLL_MS);
    return () => window.clearInterval(timer);
  }, [openRun, load, onRunFinished]);

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  };

  const registered = Boolean(draft?.zac_registered_at);
  const enteredMinutes = draft?.entries.reduce((sum, entry) => sum + entry.minutes, 0) ?? 0;

  return (
    <section aria-labelledby="zac-panel-title" className="grid gap-4 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 id="zac-panel-title" className="text-lg font-semibold">
          zac 登録
        </h2>
        <Button
          onClick={() => void act(() => api.requestZacRun(workDate))}
          disabled={busy || registered || openRun !== null || draft === null}
        >
          <Send aria-hidden="true" className="h-4 w-4" />
          この日を zac に登録
        </Button>
      </div>

      {openRun ? (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-md border border-primary/40 bg-primary/10 px-3 py-2 text-sm">
          <span>
            {openRun.status === "requested"
              ? `依頼中（${formatShortDateTime(openRun.started_at)}）— エージェントが 1 分以内に実行します`
              : `実行中（${formatShortDateTime(openRun.started_at)} 開始）`}
          </span>
          {openRun.status === "requested" ? (
            <Button size="sm" variant="outline" onClick={() => void act(() => api.cancelZacRun(openRun.id))} disabled={busy}>
              <X aria-hidden="true" className="h-4 w-4" />
              依頼を取り消す
            </Button>
          ) : null}
        </div>
      ) : null}
      {registered && draft?.zac_registered_at ? (
        <p className="text-sm text-secondary">zac に登録済みです（{formatShortDateTime(draft.zac_registered_at)}）</p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {draft ? (
        <div className="grid gap-3">
          <p className="text-sm" data-testid="zac-summary">
            {draft.attendance ? `出退勤 ${draft.attendance.start}–${draft.attendance.end}` : "出退勤 未取込"}
            {draft.working_minutes !== null ? ` / 実働 ${formatHoursMinutes(draft.working_minutes)}` : ""}
            {draft.entries.length > 0 ? ` / 入力 ${formatHoursMinutes(enteredMinutes)}` : ""}
            {draft.breaks.length > 0
              ? ` / 休憩 ${draft.breaks.map((item) => `${item.start}–${item.end}`).join("・")}`
              : ""}
          </p>

          {draft.entries.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <caption className="sr-only">zac に入力する内容</caption>
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    {draft.entry_style === "time_range" ? (
                      <th scope="col" className="py-2 pr-3 font-medium">時刻</th>
                    ) : null}
                    <th scope="col" className="py-2 pr-3 font-medium">作業内容</th>
                    <th scope="col" className="py-2 pr-3 font-medium">案件</th>
                    <th scope="col" className="py-2 pr-3 font-medium">売上項目</th>
                    <th scope="col" className="py-2 pr-3 font-medium">時間</th>
                    <th scope="col" className="py-2 font-medium">備考</th>
                  </tr>
                </thead>
                <tbody>
                  {draft.entries.map((entry, index) => (
                    <tr key={`${entry.job_code}-${index}`} className="border-b border-border last:border-0">
                      {draft.entry_style === "time_range" ? (
                        <td className="py-2 pr-3 tabular-nums">
                          {entry.start}–{entry.end}
                        </td>
                      ) : null}
                      <td className="py-2 pr-3">{entry.work_kind || "（未設定）"}</td>
                      <td className="py-2 pr-3">
                        {entry.job_code}
                        {entry.project_name ? <span className="block text-xs text-muted-foreground">{entry.project_name}</span> : null}
                      </td>
                      <td className="py-2 pr-3">{entry.sales_item || "（未設定）"}</td>
                      <td className="py-2 pr-3 tabular-nums">{formatHoursMinutes(entry.minutes)}</td>
                      <td className="whitespace-pre-line py-2">{entry.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {draft.issues.length > 0 ? (
            <ul aria-label="検証結果" className="grid gap-2">
              {draft.issues.map((issue, index) => (
                <IssueItem key={`${issue.code}-${issue.ref_id ?? index}`} issue={issue} />
              ))}
            </ul>
          ) : null}
          <p className="text-xs text-muted-foreground">
            {draft.registrable
              ? draft.auto_allowed
                ? "zac に登録できます。"
                : "zac に登録できます（警告があるため auto では保存せず、入力までにとどめます）。"
              : waitingForAttendance(draft)
                ? "「この日を zac に登録」を押すと、人事メールから出退勤を取り込んでから zac に入力します。"
                : "エラーがあるため zac には保存しません。"}
          </p>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">読み込み中です</p>
      )}

      <div className="border-t border-border pt-3 text-sm" data-testid="zac-latest-run">
        {latestRun ? (
          <div className="grid gap-1">
            <p>
              最終実行：{formatShortDateTime(latestRun.started_at)} {modeLabels[latestRun.mode]}・
              <span className="font-medium">{zacRunStatusLabels[latestRun.status]}</span>
            </p>
            {latestRun.message ? <p className="text-muted-foreground">{latestRun.message}</p> : null}
            {latestRun.screenshot_path ? (
              <p className="text-muted-foreground">
                スクリーンショット：<code className="break-all text-xs">{latestRun.screenshot_path}</code>
              </p>
            ) : null}
          </div>
        ) : (
          <p className="text-muted-foreground">まだ実行していません</p>
        )}
      </div>
    </section>
  );
}
