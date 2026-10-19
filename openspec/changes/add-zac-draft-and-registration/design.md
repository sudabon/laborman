# Design

## Context

- 前提：`add-work-tasks-and-breaks`（タスク・休憩・ジョブ・`automation_settings`・`app_timezone`）と `add-attendance-import`（出退勤実績・`agent/` の共通基盤・`login owa`・`fetch-attendance`・`doctor`）が実装済み。
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

- 公開する操作は `open(date)`・`is_login_page()`・`has_existing_entries()`・`fill(draft)`・`fill_breaks(breaks)`・`screenshot(path)`・`click_save()`・`wait_saved(timeout)`・`has_error()` に限定する。「申請」等の要素を扱うメソッドは作らず、`click_save()` は設定の `save_button` セレクタだけをクリックする。
- URL（`report_url_template`）とセレクタ（`[zac.selectors]`）はすべて設定から与える。`fill()` は `entry_style` に応じて行を追加・入力し、案件の選択は `zac_search_text` で検索して最初の候補を選ぶ。
- 休憩は工数明細の行ではなく、勤怠欄の休憩の**時間数**に入れる（2026-10-14 の画面確認で、zac の休憩は時刻帯ではなく時間数の欄と判明）。`fill_breaks()` は範囲内の休憩を時間帯で分け（D12）、`TimeBreak`・`TimeBreak3`・`TimeBreak4` に `H:MM` で入れる。
- テストは `agent/tests/fixtures/zac/*.html`（空の画面・既存入力あり・保存完了・エラー・ログイン画面）の静的モックに対して Playwright で行い、実システムには接続しない。

### D7. スクリーンショット

`logs.dir/screenshots/<date>_<run_id>.png` に権限 `600` で保存し、Phase 2 のログ期限削除の対象に含める。パスは `zac_sync_runs.screenshot_path` に記録する（画像は DB に入れない）。

### D8. 画面

- 「本日の報告」の zac パネルは `GET zac-draft` と `GET zac-sync-runs?work_date=` の結果を表示するだけで、算出は行わない。業務明細・出退勤の変更後に再取得する。
- カレンダーは月一覧の `zac_status` と `zac_registered_at` を表示し、強調判定に使う。
- 設定画面に「業務明細・zac」セクション（D3 の項目）を追加する。

### D9. 定時実行

`agent/launchd/jp.sudabon.laborman-agent.plist.example` に平日 9:20・10:20・11:20・13:20 の `StartCalendarInterval` を列挙し、`SETUP_GUIDE.md` に `launchctl bootstrap gui/$(id -u) ...` での導入・解除手順を書く。`install-launchd` コマンドは作らない（手順で十分なため）。

### D10. 画面からの実行依頼（`process-requests`）

画面（Docker 内の laborman から配信）からホストのコマンドは直接起動できないため、実行履歴を依頼のキューとして使う。

- `POST /api/zac-sync-runs/requests`（本文 `{ work_date }`）で `status=requested`・`mode=設定の実行モード`・`started_at=now` の行を作る。同じ勤務日に `requested`・`running` があれば `409`。`POST /api/zac-sync-runs/{id}/cancel` は `requested` のときだけ `cancelled` にする（それ以外は `409`）。
- `POST /api/zac-sync-runs/{id}/claim` は `requested` → `running` を条件付き更新（`UPDATE … WHERE status='requested'`）で行い、取得できなければ `409`。これで launchd の重複起動や定時の `run` と同時に動いても、同じ依頼を二重に実行しない。
- エージェントの `process-requests` は依頼を古い順に取得し、`claim` に成功したものだけ D5 の流れを実行する。D5 の各状態は、新しい行を作らずに依頼の行を `PATCH` で更新する（`runner` に既存の run ID を渡せるようにする）。依頼がなければブラウザを起動しない。多重起動ロックは `run` と共有する（ロック中は何もせず 0、依頼は次回に拾う）。
- `agent/launchd/jp.sudabon.laborman-agent.requests.plist.example` に `StartInterval` 60 秒で `process-requests` を起動する例を置く。押してから処理開始まで最大 1 分程度待つ。
- 画面の「この日を zac に登録」は、`zac_registered_at` のある日は無効にする。ドラフトの error では無効にしない（`ATTENDANCE_MISSING` は実行時の人事メール取込で解消しうるため。エージェントが実行時に再検証する）。依頼中・実行中は 10 秒ごとに `GET zac-sync-runs?work_date=` を再取得して状態を更新する。
- 前提：Mac がログイン中で、Docker と laborman が起動していること（画面付きブラウザが必要な `assist` でも動くよう、launchd は GUI セッションの LaunchAgent とする）。

