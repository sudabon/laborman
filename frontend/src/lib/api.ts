import type { MailCreatedRequest } from "@/lib/mail";
import type {
  AttendanceInput,
  AutomationSettings,
  AutomationSettingsInput,
  EntryConflict,
  Job,
  JobCodeChange,
  JobCreate,
  JobUpdate,
  MailSettings,
  WorkBreak,
  WorkBreakInput,
  WorkReport,
  WorkReportUpdate,
  WorkTask,
  WorkTaskInput,
  ZacDraft,
  ZacSalesItem,
  ZacSyncRun,
  ZacTaskDefault,
  ZacWorkKind,
} from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8888";

export class ApiError extends Error {
  readonly status: number;
  readonly conflicts: EntryConflict[];

  constructor(status: number, message: string, conflicts: EntryConflict[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.conflicts = conflicts;
  }
}

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") {
    return detail.message;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item: unknown) =>
        item && typeof item === "object" && "msg" in item && typeof item.msg === "string" ? item.msg : null,
      )
      .filter(Boolean);
    if (messages.length > 0) return messages.join(" / ");
  }
  return fallback;
}

async function toApiError(response: Response): Promise<ApiError> {
  const text = await response.text();
  const fallback = text || `Request failed: ${response.status}`;
  try {
    const { detail } = JSON.parse(text) as { detail?: unknown };
    const conflicts =
      detail && typeof detail === "object" && "conflicts" in detail && Array.isArray(detail.conflicts)
        ? (detail.conflicts as EntryConflict[])
        : [];
    return new ApiError(response.status, errorMessage(detail, fallback), conflicts);
  } catch {
    return new ApiError(response.status, fallback);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  getSettings: () => request<MailSettings>("/api/mail-settings"),
  saveSettings: (settings: MailSettings) =>
    request<MailSettings>("/api/mail-settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  getReport: (workDate: string) => request<WorkReport>(`/api/work-reports/${workDate}`),
  getMonthReports: (year: number, month: number) =>
    request<WorkReport[]>(`/api/work-reports?year=${year}&month=${month}`),
  updateReport: (workDate: string, payload: WorkReportUpdate) =>
    request<WorkReport>(`/api/work-reports/${workDate}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  recordStart: (workDate: string, payload: WorkReportUpdate) =>
    request<WorkReport>(`/api/work-reports/${workDate}/record-start`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  recordEnd: (workDate: string, payload: WorkReportUpdate) =>
    request<WorkReport>(`/api/work-reports/${workDate}/record-end`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  markMailCreated: (workDate: string, payload: MailCreatedRequest) =>
    request<WorkReport>(`/api/work-reports/${workDate}/mail-created`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  saveAttendance: (workDate: string, payload: AttendanceInput) =>
    request<WorkReport>(`/api/work-reports/${workDate}/attendance`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  getJobs: (params: { active?: boolean; q?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.active !== undefined) query.set("active", String(params.active));
    if (params.q) query.set("q", params.q);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<Job[]>(`/api/jobs${suffix}`);
  },
  createJob: (payload: JobCreate) =>
    request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) }),
  updateJob: (code: string, payload: JobUpdate) =>
    request<Job>(`/api/jobs/${encodeURIComponent(code)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  changeJobCode: (code: string, payload: JobCodeChange) =>
    request<Job>(`/api/jobs/${encodeURIComponent(code)}/change-code`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getWorkKinds: () => request<ZacWorkKind[]>("/api/zac-work-kinds"),
  createWorkKind: (name: string) =>
    request<ZacWorkKind>("/api/zac-work-kinds", { method: "POST", body: JSON.stringify({ name }) }),
  updateWorkKind: (name: string, payload: { is_active?: boolean }) =>
    request<ZacWorkKind>(`/api/zac-work-kinds/${encodeURIComponent(name)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  getSalesItems: () => request<ZacSalesItem[]>("/api/zac-sales-items"),
  createSalesItem: (jobCode: string, payload: { name: string; is_closed?: boolean }) =>
    request<ZacSalesItem>(`/api/jobs/${encodeURIComponent(jobCode)}/sales-items`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateSalesItem: (itemId: string, payload: { is_active?: boolean; is_closed?: boolean }) =>
    request<ZacSalesItem>(`/api/zac-sales-items/${itemId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  getZacTaskDefaults: () => request<ZacTaskDefault[]>("/api/zac-task-defaults"),

  getTasks: (workDate: string) => request<WorkTask[]>(`/api/work-reports/${workDate}/tasks`),
  createTask: (workDate: string, payload: WorkTaskInput) =>
    request<WorkTask>(`/api/work-reports/${workDate}/tasks`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateTask: (taskId: string, payload: Partial<WorkTaskInput>) =>
    request<WorkTask>(`/api/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteTask: (taskId: string) => request<void>(`/api/tasks/${taskId}`, { method: "DELETE" }),
  startTask: (workDate: string, payload: { job_code: string; description: string }) =>
    request<WorkTask>(`/api/work-reports/${workDate}/tasks/start`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  stopTask: (taskId: string) => request<WorkTask>(`/api/tasks/${taskId}/stop`, { method: "POST" }),

  getBreaks: (workDate: string) => request<WorkBreak[]>(`/api/work-reports/${workDate}/breaks`),
  createBreak: (workDate: string, payload: WorkBreakInput) =>
    request<WorkBreak>(`/api/work-reports/${workDate}/breaks`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateBreak: (breakId: string, payload: Partial<WorkBreakInput>) =>
    request<WorkBreak>(`/api/breaks/${breakId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteBreak: (breakId: string) => request<void>(`/api/breaks/${breakId}`, { method: "DELETE" }),
  startBreak: (workDate: string) =>
    request<WorkBreak>(`/api/work-reports/${workDate}/breaks/start`, { method: "POST" }),
  stopBreak: (breakId: string) => request<WorkBreak>(`/api/breaks/${breakId}/stop`, { method: "POST" }),

  getZacDraft: (workDate: string) => request<ZacDraft>(`/api/work-reports/${workDate}/zac-draft`),
  getZacRuns: (workDate: string) => request<ZacSyncRun[]>(`/api/zac-sync-runs?work_date=${workDate}&limit=10`),
  requestZacRun: (workDate: string) =>
    request<ZacSyncRun>("/api/zac-sync-runs/requests", {
      method: "POST",
      body: JSON.stringify({ work_date: workDate }),
    }),
  cancelZacRun: (runId: string) => request<ZacSyncRun>(`/api/zac-sync-runs/${runId}/cancel`, { method: "POST" }),

  getAutomationSettings: () => request<AutomationSettings>("/api/automation-settings"),
  saveAutomationSettings: (payload: AutomationSettingsInput) =>
    request<AutomationSettings>("/api/automation-settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};
