import { CalendarDays, ClipboardList, Settings } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { MailComposeDialog } from "@/components/MailComposeDialog";
import { ReportCalendar } from "@/components/ReportCalendar";
import { SettingsPanel } from "@/components/SettingsPanel";
import { TodayReport } from "@/components/TodayReport";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toISODate } from "@/lib/date";
import { buildMailDraft } from "@/lib/mail";
import { cn } from "@/lib/utils";
import type { MailDraft, MailKind, MailSettings, WorkReport, WorkReportUpdate } from "@/types";

type View = "today" | "calendar" | "settings";

const confirmationStorageKey = "laborman.sentConfirmations";

function loadConfirmations(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(confirmationStorageKey) ?? "{}") as Record<string, boolean>;
  } catch {
    return {};
  }
}

function saveConfirmations(confirmations: Record<string, boolean>) {
  localStorage.setItem(confirmationStorageKey, JSON.stringify(confirmations));
}

export default function App() {
  const today = useMemo(() => new Date(), []);
  const [view, setView] = useState<View>("today");
  const [selectedDate, setSelectedDate] = useState(today);
  const [month, setMonth] = useState(new Date(today.getFullYear(), today.getMonth(), 1));
  const [settings, setSettings] = useState<MailSettings | null>(null);
  const [report, setReport] = useState<WorkReport | null>(null);
  const [monthReports, setMonthReports] = useState<WorkReport[]>([]);
  const [draft, setDraft] = useState<MailDraft | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmations, setConfirmations] = useState<Record<string, boolean>>(() => loadConfirmations());
  const [error, setError] = useState<string | null>(null);

  const selectedISODate = toISODate(selectedDate);

  const refreshSettings = useCallback(async () => {
    setSettings(await api.getSettings());
  }, []);

  const refreshReport = useCallback(async () => {
    setReport(await api.getReport(selectedISODate));
  }, [selectedISODate]);

  const refreshMonthReports = useCallback(async () => {
    setMonthReports(await api.getMonthReports(month.getFullYear(), month.getMonth() + 1));
  }, [month]);

  useEffect(() => {
    void refreshSettings().catch((cause: Error) => setError(cause.message));
  }, [refreshSettings]);

  useEffect(() => {
    void refreshReport().catch((cause: Error) => setError(cause.message));
  }, [refreshReport]);

  useEffect(() => {
    void refreshMonthReports().catch((cause: Error) => setError(cause.message));
  }, [refreshMonthReports]);

  const updateLoadedReport = (next: WorkReport) => {
    setReport(next);
    setMonthReports((current) => {
      const without = current.filter((item) => item.work_date !== next.work_date);
      return [...without, next].sort((a, b) => a.work_date.localeCompare(b.work_date));
    });
  };

  const runApi = async (action: () => Promise<WorkReport>) => {
    setError(null);
    const next = await action();
    updateLoadedReport(next);
  };

  const saveReport = (payload: WorkReportUpdate) =>
    runApi(() => api.updateReport(selectedISODate, payload));

  const recordStart = (payload: WorkReportUpdate) =>
    runApi(() => api.recordStart(selectedISODate, payload));

  const recordEnd = (payload: WorkReportUpdate) =>
    runApi(() => api.recordEnd(selectedISODate, payload));

  const createMail = async (kind: MailKind, payload: WorkReportUpdate) => {
    if (!settings) return;
    let currentReport = report;
    if (!currentReport || currentReport.note !== payload.note || currentReport.work_style !== payload.work_style) {
      currentReport = await api.updateReport(selectedISODate, payload);
      updateLoadedReport(currentReport);
    }
    setDraft(buildMailDraft(kind, settings, currentReport));
    setDialogOpen(true);
  };

  const confirmMailCreated = async (confirmedDraft: MailDraft) => {
    const next = await api.markMailCreated(selectedISODate, {
      kind: confirmedDraft.kind,
      end_mail_body: confirmedDraft.kind === "end" ? confirmedDraft.endBodyCore : null,
    });
    updateLoadedReport(next);
  };

  const saveSettings = async (nextSettings: MailSettings) => {
    setError(null);
    setSettings(await api.saveSettings(nextSettings));
  };

  const toggleConfirmation = (key: string, checked: boolean) => {
    if (!key) return;
    setConfirmations((current) => {
      const next = { ...current, [key]: checked };
      saveConfirmations(next);
      return next;
    });
  };

  const selectDateFromCalendar = (date: Date) => {
    setSelectedDate(date);
    setView("today");
  };

  const navItems: { id: View; label: string; icon: typeof ClipboardList }[] = [
    { id: "today", label: "本日の報告", icon: ClipboardList },
    { id: "calendar", label: "カレンダー", icon: CalendarDays },
    { id: "settings", label: "設定", icon: Settings },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-medium text-primary">Laborman</p>
            <p className="text-xl font-semibold">労務報告カレンダー</p>
          </div>
          <nav aria-label="主ナビゲーション" className="flex flex-wrap gap-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <Button
                  key={item.id}
                  variant={view === item.id ? "default" : "outline"}
                  onClick={() => setView(item.id)}
                  className={cn("justify-start", view === item.id && "shadow-sm")}
                >
                  <Icon aria-hidden="true" className="h-4 w-4" />
                  {item.label}
                </Button>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-5 px-4 py-6">
        {error ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {view === "today" ? (
          <TodayReport
            date={selectedDate}
            report={report}
            settings={settings}
            sentConfirmations={confirmations}
            onSaveReport={saveReport}
            onRecordStart={recordStart}
            onRecordEnd={recordEnd}
            onCreateMail={createMail}
            onToggleConfirmation={toggleConfirmation}
            onOpenSettings={() => setView("settings")}
          />
        ) : null}

        {view === "calendar" ? (
          <ReportCalendar
            month={month}
            selectedDate={selectedDate}
            reports={monthReports}
            onMonthChange={setMonth}
            onSelectDate={selectDateFromCalendar}
            onOpenToday={() => {
              setSelectedDate(today);
              setMonth(new Date(today.getFullYear(), today.getMonth(), 1));
              setView("today");
            }}
          />
        ) : null}

        {view === "settings" ? <SettingsPanel settings={settings} onSave={saveSettings} /> : null}
      </main>

      <MailComposeDialog
        draft={draft}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onConfirm={confirmMailCreated}
      />
    </div>
  );
}