**代替案**：エージェントを常駐させてローカル HTTP で画面から直接呼ぶ案は、待ち時間はなくなるが常駐プロセスの管理と CORS・認証の考慮が増え、結果の記録も別途必要になるため採らない。

### D11. 作業内容・案件・売上項目のデータモデル（2026-10-14 追加）

zac の工数 1 行は「作業内容 × 案件（JOB 番号）× 売上項目」で、売上項目は案件ごとの選択肢である。laborman の 1 タスクにこの 3 つを持たせ、zac にはタスクで選んだ値で登録する。終業メール（`{{tasks}}`）は従来どおり時刻・ジョブ ID・内容だけを使う。

- `jobs`（案件）：既存の列に `series_name`（NULL 可）・`valid_month`（`YYYY-MM`、NULL 可）を追加。既存の `zac_work_category` は「既定の作業内容」として使う。`zac_search_text` が空ならジョブ ID で検索する。
- `zac_sales_items`（新規）：`id`・`job_code`（FK、ON UPDATE CASCADE）・`name`・`valid_month`（NULL 可）・`is_closed`（売上計上済み）・`is_active`・`sort_order`。`UNIQUE (job_code, name)`。
- `zac_work_kinds`（新規）：`name`（PK）・`is_active`・`sort_order`。
- `work_tasks`：`work_kind`（FK → `zac_work_kinds.name`、NULL 可）・`sales_item_id`（FK → `zac_sales_items.id`、NULL 可）を追加。保存時に `sales_item_id` がタスクのジョブの売上項目であることを検証する（違えば 422）。NULL 可にするのは既存のタスク（9/1〜10/13 の記録）を壊さないため。zac のドラフトでは未設定を error にする。
- 年月の読み取り：`（2026／10）`・`(26/10)`・`（2026年8月分）`・`(2026/09-2026/12)`（範囲は対象年月なしとする）を NFKC 正規化してから正規表現で読む。backend の関数 `parse_valid_month(name)` に集約し、取込と手入力の両方で使う。
- 月ごとの案件（パターン C）：`series_name` と `valid_month` を持つジョブを、画面ではシリーズ名で 1 候補にまとめる。保存時にフロントエンドが勤務日の年月のジョブに解決する（なければ保存しない）。backend はタスクのジョブの `valid_month` が勤務日の年月と違えばドラフトで `JOB_MONTH_MISMATCH` を出す（取り違え防止）。
- 初期値：売上項目は ①勤務日の年月の項目（計上済みを除く）→ ②そのジョブで前回使った項目 → ③選択肢が 1 つならそれ → ④空。作業内容は ①そのジョブで前回使った作業内容 → ②ジョブの既定の作業内容 → ③空。「前回使った」は `work_tasks` から求める（別テーブルは持たない）。
- 初期データ：2026-10-14 に画面で記録した `backend/seed/zac_masters_2026-10-14.json`（作業内容 26 件・案件 5 件・売上項目）を、取込 API で投入する。

**代替案**：売上項目をタスクに文字列で持つ案は、zac の表記揺れ・計上済みの判定・案件との対応が検証できないため採らない。

### D12. zac の画面の対応表（2026-10-14 に Claude in Chrome で確認）

