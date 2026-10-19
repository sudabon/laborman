import { ApiError } from "@/lib/api";
import { automationSettings } from "@/test/fixtures";
import type { AutomationSettings, Job, WorkBreak, WorkTask, ZacSalesItem, ZacTaskDefault, ZacWorkKind } from "@/types";

// テスト用のインメモリ API。時刻は clock を進めて操作する
export function createFakeApi(workDate = "2026-10-09") {
  const state = {
    clock: `${workDate}T09:00:00+09:00`,
    tasks: [] as WorkTask[],
    breaks: [] as WorkBreak[],
    jobs: [] as Job[],
    automation: { ...automationSettings } as AutomationSettings,
    seq: 0,
    salesItems: [] as ZacSalesItem[],
    workKinds: [] as ZacWorkKind[],
    zacDefaults: [] as ZacTaskDefault[],
  };
  const now = () => new Date(state.clock).toISOString();
  const nextId = (prefix: string) => `${prefix}-${++state.seq}`;
  const iso = (value: string) => new Date(value).toISOString();

  const job = (code: string, name: string, lastUsedAt: string | null = null, isActive = true): Job => ({
    code,
    name,
    zac_search_text: "",
    zac_work_category: "",
    series_name: null,
    valid_month: null,
    is_active: isActive,
    last_used_at: lastUsedAt,
    created_at: null,
    updated_at: null,
  });

  const touch = (code: string) => {
    state.jobs = state.jobs.map((j) => (j.code === code ? { ...j, last_used_at: now() } : j));
  };
  const stopAll = () => {
    state.tasks = state.tasks.map((t) => (t.end_at ? t : { ...t, end_at: now() }));
    state.breaks = state.breaks.map((b) => (b.end_at ? b : { ...b, end_at: now() }));
  };
  const sortedJobs = () =>
    [...state.jobs].sort(
      (a, b) =>
        (b.last_used_at ? new Date(b.last_used_at).getTime() : -Infinity) -
          (a.last_used_at ? new Date(a.last_used_at).getTime() : -Infinity) || a.code.localeCompare(b.code),
    );

  const api = {
    getJobs: async (params: { active?: boolean } = {}) =>
      sortedJobs().filter((j) => params.active === undefined || j.is_active === params.active),
    createJob: async (payload: { code: string; name: string }) => {
      if (state.jobs.some((j) => j.code === payload.code)) throw new ApiError(409, "duplicate");
      const created = job(payload.code, payload.name);
      state.jobs.push(created);
      return created;
    },
    getTasks: async () => [...state.tasks].sort((a, b) => a.start_at.localeCompare(b.start_at)),
    getBreaks: async () => [...state.breaks].sort((a, b) => a.start_at.localeCompare(b.start_at)),
    startTask: async (_date: string, payload: { job_code: string; description: string }) => {
      stopAll();
      const task: WorkTask = {
        id: nextId("task"),
        work_report_id: "r",
        job_code: payload.job_code,
        description: payload.description,
        work_kind: null,
        sales_item_id: null,
        start_at: now(),
        end_at: null,
        created_at: null,
        updated_at: null,
      };
      state.tasks.push(task);
      touch(payload.job_code);
      return task;
    },
    stopTask: async (id: string) => {
      state.tasks = state.tasks.map((t) => (t.id === id ? { ...t, end_at: now() } : t));
      return state.tasks.find((t) => t.id === id)!;
    },
    createTask: async (
      _date: string,
      payload: {
        job_code: string;
        description: string;
        work_kind?: string | null;
        sales_item_id?: string | null;
        start_at: string;
        end_at: string | null;
      },
    ) => {
      const task: WorkTask = {
        id: nextId("task"),
        work_report_id: "r",
        ...payload,
        work_kind: payload.work_kind ?? null,
        sales_item_id: payload.sales_item_id ?? null,
        start_at: iso(payload.start_at),
        end_at: payload.end_at ? iso(payload.end_at) : null,
        created_at: null,
        updated_at: null,
      };
      state.tasks.push(task);
      touch(payload.job_code);
      return task;
    },
    updateTask: async (id: string, payload: Partial<WorkTask>) => {
      const current = state.tasks.find((t) => t.id === id)!;
      const updated = {
        ...current,
        ...payload,
        start_at: payload.start_at ? iso(payload.start_at) : current.start_at,
        end_at: payload.end_at === undefined ? current.end_at : payload.end_at ? iso(payload.end_at) : null,
      };
      state.tasks = state.tasks.map((t) => (t.id === id ? updated : t));
      return updated;
    },
    startBreak: async () => {
      stopAll();
      const item: WorkBreak = {
        id: nextId("break"),
        work_report_id: "r",
        start_at: now(),
        end_at: null,
        source: "manual",
        created_at: null,
        updated_at: null,
      };
      state.breaks.push(item);
      return item;
    },
    stopBreak: async (id: string) => {
      state.breaks = state.breaks.map((b) => (b.id === id ? { ...b, end_at: now() } : b));
      return state.breaks.find((b) => b.id === id)!;
    },
    createBreak: async (_date: string, payload: { start_at: string; end_at: string | null }) => {
      const item: WorkBreak = {
        id: nextId("break"),
        work_report_id: "r",
        start_at: iso(payload.start_at),
        end_at: payload.end_at ? iso(payload.end_at) : null,
        source: "manual",
        created_at: null,
        updated_at: null,
      };
      state.breaks.push(item);
      return item;
    },
    updateBreak: async (id: string, payload: { start_at?: string; end_at?: string | null }) => {
      const current = state.breaks.find((b) => b.id === id)!;
      const start = payload.start_at ?? current.start_at;
      const end = payload.end_at === undefined ? current.end_at : payload.end_at;
      const updated = { ...current, start_at: iso(start), end_at: end ? iso(end) : null };
      state.breaks = state.breaks.map((b) => (b.id === id ? updated : b));
      return updated;
    },
    getAutomationSettings: async () => state.automation,
    getSalesItems: async () => state.salesItems,
    getWorkKinds: async () => state.workKinds,
    getZacTaskDefaults: async () => state.zacDefaults,
  };

  return { api, state, job, setClock: (value: string) => (state.clock = value) };
}
