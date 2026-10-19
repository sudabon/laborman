import { PencilLine } from "lucide-react";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatShortDateTime, formatWorkTime, parseWorkTime } from "@/lib/date";
import { ATTENDANCE_NOT_IMPORTED } from "@/lib/mail";
import type { AttendanceInput, AttendanceKind, AttendanceSource, WorkReport } from "@/types";

type AttendancePanelProps = {
  workDate: string;
  report: WorkReport | null;
  onSave: (payload: AttendanceInput) => Promise<void>;
};

const sourceLabels: Record<AttendanceSource, string> = {
  hr_mail: "人事メール",
  manual: "手入力",
};

const kindLabels: Record<AttendanceKind, string> = {
  work: "勤務",
  leave: "休暇",
};

function attendanceSummary(workDate: string, report: WorkReport | null): string {
  if (report?.attendance_kind === "leave") return kindLabels.leave;
  if (!report?.attendance_start_at || !report.attendance_end_at) return ATTENDANCE_NOT_IMPORTED;
  return `${formatWorkTime(workDate, report.attendance_start_at)} – ${formatWorkTime(workDate, report.attendance_end_at)}`;
}

type AttendanceForm = { start: string; end: string; kind: AttendanceKind };

function initialForm(workDate: string, report: WorkReport | null): AttendanceForm {
  return {
    start: report?.attendance_start_at ? formatWorkTime(workDate, report.attendance_start_at) : "",
    end: report?.attendance_end_at ? formatWorkTime(workDate, report.attendance_end_at) : "",
    kind: report?.attendance_kind ?? "work",
  };
}

function toInput(workDate: string, form: AttendanceForm): AttendanceInput {
  const parse = (value: string) => (value.trim() ? parseWorkTime(workDate, value) : null);
  if (form.kind === "work" && (!form.start.trim() || !form.end.trim())) {
    throw new Error("勤務の場合は出勤・退勤を入力してください");
  }
  return { start_at: parse(form.start), end_at: parse(form.end), source: "manual", kind: form.kind };
}

export function AttendancePanel({ workDate, report, onSave }: AttendancePanelProps) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<AttendanceForm>(() => initialForm(workDate, report));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const source = report?.attendance_source ?? null;

  const openDialog = () => {
    setForm(initialForm(workDate, report));
    setError(null);
    setOpen(true);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await onSave(toInput(workDate, form));
      setOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      aria-labelledby="attendance-title"
      className="flex flex-col gap-3 rounded-md border border-border bg-muted px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="grid gap-1">
        <h2 id="attendance-title" className="text-sm text-muted-foreground">
          出退勤（人事メール）
        </h2>
        <p className="text-2xl font-semibold" data-testid="attendance-summary">
          {attendanceSummary(workDate, report)}
        </p>
        {source ? (
          <p className="text-xs text-muted-foreground">
            {sourceLabels[source]}
            {report?.attendance_imported_at ? `・取込 ${formatShortDateTime(report.attendance_imported_at)}` : ""}
          </p>
        ) : null}
      </div>
      <Button variant="outline" size="sm" className="w-fit" onClick={openDialog} disabled={!report}>
        <PencilLine aria-hidden="true" className="h-4 w-4" />
        手入力
      </Button>

      <Dialog open={open} onOpenChange={setOpen} className="w-[min(420px,calc(100vw-2rem))]">
        <form aria-labelledby="attendance-dialog-title" className="grid gap-4 p-5" onSubmit={(event) => void submit(event)}>
          <h2 id="attendance-dialog-title" className="text-lg font-semibold">
            出退勤を手入力
          </h2>
          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium">区分</legend>
            <div className="flex gap-4">
              {(Object.keys(kindLabels) as AttendanceKind[]).map((kind) => (
                <label key={kind} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="attendance-kind"
                    value={kind}
                    checked={form.kind === kind}
                    onChange={() => setForm({ ...form, kind })}
                  />
                  {kindLabels[kind]}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex flex-wrap gap-3">
            <div className="grid gap-1">
              <Label htmlFor="attendance-start">出勤</Label>
              <Input
                id="attendance-start"
                className="w-28"
                inputMode="numeric"
                placeholder="09:00"
                value={form.start}
                onChange={(event) => setForm({ ...form, start: event.target.value })}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="attendance-end">退勤</Label>
              <Input
                id="attendance-end"
                className="w-28"
                inputMode="numeric"
                placeholder="18:00"
                value={form.end}
                onChange={(event) => setForm({ ...form, end: event.target.value })}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            HH:MM 形式（24:00〜29:59 は翌日）。休暇の日は時刻を空にできます。手入力した日は人事メールで上書きされません。
          </p>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              キャンセル
            </Button>
            <Button type="submit" disabled={saving}>
              保存
            </Button>
          </div>
        </form>
      </Dialog>
    </section>
  );
}
