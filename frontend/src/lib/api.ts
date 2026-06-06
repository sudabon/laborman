import type { MailCreatedRequest } from "@/lib/mail";
import type { MailSettings, WorkReport, WorkReportUpdate } from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
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
};
