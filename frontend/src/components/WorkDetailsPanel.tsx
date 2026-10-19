import { Coffee, Pencil, Plus, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { JobCombobox } from "@/components/JobCombobox";
import { ZacTaskFields } from "@/components/ZacTaskFields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { formatHoursMinutes, formatWorkTime, parseWorkTime, workMinutesBetween } from "@/lib/date";
import {
  collapseSeries,
  defaultSalesItemId,
  defaultWorkKind,
  unresolvedSeriesMessage,
  UNRESOLVED_SERIES_PREFIX,
} from "@/lib/zacDefaults";
import type { EntryConflict, Job, WorkBreak, WorkDetails, WorkTask } from "@/types";

type EntryRow =
  | { kind: "task"; entry: WorkTask }
  | { kind: "break"; entry: WorkBreak };

type RowForm = {
  kind: "task" | "break";
  // 編集中のレコード ID（新規は null）
  id: string | null;
  jobCode: string;
  salesItemId: string;
  workKind: string;
  description: string;
  start: string;
  end: string;
};

type PanelError = { message: string; conflicts: EntryConflict[] };

type WorkDetailsPanelProps = {
  workDate: string;
  details: WorkDetails;
  onChanged: () => Promise<void>;
};

const RUNNING_TICK_MS = 30_000;

function entryLabel(workDate: string, conflict: EntryConflict, details: WorkDetails): string {
  const range = `${formatWorkTime(workDate, conflict.start_at)}–${
    conflict.end_at ? formatWorkTime(workDate, conflict.end_at) : "進行中"
  }`;
  if (conflict.kind === "break") return `休憩 ${range}`;
  const task = details.tasks.find((item) => item.id === conflict.id);
  return `タスク ${range}${task ? ` [${task.job_code}] ${task.description}`.trimEnd() : ""}`;
}

function toPanelError(cause: unknown): PanelError {
  if (cause instanceof ApiError) return { message: cause.message, conflicts: cause.conflicts };
  return { message: cause instanceof Error ? cause.message : String(cause), conflicts: [] };
}

function minutesUntil(entry: { start_at: string; end_at: string | null }, nowIso: string): number {
  return workMinutesBetween(entry.start_at, entry.end_at ?? nowIso);
}

export function WorkDetailsPanel({ workDate, details, onChanged }: WorkDetailsPanelProps) {
  const [jobCode, setJobCode] = useState("");
  const [salesItemId, setSalesItemId] = useState("");
  const [workKind, setWorkKind] = useState("");
  const [description, setDescription] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [form, setForm] = useState<RowForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<PanelError | null>(null);
  const [now, setNow] = useState(() => new Date().toISOString());

  const { tasks, breaks, jobs, salesItems, workKinds, zacDefaults } = details;
  // 月ごとの案件は勤務日の年月の案件にまとめた候補
  const candidateJobs = useMemo(() => collapseSeries(jobs, workDate), [jobs, workDate]);
  const runningTask = tasks.find((task) => task.end_at === null) ?? null;
  const runningBreak = breaks.find((item) => item.end_at === null) ?? null;

  const rows = useMemo<EntryRow[]>(
    () =>
      [
        ...tasks.map((entry) => ({ kind: "task" as const, entry })),
        ...breaks.map((entry) => ({ kind: "break" as const, entry })),
      ].sort((a, b) => new Date(a.entry.start_at).getTime() - new Date(b.entry.start_at).getTime()),
    [tasks, breaks],
  );

  useEffect(() => {
    if (!runningTask && !runningBreak) return;
    const timer = window.setInterval(() => setNow(new Date().toISOString()), RUNNING_TICK_MS);
    return () => window.clearInterval(timer);
  }, [runningTask, runningBreak]);

  useEffect(() => {
    setForm(null);
    setError(null);
    setStart("");
    setEnd("");
  }, [workDate]);

  // ジョブを選んだら、売上項目と作業内容に初期値を入れる（design D11）
  const zacDefaultsFor = (code: string) => ({
    salesItemId: defaultSalesItemId(code, workDate, salesItems, zacDefaults),
    workKind: defaultWorkKind(code, jobs, workKinds, zacDefaults),
  });

  const selectJob = (code: string) => {
    const defaults = zacDefaultsFor(code);
    setJobCode(code);
    setSalesItemId(defaults.salesItemId);
    setWorkKind(defaults.workKind);
  };

  // 勤務日を変えたとき、月ごとの案件はその月の案件に置き換えて初期値を入れ直す
  useEffect(() => {
    if (!jobCode) return;
    const current = jobs.find((job) => job.code === jobCode);
    const seriesName = current?.series_name ?? (jobCode.startsWith(UNRESOLVED_SERIES_PREFIX) ? jobCode.slice(UNRESOLVED_SERIES_PREFIX.length) : null);
    if (!seriesName) return;
    const replacement = candidateJobs.find(
      (job) => job.series_name === seriesName || job.code === `${UNRESOLVED_SERIES_PREFIX}${seriesName}`,
    );
    if (replacement && replacement.code !== jobCode) selectJob(replacement.code);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateJobs]);

  const workMinutes = tasks.reduce((sum, task) => sum + minutesUntil(task, now), 0);
  const breakMinutes = breaks.reduce((sum, item) => sum + minutesUntil(item, now), 0);

  const run = async (action: () => Promise<unknown>): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await onChanged();
      setNow(new Date().toISOString());
      return true;
    } catch (cause) {
      setError(toPanelError(cause));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const createJob = async (code: string, name: string): Promise<Job> => {
    const job = await api.createJob({ code, name });
    await onChanged();
    return job;
  };

  // 時分（HH:MM）で入力したタスクを追加する。終了が空欄なら進行中として保存する
  const addTask = async () => {
    const saved = await run(async () => {
      if (!jobCode) throw new Error("ジョブを選択してください");
      const unresolved = unresolvedSeriesMessage(jobCode, workDate);
      if (unresolved) throw new Error(unresolved);
      const start_at = parseWorkTime(workDate, start);
      const end_at = end.trim() ? parseWorkTime(workDate, end) : null;
      await api.createTask(workDate, {
        job_code: jobCode,
        description,
        work_kind: workKind || null,
        sales_item_id: salesItemId || null,
        start_at,
        end_at,
      });
    });
    if (saved) {
      // 続けて入力しやすいよう、次の開始に今回の終了を入れる
      setDescription("");
      setStart(end.trim());
      setEnd("");
    }
  };

  const openNewBreak = () => {
    setError(null);
    setForm({ kind: "break", id: null, jobCode: "", salesItemId: "", workKind: "", description: "", start: "", end: "" });
  };

  const openEditRow = (row: EntryRow) => {
    setError(null);
    setForm({
      kind: row.kind,
      id: row.entry.id,
      jobCode: row.kind === "task" ? row.entry.job_code : "",
      salesItemId: row.kind === "task" ? (row.entry.sales_item_id ?? "") : "",
      workKind: row.kind === "task" ? (row.entry.work_kind ?? "") : "",
      description: row.kind === "task" ? row.entry.description : "",
      start: formatWorkTime(workDate, row.entry.start_at),
      end: row.entry.end_at ? formatWorkTime(workDate, row.entry.end_at) : "",
    });
  };

  const saveRow = async () => {
    if (!form) return;
    const saved = await run(async () => {
      const start_at = parseWorkTime(workDate, form.start);
      // 終了が空欄なら進行中として保存する
      const end_at = form.end.trim() ? parseWorkTime(workDate, form.end) : null;
      if (form.kind === "task") {
        if (!form.jobCode) throw new Error("ジョブを選択してください");
        const unresolved = unresolvedSeriesMessage(form.jobCode, workDate);
        if (unresolved) throw new Error(unresolved);
        const payload = {
          job_code: form.jobCode,
          description: form.description,
          work_kind: form.workKind || null,
          sales_item_id: form.salesItemId || null,
          start_at,
          end_at,
        };
        await (form.id ? api.updateTask(form.id, payload) : api.createTask(workDate, payload));
      } else {
        const payload = { start_at, end_at };
        await (form.id ? api.updateBreak(form.id, payload) : api.createBreak(workDate, payload));
      }
    });
    if (saved) setForm(null);
  };

  const deleteRow = (row: EntryRow) =>
    run(() => (row.kind === "task" ? api.deleteTask(row.entry.id) : api.deleteBreak(row.entry.id)));

  const updateForm = (patch: Partial<RowForm>) => setForm((current) => (current ? { ...current, ...patch } : current));

  const rowForm = form ? (
    <div className="grid gap-3 rounded-md border border-border bg-muted p-3" aria-label={form.id ? "行を編集" : "休憩を追加"} role="group">
      <div className="grid gap-3 sm:grid-cols-[96px_96px_minmax(0,1fr)_minmax(0,2fr)]">
        <div className="grid gap-1">
          <label htmlFor="row-start" className="text-sm font-medium">
            開始
          </label>
          <Input
            id="row-start"
            inputMode="numeric"
            placeholder="09:00"
            value={form.start}
            onChange={(event) => updateForm({ start: event.target.value })}
          />
        </div>
        <div className="grid gap-1">
          <label htmlFor="row-end" className="text-sm font-medium">
            終了
          </label>
          <Input
            id="row-end"
            inputMode="numeric"
            placeholder="25:15"
            value={form.end}
            onChange={(event) => updateForm({ end: event.target.value })}
          />
        </div>
        {form.kind === "task" ? (
          <>
            <JobCombobox
              id="row-job"
              jobs={candidateJobs}
              value={form.jobCode}
              onChange={(code) => updateForm({ jobCode: code, ...zacDefaultsFor(code) })}
              onCreateJob={createJob}
            />
            <div className="grid gap-1">
              <label htmlFor="row-description" className="text-sm font-medium">
                内容
              </label>
              <Input
                id="row-description"
                maxLength={200}
                value={form.description}
                onChange={(event) => updateForm({ description: event.target.value })}
              />
            </div>
          </>
        ) : null}
      </div>
      {form.kind === "task" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <ZacTaskFields
            idPrefix="row"
            jobCode={form.jobCode}
            salesItems={salesItems}
            workKinds={workKinds}
            salesItemId={form.salesItemId}
            workKind={form.workKind}
            onSalesItemChange={(id) => updateForm({ salesItemId: id })}
            onWorkKindChange={(name) => updateForm({ workKind: name })}
          />
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">
        HH:MM で入力します。日付をまたぐ場合は 24:00〜29:59 を使います。終了を空欄にすると進行中になります。
      </p>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => void saveRow()} disabled={busy}>
          保存
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setForm(null)}>
          <X aria-hidden="true" className="h-4 w-4" />
          キャンセル
        </Button>
      </div>
    </div>
  ) : null;

  return (
    <section aria-labelledby="work-details-title" className="grid gap-4 rounded-lg border border-border bg-card p-4">
      <h2 id="work-details-title" className="text-lg font-semibold">
        業務明細
      </h2>

      <form
        aria-label="タスクを追加"
        className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.6fr)_88px_88px_auto] sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          void addTask();
        }}
      >
        <JobCombobox id="current-job" jobs={candidateJobs} value={jobCode} onChange={selectJob} onCreateJob={createJob} />
        <ZacTaskFields
          idPrefix="current"
          jobCode={jobCode}
          salesItems={salesItems}
          workKinds={workKinds}
          salesItemId={salesItemId}
          workKind={workKind}
          onSalesItemChange={setSalesItemId}
          onWorkKindChange={setWorkKind}
        />
        <div className="grid gap-1">
          <label htmlFor="current-description" className="text-sm font-medium">
            内容
          </label>
          <Input
            id="current-description"
            maxLength={200}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
        <div className="grid gap-1">
          <label htmlFor="current-start" className="text-sm font-medium">
            開始
          </label>
          <Input
            id="current-start"
            inputMode="numeric"
            placeholder="09:00"
            value={start}
            onChange={(event) => setStart(event.target.value)}
          />
        </div>
        <div className="grid gap-1">
          <label htmlFor="current-end" className="text-sm font-medium">
            終了
          </label>
          <Input
            id="current-end"
            inputMode="numeric"
            placeholder="10:30"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={busy || !jobCode || !start.trim()}>
          <Plus aria-hidden="true" className="h-4 w-4" />
          追加
        </Button>
      </form>
      <p className="-mt-2 text-xs text-muted-foreground">
        時刻は HH:MM（時分のみ）。日付をまたぐ場合は 24:00〜29:59、終了を空欄にすると進行中になります。休憩は平日を開くと既定の時間帯で自動的に入ります。
      </p>

      {error ? (
        <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <p>保存できませんでした：{error.message}</p>
          {error.conflicts.length > 0 ? (
            <ul className="mt-1 list-disc pl-5">
              {error.conflicts.map((conflict) => (
                <li key={`${conflict.kind}-${conflict.id}`}>重なっている相手：{entryLabel(workDate, conflict, details)}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th scope="col" className="py-2 pr-3 font-medium">開始</th>
              <th scope="col" className="py-2 pr-3 font-medium">終了</th>
              <th scope="col" className="py-2 pr-3 font-medium">ジョブ</th>
              <th scope="col" className="py-2 pr-3 font-medium">内容</th>
              <th scope="col" className="py-2 pr-3 font-medium">時間</th>
              <th scope="col" className="py-2 font-medium">
                <span className="sr-only">操作</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-3 text-muted-foreground">
                  まだ記録がありません
                </td>
              </tr>
            ) : null}
            {rows.map((row) => {
              const { entry } = row;
              const label = `${formatWorkTime(workDate, entry.start_at)} の${row.kind === "task" ? "タスク" : "休憩"}`;
              return (
                <tr key={`${row.kind}-${entry.id}`} className="border-b border-border last:border-0">
                  <td className="py-2 pr-3 tabular-nums">{formatWorkTime(workDate, entry.start_at)}</td>
                  <td className="py-2 pr-3 tabular-nums">
                    {entry.end_at ? (
                      formatWorkTime(workDate, entry.end_at)
                    ) : (
                      <span className="font-medium text-primary">進行中</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    {row.kind === "task" ? (
                      <>
                        {row.entry.job_code}
                        <span className="block text-xs text-muted-foreground" data-testid="task-zac">
                          {[
                            row.entry.work_kind ?? "作業内容 未選択",
                            salesItems.find((item) => item.id === row.entry.sales_item_id)?.name ?? "売上項目 未選択",
                          ].join(" / ")}
                        </span>
                      </>
                    ) : (
                      "(休憩)"
                    )}
                  </td>
                  <td className="py-2 pr-3">{row.kind === "task" ? row.entry.description : ""}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatHoursMinutes(minutesUntil(entry, now))}</td>
                  <td className="py-2 text-right whitespace-nowrap">
                    <Button variant="ghost" size="icon" aria-label={`${label}を編集`} onClick={() => openEditRow(row)}>
                      <Pencil aria-hidden="true" className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`${label}を削除`}
                      onClick={() => void deleteRow(row)}
                      disabled={busy}
                    >
                      <Trash2 aria-hidden="true" className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {rowForm}
      {!form ? (
        <Button variant="outline" size="sm" className="w-fit" onClick={openNewBreak}>
          <Coffee aria-hidden="true" className="h-4 w-4" />
          休憩を追加
        </Button>
      ) : null}

      <p className="text-sm">
        合計 作業 <span className="font-semibold tabular-nums">{formatHoursMinutes(workMinutes)}</span> / 休憩{" "}
        <span className="font-semibold tabular-nums">{formatHoursMinutes(breakMinutes)}</span>
      </p>
    </section>
  );
}
