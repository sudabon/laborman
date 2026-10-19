import { Plus } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Job } from "@/types";

type JobComboboxProps = {
  id?: string;
  label?: string;
  // 最近使った順（API の並び順）で渡す
  jobs: Job[];
  value: string;
  onChange: (code: string) => void;
  onCreateJob: (code: string, name: string) => Promise<Job>;
  disabled?: boolean;
};

function matches(job: Job, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return job.code.toLowerCase().includes(needle) || job.name.toLowerCase().includes(needle);
}

export function JobCombobox({ id, label = "ジョブ", jobs, value, onChange, onCreateJob, disabled }: JobComboboxProps) {
  const generatedId = useId();
  const inputId = id ?? `job-combobox-${generatedId}`;
  const listboxId = `${inputId}-listbox`;
  const [query, setQuery] = useState(value);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [registering, setRegistering] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);

  // 再開・編集などで外から値が変わったら入力欄に反映する
  useEffect(() => {
    if (value) setQuery(value);
  }, [value]);

  const selectedJob = jobs.find((job) => job.code === value);
  const trimmedQuery = query.trim();
  // 無効化したジョブは新規タスクの候補に出さない
  const candidates = useMemo(
    () => jobs.filter((job) => job.is_active && matches(job, query)),
    [jobs, query],
  );
  const canRegister = trimmedQuery !== "" && !jobs.some((job) => job.code === trimmedQuery);

  const select = (job: Job) => {
    onChange(job.code);
    setQuery(job.code);
    setOpen(false);
    setActiveIndex(-1);
  };

  const startRegistering = () => {
    setRegistering(trimmedQuery);
    setNewName("");
    setError(null);
    setOpen(false);
  };

  const register = async () => {
    if (!registering || !newName.trim()) return;
    try {
      const job = await onCreateJob(registering, newName.trim());
      setRegistering(null);
      select(job);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const optionCount = candidates.length + (canRegister ? 1 : 0);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => Math.min(current + 1, optionCount - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter" && open && activeIndex >= 0) {
      event.preventDefault();
      if (activeIndex < candidates.length) select(candidates[activeIndex]);
      else startRegistering();
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative grid gap-1">
      <label htmlFor={inputId} className="text-sm font-medium">
        {label}
      </label>
      <Input
        id={inputId}
        role="combobox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={open && activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
        autoComplete="off"
        placeholder="ジョブ ID・表示名で検索"
        value={query}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          setActiveIndex(-1);
          const exact = jobs.find((job) => job.is_active && job.code === event.target.value.trim());
          onChange(exact ? exact.code : "");
        }}
      />
      {selectedJob ? <span className="text-xs text-muted-foreground">{selectedJob.name}</span> : null}
      {open && optionCount > 0 ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={`${label}の候補`}
          className="absolute top-full z-10 mt-1 max-h-64 w-full min-w-64 overflow-y-auto rounded-md border border-border bg-card py-1 text-sm shadow-lg"
        >
          {candidates.map((job, index) => (
            <li
              key={job.code}
              id={`${listboxId}-${index}`}
              role="option"
              aria-selected={job.code === value}
              className={`cursor-pointer px-3 py-2 ${index === activeIndex ? "bg-muted" : "hover:bg-muted"}`}
              // blur より先に選択させる
              onMouseDown={(event) => {
                event.preventDefault();
                select(job);
              }}
            >
              <span className="font-medium">{job.code}</span>
              <span className="ml-2 text-muted-foreground">{job.name}</span>
            </li>
          ))}
          {canRegister ? (
            <li
              id={`${listboxId}-${candidates.length}`}
              role="option"
              aria-selected={false}
              className={`cursor-pointer px-3 py-2 text-primary ${
                activeIndex === candidates.length ? "bg-muted" : "hover:bg-muted"
              }`}
              onMouseDown={(event) => {
                event.preventDefault();
                startRegistering();
              }}
            >
              {trimmedQuery} を登録
            </li>
          ) : null}
        </ul>
      ) : null}
      {registering ? (
        <div className="grid gap-2 rounded-md border border-border bg-muted p-2">
          <label htmlFor={`${inputId}-new-name`} className="text-xs font-medium">
            {registering} の表示名
          </label>
          <div className="flex gap-2">
            <Input
              id={`${inputId}-new-name`}
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void register();
                }
              }}
            />
            <Button size="sm" className="h-10" onClick={() => void register()} disabled={!newName.trim()}>
              <Plus aria-hidden="true" className="h-4 w-4" />
              登録
            </Button>
            <Button size="sm" variant="ghost" className="h-10" onClick={() => setRegistering(null)}>
              取消
            </Button>
          </div>
          {error ? (
            <p role="alert" className="text-xs text-destructive">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