| 用途 | 要素 |
|------|------|
| 業務報告画面 | `{base_url}/b/daily_report/{YYYY-MM-DD}`（`base_url = https://tribeck2.zac.ai/tribeck2`） |
| サインイン画面 | `/User/user_logon.asp`。`#username`（ログイン ID）・`#password`・`form[action="user_check.asp"]` の送信 |
| 出社・退社時刻 | `zac-time-duration-input[formcontrolname=TimeIn] input`・`[formcontrolname=TimeOut] input` |
| 休憩（時間数） | `TimeBreak`（通常。初期値 1:00）・`TimeBreak3`（22〜24時）・`TimeBreak4`（24〜29時）。`TimeBreak5`（深夜外所定内休憩時間（明日））は使わない |
| 既存入力 | 作業工数の `tr.zac-row.cdk-row.data-row` が 1 行以上、または「日報確定済」の表示 |
| 作業登録 | 「作業登録」ボタン → ダイアログ。`zac-entity-dropdown[formcontrolname=IdSagyouNaiyou]`（作業内容）→ `zac-entity-select-v2[formcontrolname=IdProject]`（案件。入力欄に JOB 番号を入れ、候補 `div.entity-select-menu-container zac-option` から選ぶ）→ `zac-entity-dropdown-v2[formcontrolname=IdProjectSales]`（売上項目）→ `TimeRequired`（所要時間）・`TimeMove`（内移動時間）・`zac-textarea[formcontrolname=Memo]`（備考）→「登録」 |
| 保存 | 画面上部の「保存」（`button.basic`）。「確定」（`button.success`。保存＋内容確定）・「確定解除」「月報確定」は押さない |
| 保存完了 | 画面にメッセージは出ない（2026-10-14 に利用者の保存を観察）。「保存」は `POST {base_url}/b/api/v2/daily_report/daily_reports/{YYYY-MM-DD}/save` を送り、成功時は 200。この通信の成功（2xx）で保存完了、4xx・5xx で失敗とする。利用者が「確定」した場合は「日報確定済」の表示でも完了とする |
| 入力済みの行（保存前） | 所要時間と備考は行の中の入力欄の値（`input`・`textarea`）で、文字列としては表に出ない |

- ボタンは文字の前後に空白などを含み、Playwright の `:text-is` では一致しない（2026-10-14 の `sync-zac` の実行で判明）。「登録」は `button.success:has-text('登録')`、「キャンセル」は `button.basic:has-text('キャンセル')`、「保存」は DOM 上に 2 つあるため `button.basic:has-text('保存'):visible` で特定する。
- zac は同じアカウントで同時に 1 か所しかログインできない。エージェントがサインインすると、利用者のブラウザの zac は「ログアウトされました」になる（運用上の注意として `agent/README.md` に記載）。
- 選択肢は文言の完全一致（NFKC 正規化・前後の空白除去）で選ぶ。部分一致は使わない（「プロジェクト作業」と「プロジェクト業務（QA）」などの取り違えを防ぐ）。
- 休憩の時間帯の分割：ドラフトの範囲内の休憩（勤務日基準の時刻）を `[22:00, 24:00)`・`[24:00, 29:00)` と重なる部分とそれ以外に分けて合計する。
- `entry_style` は `duration` を既定とする（所要時間で入力する画面のため）。`time_range` は行を時刻順にするだけで、zac には所要時間として入れる。
- 直行・直帰の移動時間（作業登録の「内移動時間」）は本 change では入れない（入力方法の確認後に別 change で扱う）。

### D13. zac のサインイン（キーチェーン）

zac は独自 ID/パスワードで、セッションは翌日に切れる。`[zac] login_id`・`keychain_service`（既定 `laborman-agent.zac`）を設定に持ち、パスワードは利用者が `security add-generic-password -s laborman-agent.zac -a <login_id> -w` で登録する。エージェントは `security find-generic-password -s … -a … -w` をサブプロセスで実行して読み出し（標準出力をそのまま入力欄へ渡し、変数のログ出力・例外メッセージへの埋め込みをしない）、サインイン画面でだけ使う。`keyring` ライブラリは追加しない（`security` コマンドで足りるため）。`doctor` は登録の有無だけを確認する。

