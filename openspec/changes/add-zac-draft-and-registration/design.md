# Design

## Context

- 前提：`add-work-tasks-and-breaks`（タスク・休憩・ジョブ・`automation_settings`・`app_timezone`）と `add-attendance-import`（出退勤実績・`attendance_break_minutes`・`agent/` の共通基盤・`login owa`・`fetch-attendance`・`doctor`）が実装済み。
- zac は VPN 内の社内 Web アプリで、業務報告は勤怠の公式記録を兼ねる。画面仕様（URL・項目・保存と申請の区別・既存入力の見え方）は未確定（仕様書 §13-2）。
- 全体設計の出典は `ZAC_AUTOMATION_SPEC.md`（§3 の D2〜D4、§4.6〜4.8、§7）。振る舞いは specs/ を参照。

## Goals / Non-Goals

**Goals:**

- 業務ルール（クリップ・空き時間・丸め・検証）を backend の純粋関数に集約し、pytest で網羅的に検証できるようにする（エージェントは「入力係」に限定）
- zac の画面仕様が未確定でも、セレクタ・URL を設定で与えるだけで動く Page Object にする
- 誤登録を構造的に起こしにくくする（保存以外の確定操作を Page Object に持たせない、既存入力・error・warning のガード）

**Non-Goals:**

- zac の「申請」「承認依頼」の自動化、有給・休暇申請
- Slack 通知（macOS 通知のみ）
- モードの段階運用（`dry_run` 2 週間 → `assist` → `auto`）のシステムによる強制。運用ルールとしてランブックに記載する

## Decisions

### D1. ドラフト算出は純粋関数モジュール

`backend/app/zac_draft.py` に `build_zac_draft(report, tasks, breaks, jobs, settings, tz) -> ZacDraft` を置く。DB アクセスはルート側で行い、関数は入力だけから結果を決める。手順は仕様書 §4.6 の 1〜7（出退勤 → 範囲内の休憩 → クリップ → 実働 `W` → 空き時間 → 入力行 → 検証）。検証の順序に依存しないよう、全コードを一度に集めてから `registrable`・`auto_allowed` を導出する。

- 出退勤がない・休暇の日は、入力行を空にして該当 error だけを返す（以降の手順は行わない）。
- 範囲内の休憩：出退勤と重なる部分だけを数える（はみ出した休憩は切り詰める）。
- 空き時間は、出退勤の範囲からタスク（クリップ後）と休憩を差し引いた区間の合計。1 分未満は無視する。

**代替案**：フロントエンドでも算出する案は、UI とエージェントの結果が乖離しうるため採らない（UI は API の結果を表示するだけ）。

### D2. `duration` の丸め（最大剰余法）

1. ジョブごとの分数 `m_j`（クリップ後＋`assign_default_job` の割当）を求める
2. 目標合計 `T = floor(W / unit) * unit`
3. `f_j = floor(m_j / unit) * unit`、剰余 `r_j = m_j - f_j`
4. 不足 `T - Σf_j` を `unit` ずつ、`r_j` の大きい順（同値は `m_j` の大きい順、次にジョブ ID 順）に配分する
5. `Σ` が `T` と一致しなければ `TOTAL_MISMATCH`（不具合検知用）

`block` で空き時間がある場合は `Σm_j < W` となり配分が成立しないことがあるが、`UNCOVERED_TIME`（error）で登録不可になるため、入力行は参考値として返す。`time_range` では丸めを行わず、クリップ後の時刻をそのまま使う。

### D3. 設定と実行履歴のテーブル

- `automation_settings` に仕様書 §5.6 の残りの列（`zac_submit_mode`・`entry_style`・`time_unit_minutes`・`clip_tolerance_minutes`・`gap_policy`・`default_job_code`〔FK → `jobs.code`〕・`description_max_length`）を CHECK 制約付きで追加する。`time_unit_minutes` は 1〜60 かつ 60 の約数に限定する。
- `zac_sync_runs` は仕様書 §5.5 のとおり（`entries` は `sa.JSON`）。`work_reports.zac_registered_at` を追加する。
- `POST /api/zac-sync-runs` は `status=running`・`started_at=now` で作成、`PATCH /api/zac-sync-runs/{id}` で `status`・`message`・`entries`・`screenshot_path`・`finished_at` を更新。`succeeded` への更新時に同一トランザクションで対象日の `zac_registered_at = now` を設定する（報告がなければ get-or-create）。

### D4. `zac_status` の導出と N+1 回避

`zac_status` は `registered`（`zac_registered_at` あり）／`needs_action`（最新 run の status が `validation_failed`・`needs_login`・`failed`・`already_registered_in_zac`）／`null`。月一覧では、対象月の `zac_sync_runs` を `work_date` ごとの最新 `started_at` で絞るサブクエリ 1 本を `work_reports` に外部結合して取得する。`WorkReportRead` に `zac_registered_at`・`zac_status` を追加する。

### D5. エージェントの実行フロー（`runner.py`）

仕様書 §4.7 のシーケンスに従う。各分岐で `zac_sync_runs` を記録し、終了コードを決める。

