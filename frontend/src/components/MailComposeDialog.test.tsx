import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MailComposeDialog } from "@/components/MailComposeDialog";
import { buildOutlookComposeUrl } from "@/lib/mail";
import type { MailDraft } from "@/types";

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: { open: boolean; children: ReactNode }) =>
    open ? <div role="dialog">{children}</div> : null,
}));

const draft: MailDraft = {
  kind: "start",
  to: ["boss@example.com"],
  cc: ["labor@example.com"],
  bcc: ["audit@example.com"],
  subject: "始業 報告",
  body: "始業しました。\n本日もよろしくお願いいたします。",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MailComposeDialog", () => {
  it("opens an isolated Outlook tab before recording that the mail was created", async () => {
    const events: string[] = [];
    const originalLocation = window.location.href;
    const openWindow = vi.spyOn(window, "open").mockImplementation(() => {
      events.push("open");
      return null;
    });
    const onConfirm = vi.fn(async () => {
      events.push("confirm");
    });

    render(
      <MailComposeDialog
        draft={draft}
        open
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />,
    );

    expect(screen.getByText(/会社のMicrosoft 365アカウントでOutlook on the webにサインイン/)).toBeVisible();
    expect(screen.getByText(/From（差出人）が会社メールアドレス/)).toBeVisible();
    expect(screen.getByText(/登録上のCC\/BCCも宛先（To）に入り/)).toBeVisible();
    expect(screen.getByText("boss@example.com, labor@example.com, audit@example.com")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Outlook on the webを開く" }));

    expect(events).toEqual(["open", "confirm"]);
    expect(openWindow).toHaveBeenCalledWith(
      buildOutlookComposeUrl(draft),
      "_blank",
      "noopener,noreferrer",
    );
    expect(window.location.href).toBe(originalLocation);
    expect(onConfirm).toHaveBeenCalledWith(draft);
    await waitFor(() => expect(screen.getByRole("button", { name: "Outlook on the webを開く" })).toBeEnabled());
  });
});
