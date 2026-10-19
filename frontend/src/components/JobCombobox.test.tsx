import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { JobCombobox } from "@/components/JobCombobox";
import type { Job } from "@/types";

function job(code: string, name: string, isActive = true): Job {
  return {
    code,
    name,
    zac_search_text: "",
    zac_work_category: "",
    series_name: null,
    valid_month: null,
    is_active: isActive,
    last_used_at: null,
    created_at: null,
    updated_at: null,
  };
}

// API と同じ「最近使った順」で渡す
const recentJobs = [job("JOB-B", "社内業務"), job("JOB-A", "A社保守"), job("OLD-1", "終了案件", false), job("JOB-D", "D社開発")];

function Harness({ onCreateJob }: { onCreateJob: (code: string, name: string) => Promise<Job> }) {
  const [value, setValue] = useState("");
  return (
    <>
      <JobCombobox jobs={recentJobs} value={value} onChange={setValue} onCreateJob={onCreateJob} />
      <output data-testid="value">{value}</output>
    </>
  );
}

const optionTexts = () =>
  within(screen.getByRole("listbox")).getAllByRole("option").map((option) => option.textContent);

describe("JobCombobox", () => {
  it("lists active jobs in recently used order and filters incrementally", () => {
    render(<Harness onCreateJob={vi.fn()} />);
    const input = screen.getByRole("combobox", { name: "ジョブ" });

    fireEvent.focus(input);
    expect(optionTexts()).toEqual(["JOB-B社内業務", "JOB-AA社保守", "JOB-DD社開発"]);

    fireEvent.change(input, { target: { value: "社" } });
    expect(optionTexts()).toEqual(["JOB-B社内業務", "JOB-AA社保守", "JOB-DD社開発", "社 を登録"]);

    fireEvent.change(input, { target: { value: "a社" } });
    expect(optionTexts()).toEqual(["JOB-AA社保守", "a社 を登録"]);

    fireEvent.mouseDown(screen.getByRole("option", { name: "JOB-A A社保守" }));
    expect(screen.getByTestId("value")).toHaveTextContent("JOB-A");
    expect(input).toHaveValue("JOB-A");
  });

  it("selects with keyboard", () => {
    render(<Harness onCreateJob={vi.fn()} />);
    const input = screen.getByRole("combobox", { name: "ジョブ" });

    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByTestId("value")).toHaveTextContent("JOB-A");
  });

  it("registers an unknown job id on the spot", async () => {
    const onCreateJob = vi.fn(async (code: string, name: string) => job(code, name));
    render(<Harness onCreateJob={onCreateJob} />);
    const input = screen.getByRole("combobox", { name: "ジョブ" });

    fireEvent.change(input, { target: { value: "JOB-C" } });
    expect(screen.getByTestId("value")).toHaveTextContent("");
    fireEvent.mouseDown(screen.getByRole("option", { name: "JOB-C を登録" }));

    fireEvent.change(screen.getByLabelText("JOB-C の表示名"), { target: { value: "C社案件" } });
    fireEvent.click(screen.getByRole("button", { name: "登録" }));

    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("JOB-C"));
    expect(onCreateJob).toHaveBeenCalledWith("JOB-C", "C社案件");
    expect(screen.queryByLabelText("JOB-C の表示名")).not.toBeInTheDocument();
  });

  it("does not offer inactive jobs or registration of an existing inactive code", () => {
    render(<Harness onCreateJob={vi.fn()} />);
    const input = screen.getByRole("combobox", { name: "ジョブ" });

    fireEvent.change(input, { target: { value: "OLD-1" } });

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.getByTestId("value")).toHaveTextContent("");
  });
});
