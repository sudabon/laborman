import { Copy, ExternalLink, MailWarning, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { buildOutlookComposeUrl, getOutlookToRecipients } from "@/lib/mail";
import type { MailDraft } from "@/types";

type MailComposeDialogProps = {
  draft: MailDraft | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (draft: MailDraft) => Promise<void>;
};

async function copyText(value: string): Promise<void> {
  await navigator.clipboard.writeText(value);
}

export function MailComposeDialog({ draft, open, onOpenChange, onConfirm }: MailComposeDialogProps) {
  const [copied, setCopied] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);

  const outlookComposeUrl = useMemo(() => (draft ? buildOutlookComposeUrl(draft) : ""), [draft]);
  const isLongUrl = outlookComposeUrl.length > 1900;

  if (!draft) return null;

  const outlookToLabel = getOutlookToRecipients(draft).join(", ");

  const copy = async (label: string, value: string) => {
    await copyText(value);
    setCopied(label);
  };

  const confirm = async () => {
    setIsConfirming(true);
    try {
      window.open(outlookComposeUrl, "_blank", "noopener,noreferrer");
      await onConfirm(draft);
    } finally {
      setIsConfirming(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <section aria-labelledby="mail-dialog-title" className="max-h-[86vh] overflow-y-auto">
        <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div>
            <h1 id="mail-dialog-title" className="text-xl font-semibold">
              以下の内容でOutlook on the webメールを作成します
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              会社のMicrosoft 365アカウントでOutlook on the webにサインインしてから進み、
              作成画面でFrom（差出人）が会社メールアドレスになっていることを確認してください。
            </p>
          </div>
          <Button variant="ghost" size="icon" aria-label="閉じる" onClick={() => onOpenChange(false)}>
            <X aria-hidden="true" className="h-5 w-5" />
          </Button>
        </header>

        <div className="grid gap-4 px-5 py-5">
          <div className="rounded-md border border-accent/50 bg-accent/15 px-4 py-3 text-sm text-accent-foreground">
            <div className="flex gap-2">
              <MailWarning aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                新しいタブで作成画面を開き、labormanのタブはこのまま残ります。送信完了は検知しないため、
                Outlook on the webで内容を確認してから送信してください。登録上のCC/BCCも宛先（To）に入り、
                BCCを含む全宛先が受信者全員に表示されます。
              </p>
            </div>
          </div>

          {isLongUrl ? (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              Outlook on the webのメール作成URLが長くなっています。入力内容が引き継がれない場合は、
              下の項目をコピーして手動で入力してください。
            </div>
          ) : null}

          <dl className="grid gap-3 text-sm">
            <div>
              <dt className="font-medium text-muted-foreground">Outlookの宛先（To）</dt>
              <dd className="mt-1 break-all rounded-md border border-border bg-muted px-3 py-2">
                {outlookToLabel}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">件名</dt>
              <dd className="mt-1 break-all rounded-md border border-border bg-muted px-3 py-2">{draft.subject}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">本文</dt>
              <dd className="mt-1 whitespace-pre-wrap rounded-md border border-border bg-muted px-3 py-3 leading-7">
                {draft.body}
              </dd>
            </div>
          </dl>

          <section aria-labelledby="fallback-title" className="rounded-md border border-border px-4 py-3">
            <h2 id="fallback-title" className="text-base font-semibold">
              手動送信用コピー
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              新しいタブが開かない、Outlook on the webが表示されない、または入力内容が引き継がれない場合は、
              もう一度開くか、各項目をコピーして手動で送信してください。
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => copy("宛先（To）", outlookToLabel)}>
                <Copy aria-hidden="true" className="h-4 w-4" />
                宛先（To）
              </Button>
              <Button variant="outline" size="sm" onClick={() => copy("件名", draft.subject)}>
                <Copy aria-hidden="true" className="h-4 w-4" />
                件名
              </Button>
              <Button variant="outline" size="sm" onClick={() => copy("本文", draft.body)}>
                <Copy aria-hidden="true" className="h-4 w-4" />
                本文
              </Button>
              {copied ? <span className="self-center text-sm text-secondary">{copied}をコピーしました</span> : null}
            </div>
          </section>
        </div>

        <footer className="flex flex-col-reverse gap-2 border-t border-border px-5 py-4 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            キャンセル
          </Button>
          <Button onClick={confirm} disabled={isConfirming}>
            <ExternalLink aria-hidden="true" className="h-4 w-4" />
            {isConfirming ? "作成済みを記録中" : "Outlook on the webを開く"}
          </Button>
        </footer>
      </section>
    </Dialog>
  );
}