### D14. `sync-zac`（zac のマスタの取込）

- 未確定の日（既定は今日）の業務報告画面で作業登録を開き、作業内容の選択肢を読む → 作業内容に「プロジェクト作業」（設定で変更可）を選ぶ → 案件の入力欄の候補をすべて読む → 案件ごとに選択して売上項目の選択肢と「売上計上済」の印を読む → 「キャンセル」で閉じる。「登録」「保存」「確定」は呼ばない（Page Object に別の読み取り専用のクラス `ZacMasterReader` を用意し、保存系の操作を持たせない）。
- 結果は `POST /api/zac-masters/import`（本文 `{ work_kinds: [...], projects: [{ code, name, sales_items: [{ name, is_closed }] }] }`）で一括登録する。backend は追加・更新のみ行い、`series_name`・`valid_month` を案件名から導出する。応答に「追加」「更新」「今回現れなかった」件数とジョブ ID を返す。
- 期替わり（第26期 → 第27期 など）で JOB 番号が払い出されたら、利用者と zac の画面を確認したうえで `sync-zac` を実行し、旧期のジョブを設定画面で無効化する（`agent/README.md` の手順）。

### D15. 画面（業務明細）の入力

- 業務明細の上部を「ジョブ → 売上項目 → 作業内容 → 内容 → 開始 → 終了 → 追加」にする。ジョブの候補はシリーズ名でまとめる。売上項目・作業内容は D11 の初期値を入れ、利用者が変えたときだけ選び直す。
- 一覧の各行に作業内容・売上項目を小さく表示し、行の編集でも変更できるようにする。
- 設定画面のジョブマスタに、売上項目の一覧（追加・無効化）・シリーズ名・対象年月・既定の作業内容を、作業内容の一覧（追加・無効化）を追加する。

## Risks / Trade-offs

- [zac の画面仕様が想定と異なり、入力形式（時間数／時刻）が合わない（§13-2）] → 2026-10-14 の画面確認で所要時間（時間数）と判明。`duration` を既定にする
- [zac の選択肢の表記が laborman のマスタとずれる（全角・半角、月替わり）] → 完全一致で選び、なければ入力を中止して `failed`。`sync-zac` で zac の表記を取り込み直せる
- [キーチェーンのパスワードが漏れる] → `security` の出力を変数に保持する時間を最小にし、ログ・例外・実行履歴に含めない。テストでは偽の値を使う
- [丸めの単位・方向が zac のルールと違う（§13-3）] → 単位は設定で変更可能。方向（切り捨て）が違う場合は D2 の目標合計の計算だけを変えればよいよう、関数を分離しておく
- [自動操作が社内規程に抵触する（§13-4）] → `auto` 運用前に情報システム部門へ確認する。初期値は `dry_run` とし、確認が取れるまで `assist` までに留める
- [zac の画面変更で誤った欄に入力される] → 既存入力の検知、保存完了表示の確認、`dry_run` のスクリーンショット確認、`warning` 時の自動降格で多重に防ぐ
- [エージェントが動いていない（Mac のスリープ・未導入）と依頼が `requested` のまま残る] → パネルに依頼日時を表示し、取り消せるようにする。`doctor` で requests 用の launchd の導入有無を確認する
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
- 社内規程上、自動操作と業務データのローカル保存が許されるか（§13-4）：`auto` 運用の可否に影響する（実装範囲は変わらない）。2026-10-15 に人事へ確認し、zac への自動入力は可
- laborman のジョブ ID と zac の案件の対応（§13-8）：`zac_search_text` で吸収できる想定。別名表が必要なら運用で `zac_search_text` を設定する
