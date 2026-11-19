import { Plus, Save } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type {
  AutomationSettings,
  AutomationSettingsInput,
  Job,
  JobCodeChange,
  JobCreate,
  JobUpdate,
  MailSettings,
  ZacSalesItem,
  ZacWorkKind,
} from "@/types";
import { salesItemLabel } from "@/lib/zacDefaults";

type BreakSettings = Pick<AutomationSettings, "default_break_start" | "default_break_end">;
type HrMailSettings = Pick<AutomationSettings, "hr_mail_subject_keyword" | "hr_mail_from">;
type ZacSettings = Pick<
  AutomationSettings,
  | "zac_submit_mode"
  | "entry_style"
  | "clip_tolerance_minutes"
  | "gap_policy"
  | "default_job_code"
  | "default_work_kind"
  | "default_sales_item_id"
  | "description_max_length"
>;

const selectClass =
  "h-10 rounded-md border border-input bg-card px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

type SettingsPanelProps = {
  settings: MailSettings | null;
  onSave: (settings: MailSettings) => Promise<void>;
  jobs: Job[];
  onCreateJob: (payload: JobCreate) => Promise<Job>;
  onUpdateJob: (code: string, payload: JobUpdate) => Promise<Job>;
  // ジョブ ID の変更。新しい ID のジョブを作り、元のジョブは無効化する（記録済みのタスクは変えない）
  onChangeJobCode: (code: string, payload: JobCodeChange) => Promise<Job>;
  salesItems: ZacSalesItem[];
  workKinds: ZacWorkKind[];
  onCreateSalesItem: (jobCode: string, name: string) => Promise<void>;
  onUpdateSalesItem: (itemId: string, payload: { is_active?: boolean; is_closed?: boolean }) => Promise<void>;
  onCreateWorkKind: (name: string) => Promise<void>;
  onUpdateWorkKind: (name: string, payload: { is_active?: boolean }) => Promise<void>;
  automationSettings: AutomationSettings | null;
  onSaveAutomationSettings: (settings: AutomationSettingsInput) => Promise<void>;
};

// 自動化設定の PUT は全項目を送るため、編集していない項目は現在値を引き継ぐ
function toAutomationInput(current: AutomationSettings, changes: Partial<AutomationSettingsInput>): AutomationSettingsInput {
  const { id: _id, created_at: _createdAt, updated_at: _updatedAt, ...fields } = current;
  return { ...fields, ...changes };
}

