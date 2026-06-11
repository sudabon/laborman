import { CalendarDays } from "lucide-react";
import { DayButtonProps, DayPicker } from "react-day-picker";
import { ja } from "react-day-picker/locale";

import { Button } from "@/components/ui/button";
import {
  formatCalendarWeekdayHeader,
  isPastWeekday,
  isReportingWeekday,
  isSameDate,
  toISODate,
} from "@/lib/date";
import { statusLabels } from "@/lib/mail";
import { cn } from "@/lib/utils";
import type { ReportStatus, WorkReport } from "@/types";

type ReportCalendarProps = {
  month: Date;
  selectedDate: Date;
  reports: WorkReport[];
  onMonthChange: (month: Date) => void;
  onSelectDate: (date: Date) => void;
  onOpenToday: () => void;
};

const shortStatusLabels: Record<ReportStatus, string> = {
  not_started: "未報告",
  start_recorded: "始業",
  start_mail_created: "始業メール",
  end_recorded: "終業",
  end_mail_created: "メール作成済み",
};

function statusTone(status: ReportStatus, isIncompletePast: boolean): string {
  if (isIncompletePast) return "border-destructive/40 bg-destructive/10 text-destructive";
  if (status === "end_mail_created") return "border-secondary/40 bg-secondary/10 text-secondary";
  if (status === "end_recorded") return "border-primary/40 bg-primary/10 text-primary";
  if (status === "start_mail_created") return "border-accent/50 bg-accent/15 text-accent-foreground";
  if (status === "start_recorded") return "border-border bg-muted text-foreground";
  return "border-border bg-card text-muted-foreground";
}

export function ReportCalendar({
  month,
  selectedDate,
  reports,
  onMonthChange,
  onSelectDate,
  onOpenToday,
}: ReportCalendarProps) {
  const reportByDate = new Map(reports.map((report) => [report.work_date, report]));

  const getStatus = (date: Date): ReportStatus => reportByDate.get(toISODate(date))?.status ?? "not_started";

  function StatusDayButton(props: DayButtonProps) {
    const dayDate = props.day.date;
    const status = getStatus(dayDate);
    const reportingDay = isReportingWeekday(dayDate);
    const incompletePast = isPastWeekday(dayDate) && status !== "end_mail_created";
    const selected = isSameDate(dayDate, selectedDate);
    const outside = Boolean(props.modifiers.outside);
    const className = cn(
      "flex h-20 w-full flex-col items-start justify-between rounded-md border px-2 py-2 text-left text-xs transition-colors",
      statusTone(status, incompletePast),
      selected && "ring-2 ring-primary ring-offset-1",
      outside && "opacity-45",
      props.className,
    );

    return (
      <button
        {...props}
        type="button"
        className={className}
        aria-label={
          reportingDay
            ? `${dayDate.toLocaleDateString("ja-JP")} ${statusLabels[status]}`
            : `${dayDate.toLocaleDateString("ja-JP")} 報告不要`
        }
      >
        <span className="text-sm font-semibold">{dayDate.getDate()}</span>
        <span className="leading-tight">{reportingDay ? shortStatusLabels[status] : ""}</span>
      </button>
    );
  }

  return (
    <section className="grid gap-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">カレンダー</h1>
          <p className="mt-1 text-sm text-muted-foreground">月単位の報告状況</p>
        </div>
        <Button onClick={onOpenToday}>
          <CalendarDays aria-hidden="true" className="h-4 w-4" />
          本日の報告
        </Button>
      </div>

      <div className="w-full rounded-lg border border-border bg-card p-4">
        <DayPicker
          className="w-full"
          locale={ja}
          mode="single"
          month={month}
          selected={selectedDate}
          showOutsideDays
          onMonthChange={onMonthChange}
          onSelect={(date) => date && onSelectDate(date)}
          classNames={{
            months: "w-full max-w-none",
            month: "w-full",
            month_grid: "w-full",
          }}
          components={{ DayButton: StatusDayButton }}
          formatters={{
            formatWeekdayName: (weekday) => formatCalendarWeekdayHeader(weekday),
          }}
          labels={{
            labelNext: () => "翌月",
            labelPrevious: () => "前月",
            labelWeekday: (date) =>
              isReportingWeekday(date)
                ? formatCalendarWeekdayHeader(date)
                : date.getDay() === 0
                  ? "日曜日（報告不要）"
                  : "土曜日（報告不要）",
          }}
        />
      </div>

      <ul className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-5">
        {Object.entries(statusLabels).map(([status, label]) => (
          <li key={status} className={cn("rounded-md border px-3 py-2", statusTone(status as ReportStatus, false))}>
            {label}
          </li>
        ))}
        <li className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-destructive">
          過去日の未完了
        </li>
      </ul>
    </section>
  );
}
