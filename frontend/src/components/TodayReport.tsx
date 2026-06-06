import { CheckCircle2, Clock, Mail, PlayCircle, Save, Settings, StopCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatDateForDisplay, formatDuration, formatTime } from "@/lib/date";
import { hasRequiredRecipients, NOTE_MAX_LENGTH, statusLabels, workStyleLabels } from "@/lib/mail";
import type { MailKind, MailSettings, WorkReport, WorkReportUpdate, WorkStyle } from "@/types";

type TodayReportProps = {
  date: Date;
  report: WorkReport | null;
  settings: MailSettings | null;
  sentConfirmations: Record<string, boolean>;
  onSaveReport: (payload: WorkReportUpdate) => Promise<void>;
  onRecordStart: (payload: WorkReportUpdate) => Promise<void>;
  onRecordEnd: (payload: WorkReportUpdate) => Promise<void>;
  onCreateMail: (kind: MailKind, payload: WorkReportUpdate) => Promise<void>;
  onToggleConfirmation: (key: string, checked: boolean) => void;
  onOpenSettings: () => void;
};

export function TodayReport({
  date,
  report,
  settings,
  sentConfirmations,
  onSaveReport,
  onRecordStart,
  onRecordEnd,
  onCreateMail,
  onToggleConfirmation,
  onOpenSettings,
}: TodayReportProps) {
  const [note, setNote] = useState(report?.note ?? "");
  const [workStyle, setWorkStyle] = useState<WorkStyle>(report?.work_style ?? "office");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    setNote(report?.note ?? "");
    setWorkStyle(report?.work_style ?? "office");
  }, [report?.id, report?.note, report?.work_style]);

  const recipientsReady = settings ? hasRequiredRecipients(settings) : false;
  const payload = { note, work_style: workStyle };
  const startConfirmationKey = report ? `${report.work_date}:start` : "";
  const endConfirmationKey = report ? `${report.work_date}:end` : "";

  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    try {
      await action();
    } finally {
      setBusy(null);
    }
  };

  const noteCount = note.length;

  return (
    <section className="grid gap-5">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">本日の報告</h1>
          <p className="mt-1 text-sm text-muted-foreground">{formatDateForDisplay(date)}</p>
        </div>
        <div className="inline-flex w-fit items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm">
          <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-secondary" />
          {report ? statusLabels[report.status] : statusLabels.not_started}
        </div>
      </div>

      {!recipientsReady ? (
        <div className="flex flex-col gap-3 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive sm:flex-row sm:items-center sm:justify-between">
          <span>上司または労務MLが未設定です。</span>
          <Button variant="outline" size="sm" onClick={onOpenSettings}>
            <Settings aria-hidden="true" className="h-4 w-4" />
            設定を開く
          </Button>
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_320px]">
        <section className="grid gap-4 rounded-lg border border-border bg-card p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-md border border-border bg-muted px-3 py-3">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Clock aria-hidden="true" className="h-4 w-4" />
                始業時刻
              </div>
              <p className="mt-2 text-2xl font-semibold">{formatTime(report?.start_time ?? null)}</p>
            </div>
            <div className="rounded-md border border-border bg-muted px-3 py-3">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Clock aria-hidden="true" className="h-4 w-4" />
                終業時刻
              </div>
              <p className="mt-2 text-2xl font-semibold">{formatTime(report?.end_time ?? null)}</p>
            </div>
            <div className="rounded-md border border-border bg-muted px-3 py-3">
              <div className="text-sm text-muted-foreground">勤務時間</div>
              <p className="mt-2 text-2xl font-semibold">{formatDuration(report?.work_duration_minutes ?? null)}</p>
            </div>
            <div className="rounded-md border border-border bg-muted px-3 py-3">
              <div className="text-sm text-muted-foreground">勤務区分</div>
              <p className="mt-2 text-2xl font-semibold">{workStyleLabels[workStyle]}</p>
            </div>
          </div>

          <div className="grid gap-3">
            <Label>勤務区分</Label>
            <div className="inline-flex w-fit rounded-md border border-border bg-muted p-1">
              {(["office", "remote"] as WorkStyle[]).map((style) => (
                <button
                  key={style}
                  type="button"
                  className={`rounded-sm px-4 py-2 text-sm font-medium transition-colors ${
                    workStyle === style ? "bg-card text-primary shadow-sm" : "text-muted-foreground hover:text-foreground"
                  }`}
                  onClick={() => setWorkStyle(style)}
                >
                  {workStyleLabels[style]}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-2">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="note">メモ</Label>
              <span className="text-xs text-muted-foreground">
                {noteCount}/{NOTE_MAX_LENGTH}
              </span>
            </div>
            <Textarea
              id="note"
              maxLength={NOTE_MAX_LENGTH}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => run("save", () => onSaveReport(payload))} disabled={busy !== null}>
              <Save aria-hidden="true" className="h-4 w-4" />
              保存
            </Button>
            <Button onClick={() => run("start", () => onRecordStart(payload))} disabled={busy !== null}>
              <PlayCircle aria-hidden="true" className="h-4 w-4" />
              始業を記録
            </Button>
            <Button variant="secondary" onClick={() => run("end", () => onRecordEnd(payload))} disabled={busy !== null}>
              <StopCircle aria-hidden="true" className="h-4 w-4" />
              終業を記録
            </Button>
          </div>
        </section>

        <aside className="grid gap-4 rounded-lg border border-border bg-card p-4">
          <div>
            <h2 className="text-lg font-semibold">メール作成</h2>
            <p className="mt-1 text-sm text-muted-foreground">ステータスはメール作成済みまで記録します。</p>
          </div>
          <div className="grid gap-2">
            <Button
              onClick={() => run("start-mail", () => onCreateMail("start", payload))}
              disabled={!recipientsReady || !report?.start_time || busy !== null}
            >
              <Mail aria-hidden="true" className="h-4 w-4" />
              Outlookで始業メールを作成
            </Button>
            <label className="flex items-start gap-2 rounded-md border border-border px-3 py-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                disabled={!report?.start_mail_created_at}
                checked={Boolean(sentConfirmations[startConfirmationKey])}
                onChange={(event) => onToggleConfirmation(startConfirmationKey, event.target.checked)}
              />
              <span>Outlookで送信しました（自己申告）</span>
            </label>
          </div>
          <div className="grid gap-2">
            <Button
              variant="secondary"
              onClick={() => run("end-mail", () => onCreateMail("end", payload))}
              disabled={!recipientsReady || !report?.end_time || busy !== null}
            >
              <Mail aria-hidden="true" className="h-4 w-4" />
              Outlookで終業メールを作成
            </Button>
            <label className="flex items-start gap-2 rounded-md border border-border px-3 py-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                disabled={!report?.end_mail_created_at}
                checked={Boolean(sentConfirmations[endConfirmationKey])}
                onChange={(event) => onToggleConfirmation(endConfirmationKey, event.target.checked)}
              />
              <span>Outlookで送信しました（自己申告）</span>
            </label>
          </div>
        </aside>
      </div>
    </section>
  );
}