function errorText(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

const emptyJob: Required<JobCreate> = { code: "", name: "", zac_search_text: "", zac_work_category: "" };

type JobDraft = {
  code: string;
  name: string;
  zac_search_text: string;
  zac_work_category: string;
  series_name: string;
  valid_month: string;
};

function jobDraft(job: Job): JobDraft {
  return {
    code: job.code,
    name: job.name,
    zac_search_text: job.zac_search_text,
    zac_work_category: job.zac_work_category,
    series_name: job.series_name ?? "",
    valid_month: job.valid_month ?? "",
  };
}

function SalesItemsEditor({
  job,
  salesItems,
  onCreate,
  onUpdate,
}: {
  job: Job;
  salesItems: ZacSalesItem[];
  onCreate: SettingsPanelProps["onCreateSalesItem"];
  onUpdate: SettingsPanelProps["onUpdateSalesItem"];
}) {
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const items = salesItems.filter((item) => item.job_code === job.code);

  const run = async (action: () => Promise<void>) => {
    setMessage(null);
    try {
      await action();
    } catch (cause) {
      setMessage(errorText(cause));
    }
  };

  return (
    <div className="grid gap-2 rounded-md bg-muted p-3" role="group" aria-label={`${job.code} の売上項目`}>
      {items.length > 0 ? (
        <ul className="grid gap-1">
          {items.map((item) => (
            <li key={item.id} className={`flex flex-wrap items-center gap-2 text-sm ${item.is_active ? "" : "text-muted-foreground line-through"}`}>
              <span className="min-w-48">{salesItemLabel(item)}</span>
              <span className="text-xs text-muted-foreground">{item.valid_month ?? "年月なし"}</span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void run(() => onUpdate(item.id, { is_closed: !item.is_closed }))}
              >
                {item.is_closed ? "計上済みを外す" : "計上済みにする"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void run(() => onUpdate(item.id, { is_active: !item.is_active }))}
              >
                {item.is_active ? "無効にする" : "有効にする"}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">売上項目がありません。</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label={`${job.code} に追加する売上項目`}
          className="w-72"
          placeholder="プロジェクトサポート（2026／11）"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Button
          size="sm"
          variant="outline"
          disabled={!name.trim()}
          onClick={() =>
            void run(async () => {
              await onCreate(job.code, name.trim());
              setName("");
            })
          }
        >
          <Plus aria-hidden="true" className="h-4 w-4" />
          売上項目を追加
        </Button>
        {message ? <span className="text-xs text-destructive">{message}</span> : null}
      </div>
    </div>
  );
}

function JobRow({
  job,
  onUpdate,
  onChangeCode,
  salesItems,
  onCreateSalesItem,
  onUpdateSalesItem,
}: {
  job: Job;
  onUpdate: SettingsPanelProps["onUpdateJob"];
  onChangeCode: SettingsPanelProps["onChangeJobCode"];
  salesItems: ZacSalesItem[];
  onCreateSalesItem: SettingsPanelProps["onCreateSalesItem"];
  onUpdateSalesItem: SettingsPanelProps["onUpdateSalesItem"];
}) {
  const [draft, setDraft] = useState<JobDraft>(() => jobDraft(job));
  const [message, setMessage] = useState<string | null>(null);
  const [showItems, setShowItems] = useState(false);
  const itemCount = salesItems.filter((item) => item.job_code === job.code && item.is_active).length;

  useEffect(() => {
    setDraft(jobDraft(job));
  }, [job]);

  const run = async (action: () => Promise<unknown>, done: string) => {
    setMessage(null);
    try {
      await action();
      setMessage(done);
    } catch (cause) {
      setMessage(errorText(cause));
    }
  };

  const save = (payload: JobUpdate, done: string) => run(() => onUpdate(job.code, payload), done);

  const saveDraft = () => {
    const { code, series_name, valid_month, ...fields } = draft;
    const nextCode = code.trim();
    if (!nextCode || nextCode === job.code) {
      return save({ ...fields, series_name: series_name.trim() || null, valid_month: valid_month.trim() || null }, "保存しました");
    }
    return run(
      () => onChangeCode(job.code, { code: nextCode, ...fields }),
      `${nextCode} を作成し、${job.code} を無効にしました`,
    );
  };

  return (
    <>
      <tr className={`border-b border-border last:border-0 ${job.is_active ? "" : "text-muted-foreground"}`}>
        <td className="py-2 pr-2">
          <Input
            aria-label={`${job.code} のジョブ ID`}
            className="font-medium"
            value={draft.code}
            onChange={(event) => setDraft({ ...draft, code: event.target.value })}
          />
        </td>
        <td className="py-2 pr-2">
          <Input
            aria-label={`${job.code} の表示名`}
            value={draft.name}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
        </td>
        <td className="py-2 pr-2">
          <Input
            aria-label={`${job.code} の zac 検索文字列`}
            placeholder="空ならジョブ ID"
            value={draft.zac_search_text}
            onChange={(event) => setDraft({ ...draft, zac_search_text: event.target.value })}
          />
        </td>
        <td className="py-2 pr-2">
          <Input
            aria-label={`${job.code} の既定の作業内容`}
            value={draft.zac_work_category}
            onChange={(event) => setDraft({ ...draft, zac_work_category: event.target.value })}
          />
        </td>
        <td className="py-2 pr-2">
          <div className="flex gap-1">
            <Input
              aria-label={`${job.code} のシリーズ名`}
              placeholder="月ごとの案件のみ"
              value={draft.series_name}
              onChange={(event) => setDraft({ ...draft, series_name: event.target.value })}
            />
            <Input
              aria-label={`${job.code} の対象年月`}
              className="w-28"
              placeholder="2026-10"
              value={draft.valid_month}
              onChange={(event) => setDraft({ ...draft, valid_month: event.target.value })}
            />
          </div>
        </td>
        <td className="py-2 whitespace-nowrap">
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => void saveDraft()}>
              保存
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowItems(!showItems)} aria-expanded={showItems}>
              売上項目（{itemCount}）
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                void save({ is_active: !job.is_active }, job.is_active ? "無効にしました" : "有効にしました")
              }
            >
              {job.is_active ? "無効にする" : "有効にする"}
            </Button>
            {message ? <span className="text-xs">{message}</span> : null}
          </div>
        </td>
      </tr>
      {showItems ? (
        <tr className="border-b border-border">
          <td colSpan={6} className="py-2">
            <SalesItemsEditor job={job} salesItems={salesItems} onCreate={onCreateSalesItem} onUpdate={onUpdateSalesItem} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

function WorkKindsSection({
  workKinds,
  onCreateWorkKind,
  onUpdateWorkKind,
}: Pick<SettingsPanelProps, "workKinds" | "onCreateWorkKind" | "onUpdateWorkKind">) {
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const run = async (action: () => Promise<void>) => {
    setMessage(null);
    try {
      await action();
    } catch (cause) {
      setMessage(errorText(cause));
    }
  };

  return (
    <section aria-labelledby="work-kinds-title" className="grid gap-3 rounded-lg border border-border bg-card p-4">
      <h2 id="work-kinds-title" className="text-sm font-semibold">
        zac の作業内容
      </h2>
      <p className="text-sm text-muted-foreground">業務明細で選ぶ作業内容の選択肢です（zac の作業登録の「作業内容」）。</p>
      <ul className="flex flex-wrap gap-2">
        {workKinds.map((kind) => (
          <li key={kind.name}>
            <button
              type="button"
              className={`rounded-full border px-3 py-1 text-xs ${kind.is_active ? "border-border" : "border-dashed text-muted-foreground line-through"}`}
              title={kind.is_active ? "クリックで無効にする" : "クリックで有効にする"}
              aria-label={`${kind.name}（${kind.is_active ? "有効" : "無効"}）`}
              onClick={() => void run(() => onUpdateWorkKind(kind.name, { is_active: !kind.is_active }))}
            >
              {kind.name}
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="追加する作業内容"
          className="w-72"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Button
          size="sm"
          variant="outline"
          disabled={!name.trim()}
          onClick={() =>
            void run(async () => {
              await onCreateWorkKind(name.trim());
              setName("");
            })
          }
        >
          <Plus aria-hidden="true" className="h-4 w-4" />
          作業内容を追加
        </Button>
        {message ? <span className="text-xs text-destructive">{message}</span> : null}
      </div>
    </section>
  );
}

function JobMasterSection({
  jobs,
  onCreateJob,
  onUpdateJob,
  onChangeJobCode,
  salesItems,
  onCreateSalesItem,
  onUpdateSalesItem,
}: Pick<
  SettingsPanelProps,
  "jobs" | "onCreateJob" | "onUpdateJob" | "onChangeJobCode" | "salesItems" | "onCreateSalesItem" | "onUpdateSalesItem"
>) {
  const [newJob, setNewJob] = useState(emptyJob);
  const [message, setMessage] = useState<string | null>(null);
  const sortedJobs = [...jobs].sort((a, b) => Number(b.is_active) - Number(a.is_active) || a.code.localeCompare(b.code));

  const add = async () => {
    setMessage(null);
    try {
      await onCreateJob(newJob);
      setNewJob(emptyJob);
      setMessage("追加しました");
    } catch (cause) {
      setMessage(errorText(cause));
    }
  };

  return (
    <section aria-labelledby="job-master-title" className="grid gap-4 rounded-lg border border-border bg-card p-4">
      <h2 id="job-master-title" className="text-sm font-semibold">
        ジョブマスタ
      </h2>
      <p className="text-sm text-muted-foreground">
        ジョブ ID は zac の案件コードです。ジョブは削除せず、使わなくなったら無効にします（過去のタスクはそのまま表示されます）。ジョブ ID を書き換えて保存すると、新しい ID のジョブを作り、元のジョブは無効にします（記録済みのタスクは元の ID のままです）。
      </p>
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
        <div className="grid gap-1">
          <Label htmlFor="new_job_code">ジョブ ID</Label>
          <Input id="new_job_code" value={newJob.code} onChange={(event) => setNewJob({ ...newJob, code: event.target.value })} />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="new_job_name">表示名</Label>
          <Input id="new_job_name" value={newJob.name} onChange={(event) => setNewJob({ ...newJob, name: event.target.value })} />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="new_job_zac_search_text">zac 検索文字列</Label>
          <Input
            id="new_job_zac_search_text"
            value={newJob.zac_search_text}
            onChange={(event) => setNewJob({ ...newJob, zac_search_text: event.target.value })}
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="new_job_zac_work_category">既定の作業内容</Label>
          <Input
            id="new_job_zac_work_category"
            value={newJob.zac_work_category}
            onChange={(event) => setNewJob({ ...newJob, zac_work_category: event.target.value })}
          />
        </div>
        <Button onClick={() => void add()} disabled={!newJob.code.trim() || !newJob.name.trim()}>
          <Plus aria-hidden="true" className="h-4 w-4" />
          追加
        </Button>
      </div>
      {message ? <p className="text-sm text-secondary">{message}</p> : null}
      {sortedJobs.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th scope="col" className="py-2 pr-2 font-medium">ジョブ ID</th>
                <th scope="col" className="py-2 pr-2 font-medium">表示名</th>
                <th scope="col" className="py-2 pr-2 font-medium">zac 検索文字列</th>
                <th scope="col" className="py-2 pr-2 font-medium">既定の作業内容</th>
                <th scope="col" className="py-2 pr-2 font-medium">シリーズ名・対象年月</th>
                <th scope="col" className="py-2 font-medium">
                  <span className="sr-only">操作</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedJobs.map((job) => (
                <JobRow
                  key={job.code}
                  job={job}
                  onUpdate={onUpdateJob}
                  onChangeCode={onChangeJobCode}
                  salesItems={salesItems}
                  onCreateSalesItem={onCreateSalesItem}
                  onUpdateSalesItem={onUpdateSalesItem}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">まだジョブがありません。</p>
      )}
    </section>
  );
}

function DefaultBreakSection({
  automationSettings,
  onSaveAutomationSettings,
}: Pick<SettingsPanelProps, "automationSettings" | "onSaveAutomationSettings">) {
  const [form, setForm] = useState<BreakSettings>({ default_break_start: "12:00", default_break_end: "13:00" });
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (automationSettings) {
      setForm({
        default_break_start: automationSettings.default_break_start,
        default_break_end: automationSettings.default_break_end,
      });
    }
  }, [automationSettings]);

  const save = async () => {
    if (!automationSettings) return;
    setMessage(null);
    try {
      await onSaveAutomationSettings(toAutomationInput(automationSettings, form));
      setMessage("保存しました");
    } catch (cause) {
      setMessage(errorText(cause));
    }
  };

  return (
    <section aria-labelledby="default-break-title" className="grid gap-4 rounded-lg border border-border bg-card p-4">
      <h2 id="default-break-title" className="text-sm font-semibold">
        既定の休憩
      </h2>
      <p className="text-sm text-muted-foreground">平日の本日の報告を開いたとき、休憩がなければ自動で入る時間帯です（HH:MM）。入った休憩は業務明細で編集できます。</p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-1">
          <Label htmlFor="default_break_start">開始</Label>
          <Input
            id="default_break_start"
            className="w-28"
            inputMode="numeric"
            value={form.default_break_start}
            onChange={(event) => setForm({ ...form, default_break_start: event.target.value })}
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="default_break_end">終了</Label>
          <Input
            id="default_break_end"
            className="w-28"
            inputMode="numeric"
            value={form.default_break_end}
            onChange={(event) => setForm({ ...form, default_break_end: event.target.value })}
          />
        </div>
        <Button variant="outline" onClick={() => void save()} disabled={!automationSettings}>
          <Save aria-hidden="true" className="h-4 w-4" />
          既定の休憩を保存
        </Button>
        {message ? <span className="text-sm text-secondary">{message}</span> : null}
      </div>
    </section>
  );
}

function HrMailSection({
  automationSettings,
  onSaveAutomationSettings,
}: Pick<SettingsPanelProps, "automationSettings" | "onSaveAutomationSettings">) {
  const [form, setForm] = useState<HrMailSettings>({ hr_mail_subject_keyword: "", hr_mail_from: "" });
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (automationSettings) {
      setForm({
        hr_mail_subject_keyword: automationSettings.hr_mail_subject_keyword,
        hr_mail_from: automationSettings.hr_mail_from,
      });
    }
  }, [automationSettings]);

  const save = async () => {
    if (!automationSettings) return;
    setMessage(null);
    try {
      await onSaveAutomationSettings(toAutomationInput(automationSettings, form));
      setMessage("保存しました");
    } catch (cause) {
      setMessage(errorText(cause));
    }
  };

  return (
    <section aria-labelledby="hr-mail-title" className="grid gap-4 rounded-lg border border-border bg-card p-4">
      <h2 id="hr-mail-title" className="text-sm font-semibold">
        人事メール（出退勤の取込）
      </h2>
      <p className="text-sm text-muted-foreground">
        laborman-agent が Outlook on the web で人事メールを検索する条件です。件名キーワードが空の場合は取り込みません。
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-1">
          <Label htmlFor="hr_mail_subject_keyword">件名キーワード</Label>
          <Input
            id="hr_mail_subject_keyword"
            className="w-48"
            placeholder="[勤怠情報]"
            value={form.hr_mail_subject_keyword}
            onChange={(event) => setForm({ ...form, hr_mail_subject_keyword: event.target.value })}
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="hr_mail_from">差出人（任意）</Label>
          <Input
            id="hr_mail_from"
            className="w-64"
            type="email"
            placeholder="hr@example.com"
            value={form.hr_mail_from}
            onChange={(event) => setForm({ ...form, hr_mail_from: event.target.value })}
          />
        </div>
        <Button variant="outline" onClick={() => void save()} disabled={!automationSettings}>
          <Save aria-hidden="true" className="h-4 w-4" />
          人事メールの条件を保存
        </Button>
        {message ? <span className="text-sm text-secondary">{message}</span> : null}
      </div>
    </section>
  );
}

function pickZacSettings(settings: AutomationSettings): ZacSettings {
  return {
    zac_submit_mode: settings.zac_submit_mode,
    entry_style: settings.entry_style,
    clip_tolerance_minutes: settings.clip_tolerance_minutes,
    gap_policy: settings.gap_policy,
    default_job_code: settings.default_job_code,
    default_work_kind: settings.default_work_kind,
    default_sales_item_id: settings.default_sales_item_id,
    description_max_length: settings.description_max_length,
  };
}

function ZacSection({
  jobs,
  salesItems,
  workKinds,
  automationSettings,
  onSaveAutomationSettings,
}: Pick<SettingsPanelProps, "jobs" | "salesItems" | "workKinds" | "automationSettings" | "onSaveAutomationSettings">) {
  const [form, setForm] = useState<ZacSettings | null>(automationSettings ? pickZacSettings(automationSettings) : null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (automationSettings) setForm(pickZacSettings(automationSettings));
  }, [automationSettings]);

  if (!form || !automationSettings) return null;

  const update = <K extends keyof ZacSettings>(key: K, value: ZacSettings[K]) => setForm({ ...form, [key]: value });
  const activeJobs = jobs.filter((job) => job.is_active || job.code === form.default_job_code);

  const save = async () => {
    setMessage(null);
    try {
      await onSaveAutomationSettings(toAutomationInput(automationSettings, form));
      setMessage("保存しました");
    } catch (cause) {
      setMessage(errorText(cause));
    }
  };

  return (
    <section aria-labelledby="zac-settings-title" className="grid gap-4 rounded-lg border border-border bg-card p-4">
      <h2 id="zac-settings-title" className="text-sm font-semibold">
        zac 連携
      </h2>
      <p className="text-sm text-muted-foreground">
        zac 登録ドラフトの算出と、laborman-agent の実行モードです。auto（保存まで自動）は社内規程の確認後に使ってください。
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="grid gap-1">
          <Label htmlFor="zac_submit_mode">実行モード</Label>
          <select
            id="zac_submit_mode"
            className={selectClass}
            value={form.zac_submit_mode}
            onChange={(event) => update("zac_submit_mode", event.target.value as ZacSettings["zac_submit_mode"])}
          >
            <option value="dry_run">dry_run（入力のみ・保存しない）</option>
            <option value="assist">assist（入力して人が保存）</option>
            <option value="auto">auto（保存まで自動）</option>
          </select>
        </div>
        <div className="grid gap-1">
          <Label htmlFor="entry_style">入力形式</Label>
          <select
            id="entry_style"
            className={selectClass}
            value={form.entry_style}
            onChange={(event) => update("entry_style", event.target.value as ZacSettings["entry_style"])}
          >
            <option value="duration">ジョブごとの時間（duration）</option>
            <option value="time_range">時刻順（time_range）</option>
          </select>
        </div>
        <div className="grid gap-1">
          <Label htmlFor="clip_tolerance_minutes">はみ出しの許容値（分）</Label>
          <Input
            id="clip_tolerance_minutes"
            type="number"
            min={0}
            value={form.clip_tolerance_minutes}
            onChange={(event) => update("clip_tolerance_minutes", Number(event.target.value))}
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="gap_policy">空き時間の扱い</Label>
          <select
            id="gap_policy"
            className={selectClass}
            value={form.gap_policy}
            onChange={(event) => update("gap_policy", event.target.value as ZacSettings["gap_policy"])}
          >
            <option value="block">エラーにする（block）</option>
            <option value="assign_default_job">既定ジョブに割り当てる</option>
          </select>
        </div>
        <div className="grid gap-1">
          <Label htmlFor="default_job_code">既定ジョブ</Label>
          <select
            id="default_job_code"
            className={selectClass}
            value={form.default_job_code ?? ""}
            onChange={(event) =>
              setForm({ ...form, default_job_code: event.target.value || null, default_sales_item_id: null })
            }
          >
            <option value="">（なし）</option>
            {activeJobs.map((job) => (
              <option key={job.code} value={job.code}>
                {job.code} {job.name}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-1">
          <Label htmlFor="default_work_kind">空き時間の作業内容</Label>
          <select
            id="default_work_kind"
            className={selectClass}
            value={form.default_work_kind ?? ""}
            onChange={(event) => update("default_work_kind", event.target.value || null)}
          >
            <option value="">（なし）</option>
            {workKinds
              .filter((kind) => kind.is_active || kind.name === form.default_work_kind)
              .map((kind) => (
                <option key={kind.name} value={kind.name}>
                  {kind.name}
                </option>
              ))}
          </select>
        </div>
        <div className="grid gap-1">
          <Label htmlFor="default_sales_item_id">空き時間の売上項目</Label>
          <select
            id="default_sales_item_id"
            className={selectClass}
            value={form.default_sales_item_id ?? ""}
            disabled={!form.default_job_code}
            onChange={(event) => update("default_sales_item_id", event.target.value || null)}
          >
            <option value="">（なし）</option>
            {salesItems
              .filter(
                (item) =>
                  item.job_code === form.default_job_code && (item.is_active || item.id === form.default_sales_item_id),
              )
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {salesItemLabel(item)}
                </option>
              ))}
          </select>
        </div>
        <div className="grid gap-1">
          <Label htmlFor="description_max_length">内容の最大長（文字）</Label>
          <Input
            id="description_max_length"
            type="number"
            min={1}
            value={form.description_max_length}
            onChange={(event) => update("description_max_length", Number(event.target.value))}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" onClick={() => void save()}>
          <Save aria-hidden="true" className="h-4 w-4" />
          zac 連携の設定を保存
        </Button>
        {message ? <span className="text-sm text-secondary">{message}</span> : null}
      </div>
    </section>
  );
}

export function SettingsPanel({
  settings,
  onSave,
  jobs,
  onCreateJob,
  onUpdateJob,
  onChangeJobCode,
  salesItems,
  workKinds,
  onCreateSalesItem,
  onUpdateSalesItem,
  onCreateWorkKind,
  onUpdateWorkKind,
  automationSettings,
  onSaveAutomationSettings,
}: SettingsPanelProps) {
  const [form, setForm] = useState<MailSettings | null>(settings);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setForm(settings);
  }, [settings]);

  if (!form) {
    return <p className="text-sm text-muted-foreground">設定を読み込み中です。</p>;
  }

  const update = (field: keyof MailSettings, value: string) => {
    setForm((current) => (current ? { ...current, [field]: value } : current));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await onSave(form);
      setMessage("保存しました");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-6">
      <form onSubmit={submit} className="grid gap-6">
        <section className="grid gap-4">
          <div>
            <h1 className="text-2xl font-semibold">設定</h1>
            <p className="mt-1 text-sm text-muted-foreground">宛先とテンプレート</p>
          </div>

          <fieldset className="grid gap-4 rounded-lg border border-border bg-card p-4">
            <legend className="px-1 text-sm font-semibold">宛先</legend>
            <p className="text-sm text-muted-foreground">
              Outlook on the webでは上司と労務MLをどちらも宛先（To）に自動設定します。
              全員のメールアドレスが受信者全員に表示されます。
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="boss_email">上司メールアドレス</Label>
                <Input
                  id="boss_email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  value={form.boss_email}
                  onChange={(event) => update("boss_email", event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="labor_ml_email">労務MLメールアドレス</Label>
                <Input
                  id="labor_ml_email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  value={form.labor_ml_email}
                  onChange={(event) => update("labor_ml_email", event.target.value)}
                />
              </div>
            </div>
          </fieldset>

          <fieldset className="grid gap-4 rounded-lg border border-border bg-card p-4">
            <legend className="px-1 text-sm font-semibold">始業メール</legend>
            <div className="grid gap-2">
              <Label htmlFor="start_subject_template">件名テンプレート</Label>
              <Input
                id="start_subject_template"
                value={form.start_subject_template}
                onChange={(event) => update("start_subject_template", event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="start_body_template">本文テンプレート</Label>
              <Textarea
                id="start_body_template"
                rows={8}
                value={form.start_body_template}
                onChange={(event) => update("start_body_template", event.target.value)}
              />
            </div>
          </fieldset>

          <fieldset className="grid gap-4 rounded-lg border border-border bg-card p-4">
            <legend className="px-1 text-sm font-semibold">終業メール</legend>
            <div className="grid gap-2">
              <Label htmlFor="end_subject_template">件名テンプレート</Label>
              <Input
                id="end_subject_template"
                value={form.end_subject_template}
                onChange={(event) => update("end_subject_template", event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="end_header_template">ヘッダテンプレート</Label>
              <Textarea
                id="end_header_template"
                rows={4}
                value={form.end_header_template}
                onChange={(event) => update("end_header_template", event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="end_body_template">本文テンプレート</Label>
              <Textarea
                id="end_body_template"
                rows={7}
                value={form.end_body_template}
                onChange={(event) => update("end_body_template", event.target.value)}
                aria-describedby="end_body_template_hint"
              />
              <p
                id="end_body_template_hint"
                className={`text-xs ${form.end_body_template.includes("{{tasks}}") ? "text-muted-foreground" : "text-destructive"}`}
              >
                {"{{tasks}}"} を追加すると業務明細が本文に入ります。ほかに {"{{tasks_by_job}}"}（ジョブ別の合計）・
                {"{{breaks}}"}（休憩）・{"{{task_total}}"}（作業の合計）・{"{{attendance_start}}"}／
                {"{{attendance_end}}"}（出退勤の実績）も使えます。
              </p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="end_footer_template">フッタテンプレート</Label>
              <Textarea
                id="end_footer_template"
                rows={4}
                value={form.end_footer_template}
                onChange={(event) => update("end_footer_template", event.target.value)}
              />
            </div>
          </fieldset>
        </section>

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={saving}>
            <Save aria-hidden="true" className="h-4 w-4" />
            {saving ? "保存中" : "保存"}
          </Button>
          {message ? <span className="text-sm text-secondary">{message}</span> : null}
        </div>
      </form>

      <div className="grid gap-4">
        <h2 className="text-lg font-semibold">業務明細・zac</h2>
        <JobMasterSection
          jobs={jobs}
          onCreateJob={onCreateJob}
          onUpdateJob={onUpdateJob}
          onChangeJobCode={onChangeJobCode}
          salesItems={salesItems}
          onCreateSalesItem={onCreateSalesItem}
          onUpdateSalesItem={onUpdateSalesItem}
        />
        <WorkKindsSection workKinds={workKinds} onCreateWorkKind={onCreateWorkKind} onUpdateWorkKind={onUpdateWorkKind} />
        <DefaultBreakSection
          automationSettings={automationSettings}
          onSaveAutomationSettings={onSaveAutomationSettings}
        />
        <HrMailSection
          automationSettings={automationSettings}
          onSaveAutomationSettings={onSaveAutomationSettings}
        />
        <ZacSection
          jobs={jobs}
          salesItems={salesItems}
          workKinds={workKinds}
          automationSettings={automationSettings}
          onSaveAutomationSettings={onSaveAutomationSettings}
        />
      </div>
    </div>
  );
}