| 状況 | 記録する状態 | 終了コード |
|------|-------------|-----------|
| 登録済み（`--force` なし） | 記録しない | 0 |
| ロック取得失敗 | 記録しない | 0 |
| VPN 未到達 | `vpn_unreachable` | 2 |
| 人事メール未着 | `hr_mail_not_found` | 2 |
| サインイン切れ（OWA/zac） | `needs_login` | 3 |
| ドラフトに error | `validation_failed` | 3 |
| zac に既存入力 | `already_registered_in_zac` | 3 |
| `dry_run`（`auto` 降格を含む） | `dry_run_done` | 0 |
| `assist` 時間切れ | `awaiting_user` | 3 |
| 保存完了を確認 | `succeeded` | 0 |
| 保存未確認・エラー表示 | `failed` | 3 |

- 人事メールの取込は Phase 2 の `fetch-attendance` の処理を関数として再利用する。
- 再試行状態（終了コード 2）の通知は、設定 `[schedule] notify_retry_after`（既定 `"13:00"`）以降の起動でのみ行う。launchd の最終回（13:20）がこれに当たる。
- `assist` は画面付きブラウザが必要なため、`--headed` 未指定でも `assist` では `headless=False` で起動する。

### D6. zac の Page Object（`zac/report_page.py`）

- 公開する操作は `open(date)`・`is_login_page()`・`has_existing_entries()`・`fill(draft)`・`screenshot(path)`・`click_save()`・`wait_saved(timeout)`・`has_error()` に限定する。「申請」等の要素を扱うメソッドは作らず、`click_save()` は設定の `save_button` セレクタだけをクリックする。
- URL（`report_url_template`）とセレクタ（`[zac.selectors]`）はすべて設定から与える。`fill()` は `entry_style` に応じて行を追加・入力し、案件の選択は `zac_search_text` で検索して最初の候補を選ぶ。
- テストは `agent/tests/fixtures/zac/*.html`（空の画面・既存入力あり・保存完了・エラー・ログイン画面）の静的モックに対して Playwright で行い、実システムには接続しない。

### D7. スクリーンショット

`logs.dir/screenshots/<date>_<run_id>.png` に権限 `600` で保存し、Phase 2 のログ期限削除の対象に含める。パスは `zac_sync_runs.screenshot_path` に記録する（画像は DB に入れない）。

### D8. 画面

- 「本日の報告」の zac パネルは `GET zac-draft` と `GET zac-sync-runs?work_date=` の結果を表示するだけで、算出は行わない。業務明細・出退勤の変更後に再取得する。
- カレンダーは月一覧の `zac_status` と `zac_registered_at` を表示し、強調判定に使う。
- 設定画面に「業務明細・zac」セクション（D3 の項目）を追加する。

### D9. 定時実行

`agent/launchd/jp.sudabon.laborman-agent.plist.example` に平日 9:20・10:20・11:20・13:20 の `StartCalendarInterval` を列挙し、`SETUP_GUIDE.md` に `launchctl bootstrap gui/$(id -u) ...` での導入・解除手順を書く。`install-launchd` コマンドは作らない（手順で十分なため）。

## Risks / Trade-offs

- [zac の画面仕様が想定と異なり、入力形式（時間数／時刻）が合わない（§13-2）] → `entry_style` を両方実装し、セレクタ・URL を設定で与える。確定後に片方へ固定してよい
- [丸めの単位・方向が zac のルールと違う（§13-3）] → 単位は設定で変更可能。方向（切り捨て）が違う場合は D2 の目標合計の計算だけを変えればよいよう、関数を分離しておく
- [自動操作が社内規程に抵触する（§13-4）] → `auto` 運用前に情報システム部門へ確認する。初期値は `dry_run` とし、確認が取れるまで `assist` までに留める
- [zac の画面変更で誤った欄に入力される] → 既存入力の検知、保存完了表示の確認、`dry_run` のスクリーンショット確認、`warning` 時の自動降格で多重に防ぐ
- [`assist` 中に利用者が気付かず時間切れになる] → `awaiting_user` を記録・通知し、カレンダーの「要対応」には含めないが次回起動で再実行される（未登録のため）
- [スクリーンショットに業務情報が残る] → 権限 `600`・期限削除・FileVault 前提

## Migration Plan

1. Alembic マイグレーションで `zac_sync_runs` 作成、`work_reports.zac_registered_at`・`automation_settings` の列を追加する
2. `task build && task start` で backend・SPA を更新する
3. 実画面で `playwright codegen` を使い zac のセレクタ・URL を採取して `config.toml` に設定 → `laborman-agent login zac` → `doctor`
4. `run --mode dry_run --headed` で確認後、launchd を導入し、段階運用（`dry_run` → `assist` → `auto`）に入る
5. ロールバック：launchd を解除し、`alembic downgrade -1`。zac 側の保存済みデータは手作業で扱う（エージェントは削除操作を持たない）

## Open Questions

- zac の業務報告画面の URL・日付指定・項目・保存完了／既存入力の見え方・ログイン方式（仕様書 §13-2）：設定値（URL・セレクタ）と `entry_style` の既定値の確定に使う
- 実働と工数合計の一致が zac で必須か、丸めの単位と方向（§13-3）：`time_unit_minutes` の既定値に影響する
- 社内規程上、自動操作と業務データのローカル保存が許されるか（§13-4）：`auto` 運用の可否に影響する（実装範囲は変わらない）
- laborman のジョブ ID と zac の案件の対応（§13-8）：`zac_search_text` で吸収できる想定。別名表が必要なら運用で `zac_search_text` を設定する
