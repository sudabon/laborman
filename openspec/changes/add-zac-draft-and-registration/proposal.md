# Proposal

## Why

毎朝、前営業日の出退勤とジョブごとの作業を、VPN 内の社内 Web アプリ zac の業務報告へ画面操作で転記している。zac の業務報告は勤怠の公式記録を兼ねるため誤登録のコストが高い。laborman が登録内容（ドラフト）と検証結果を算出し、ホストのエージェントが `dry_run` → `assist` → `auto` の段階を踏んで zac に入力・保存できるようにする。入力元仕様は `ZAC_AUTOMATION_SPEC.md` §4.6〜4.8・§5.5〜5.6・§6・§7.4（Phase 3）。前提として `add-work-tasks-and-breaks`・`add-attendance-import` が実装済みであること。

## What Changes

- backend が勤務日ごとの zac 登録ドラフト（出退勤・休憩・実働時間・入力行）と検証結果（error / warning / info）を算出する API `GET /api/work-reports/{date}/zac-draft` を追加する。UI とエージェントは同じ結果を使う
  - タスクの出退勤範囲へのクリップ、空き時間の扱い（`block` / `assign_default_job`）、入力形式（`duration` は丸め単位・最大剰余法で合計を一致させる／`time_range` は時刻順）、休憩 0 件の日はエラー（`BREAK_MISSING`）として zac 登録を中止
- zac 連携の設定（実行モード・入力形式・丸め単位・許容値・空き時間の扱い・既定ジョブ・内容の最大長）を `automation_settings` に追加し、設定画面で編集できるようにする
- zac 連携の実行履歴 `zac_sync_runs` と、保存成功日時 `work_reports.zac_registered_at` を追加する。`status=succeeded` の記録で `zac_registered_at` を設定する
- エージェントに `run`（人事メール取込→ドラフト→zac 入力の一連の流れ）・`register`・`login zac` を追加し、`doctor` に VPN 到達性を加える
  - zac の既存入力は上書きしない、`error` のある日は保存しない、`warning` のある日は `auto` を `dry_run` に降格、「申請」「承認依頼」は操作しない、保存完了の表示を確認できたときだけ成功とする
- 「本日の報告」に zac 登録パネル（ドラフト・検証結果・最終実行・スクリーンショットのパス）を、カレンダーに zac 状態（`zac済` / `要対応`）と zac 未登録の過去営業日の強調を追加する
- 平日朝に `laborman-agent run` を定時起動する launchd の plist 例と導入手順を追加する
- （2026-10-14 の zac 画面確認による追加）タスクに zac の「作業内容」「売上項目」を持たせ、案件（ジョブ）・売上項目・作業内容の選択肢を laborman で保持する。月ごとに JOB 番号が変わる案件はシリーズとして 1 つの候補にまとめ、勤務日の年月で解決する。zac の選択肢は `laborman-agent sync-zac`（読み取り専用）で取り込む。zac の休憩は時間数の欄に、時間帯（通常・22〜24時・24〜29時）で分けて入れる。zac のサインインは macOS キーチェーンに登録したパスワードで行う
- 「本日の報告」の zac 登録パネルに「この日を zac に登録」ボタンを置く。ボタンは実行依頼（実行履歴の `requested`）を記録し、1 分間隔で起動するエージェントの `process-requests` が依頼を拾って、その日の出退勤の取込と zac 入力を行う。依頼中・実行中の表示、取り消し、結果の自動反映を行う

## Capabilities

### New Capabilities

- `zac-draft`: zac 登録ドラフトと検証結果の算出、zac 連携設定、UI とエージェントで共通の結果
- `zac-registration`: エージェントによる zac への入力・保存（実行モード・安全ガード・実行履歴・定時実行・zac のサインインと VPN 診断）

### Modified Capabilities

- `report-calendar`: 「月単位カレンダー表示」に zac 状態、「未報告日の強調表示」に zac 未登録の過去営業日、「本日の報告画面」に zac 登録パネルと売上項目・作業内容の選択を追加
- `job-master`: ジョブを zac の案件として扱い、シリーズ名・対象年月・既定の作業内容を追加。売上項目・作業内容の選択肢と、zac からの取込（`sync-zac`）を追加
- `work-task-logging`: タスクに作業内容・売上項目を追加し、業務明細の入力で初期値を入れる

## Impact

- **DB**：新規 `zac_sync_runs`・`zac_sales_items`・`zac_work_kinds`、`work_reports.zac_registered_at`、`work_tasks.work_kind`・`sales_item_id`、`jobs.series_name`・`valid_month`、`automation_settings` に zac 関連の列を追加
- **API**：`GET /api/work-reports/{date}/zac-draft`、`GET/POST /api/zac-sync-runs`、`PATCH /api/zac-sync-runs/{id}`、実行依頼の `POST /api/zac-sync-runs/requests`・`/{id}/claim`・`/{id}/cancel` を追加。`WorkReportRead` と月一覧に `zac_registered_at`・`zac_status` を追加。`/api/automation-settings` を拡張
- **Backend**：ドラフト算出を独立したモジュール（純粋関数）として追加
- **Frontend**：`TodayReport.tsx`（zac パネル）、`ReportCalendar.tsx`（zac 状態）、`SettingsPanel.tsx`（業務明細・zac 設定）
- **agent**：`zac/report_page.py`（Page Object）、`runner.py`、`cli.py`（`run`・`register`・`login zac`・`process-requests`）、`launchd/jp.sudabon.laborman-agent.plist.example`・`launchd/jp.sudabon.laborman-agent.requests.plist.example`
- **前提（運用）**：zac の画面仕様（仕様書 §13-2）、実働の計算ルール（§13-3）、社内規程の確認（§13-4。`auto` 運用の前提）
- **Docs**：`docs/` 4 文書、`agent/README.md`（段階運用のランブック）
