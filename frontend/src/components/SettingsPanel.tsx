import { Save } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { MailSettings } from "@/types";

type SettingsPanelProps = {
  settings: MailSettings | null;
  onSave: (settings: MailSettings) => Promise<void>;
};

export function SettingsPanel({ settings, onSave }: SettingsPanelProps) {
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
    <form onSubmit={submit} className="grid gap-6">
      <section className="grid gap-4">
        <div>
          <h1 className="text-2xl font-semibold">設定</h1>
          <p className="mt-1 text-sm text-muted-foreground">宛先とテンプレート</p>
        </div>

        <fieldset className="grid gap-4 rounded-lg border border-border bg-card p-4">
          <legend className="px-1 text-sm font-semibold">宛先</legend>
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
            <div className="grid gap-2">
              <Label htmlFor="cc_emails">CC</Label>
              <Input
                id="cc_emails"
                type="text"
                inputMode="email"
                value={form.cc_emails}
                onChange={(event) => update("cc_emails", event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="bcc_emails">BCC</Label>
              <Input
                id="bcc_emails"
                type="text"
                inputMode="email"
                value={form.bcc_emails}
                onChange={(event) => update("bcc_emails", event.target.value)}
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
            />
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
  );
}
