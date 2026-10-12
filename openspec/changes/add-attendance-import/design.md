# Design

## Context

- `add-work-tasks-and-breaks` により `work_tasks`・`work_breaks`（`source` 列あり）・`jobs`・`automation_settings`（既定休憩のみ）、`app_timezone`、`parseWorkTime`/`formatWorkTime` が存在する前提。
- backend は Docker コンテナ内で動き、`127.0.0.1:8888` でのみ公開される。社内の Microsoft 365 は管理者承認が得られないため Graph API・IMAP は使えず、Outlook on the web（OWA）の画面を読むしかない。
- 振る舞いは specs/、全体設計の出典は `ZAC_AUTOMATION_SPEC.md`（§3 の設計判断 D1・D2・D5、§7）。

## Goals / Non-Goals

**Goals:**

- 出退勤実績のデータモデルと API を、Phase 3 の zac ドラフト算出がそのまま使える形で確定する
- `agent/` の共通基盤（設定・API クライアント・前営業日・ロック・通知・終了コード・ログ）を、Phase 3 の `run`・`register` が再利用できる形で作る
- 人事メールの書式が未確定でも、解析規則を設定で差し替えられるようにして実装を先行させる

**Non-Goals:**

- zac の操作、`run`・`register`・`login zac`、launchd 登録（`add-zac-draft-and-registration` で扱う）
- Slack 通知（macOS 通知のみ。必要になれば Phase 3 以降で追加）
- 実在の人事メール・OWA への自動テストでの接続（テストは静的モックのみ）

## Decisions

### D1. `work_reports` への列追加

仕様書 §5.4 の `attendance_start_at`・`attendance_end_at`（`timestamptz NULL`）、`attendance_source`（`varchar(16) NULL`, `CHECK in ('hr_mail','manual')`）、`attendance_kind`（`varchar(16) NOT NULL DEFAULT 'work'`, `CHECK in ('work','leave')`）、`attendance_imported_at`（`timestamptz NULL`）に加え、**`attendance_break_minutes`（`int NULL`）**を追加する。

仕様書 REQ-A2 は「分数のみの休憩は保存せず、ドラフト検証で手入力の休憩合計と比較（`BREAK_MISMATCH`）」としているが、保存しないと Phase 3 の backend が比較できない。休憩レコードは作らずに分数だけを実績の一部として保持することで、REQ-A2 の意図（手入力の休憩を勝手に作らない）を守りつつ比較を可能にする。`zac_registered_at` は Phase 3 で追加する。

### D2. `PUT /api/work-reports/{date}/attendance`

- 本文：`{ start_at, end_at, source: "hr_mail"|"manual", kind: "work"|"leave", break_minutes? }`。報告がなければ get-or-create。
- 検証：`kind=work` は `start_at`・`end_at` 必須かつ `end_at > start_at`、時刻は勤務日 00:00〜翌 06:00（Phase 1 と同じ範囲）。`kind=leave` は時刻を空にできる。違反は `422`。
- `source=hr_mail` かつ既存の `attendance_source=manual` の場合は `409`（`detail.message` のみ、値は変えない）。`source=hr_mail` のとき `attendance_imported_at = now`、`manual` のときは変更しない。
- 応答は更新後の `WorkReportRead`。`WorkReportRead` に `attendance_*` を追加する（既存クライアントは未知の項目を無視するため互換）。

**代替案**：`PATCH /work-reports/{date}` に相乗りする案は、`manual` 保護の 409 と通常の更新の区別が曖昧になるため採らない。

### D3. 人事メール由来の休憩

既存の休憩追加 API（`POST /api/work-reports/{date}/breaks`）に任意項目 `source`（既定 `manual`）を追加する。エージェントは `source=hr_mail` で登録し、`409`（重なり）は「登録せず警告」として扱う。同じ日に `hr_mail` の休憩がすでにある場合は再登録しない（エージェント側で一覧を見て判定し、冪等にする）。

### D4. `agent/` のパッケージ構成と依存

仕様書 §7.1 の構成に従い、Phase 2 では `cli.py`・`config.py`・`api_client.py`・`business_days.py`・`lock.py`・`notify.py`・`logs.py`・`owa/fetch.py`・`owa/parser.py` を作る。

- Python 3.12、`uv` の workspace member としてルート `pyproject.toml` の `members` に `agent` を追加。エントリポイント `laborman-agent = "laborman_agent.cli:main"`。
- 依存：`playwright`（ブラウザ操作）、`httpx`（API）、`jpholiday`（祝日）。設定は標準ライブラリ `tomllib`、CLI は `argparse`。
- backend の依存・イメージには一切追加しない（仕様書 D1：ブラウザ自動化はホストのみ）。

### D5. OWA の取得（`owa/fetch.py`）

- Playwright の `launch_persistent_context(profile_dir/owa, channel=config.browser.channel, headless=...)` で専用プロファイルを使う。条件付きアクセスで同梱 Chromium が弾かれる場合に備え、`channel`（`chrome`/`msedge`）を設定で切り替える。
- 手順：OWA を開く → サインイン画面（URL が `login.microsoftonline.com` 等、または設定のセレクタ）を検知したら `needs_login`（終了コード 3）→ 検索ボックスに `search_query` を入力 → 結果のうち実行日受信の先頭を開く → 本文の `inner_text` を取得。見つからなければ終了コード 2。
- セレクタは既定値をコードに持ち、`[owa.selectors]` で上書きする（OWA の画面変更にコード修正なしで追従するため）。
- `login owa` は同じプロファイルを `headless=False` で開き、利用者がブラウザを閉じるまで待つ。プロファイルディレクトリは `700` で作成する。

### D6. 本文の解析（`owa/parser.py`）

- 入力は本文テキストと対象日、出力は `AttendanceRecord(kind, start, end, break_range | break_minutes)` または解析失敗。I/O を持たない純粋関数とし、フィクスチャで単体テストする。
- 前処理で `unicodedata.normalize("NFKC")` により全角数字・コロンを半角化する。
- 規則は設定 `[owa.parser]` の `line_pattern`（名前付きグループ `month`・`day`・`start`・`end`）、`break_range_pattern`・`break_minutes_pattern`（任意）、`leave_keywords` で与える。対象日の行が見つからなければ失敗。
- 人事メールのサンプル入手前は、仕様書 §7.3 の想定書式で作った合成フィクスチャで実装・テストし、サンプル入手後に匿名化した実サンプル（5 件以上）に置き換えて既定の規則を確定する。

### D7. `fetch-attendance` の流れと終了コード

1. ロック取得（取れなければ終了コード 0）→ ログの期限削除 → 対象日の決定
2. `GET /api/work-reports/{date}`。`attendance_source=manual` なら「手入力済みのためスキップ」で終了コード 0（OWA を開かない）
3. OWA から本文取得（未着 2、サインイン切れ 3）→ 解析（失敗は本文をログに保存して 3）
4. `PUT attendance`（`409` は手入力済みとして 0）→ 休憩（D3）→ 結果を出力・必要なら通知

想定外の例外は終了コード 1 とし、スタックトレースはログに出すがメール本文は出さない。

### D8. ロック・通知・ログ

- ロック：`~/Library/Application Support/laborman-agent/agent.lock` を `fcntl.flock(LOCK_EX | LOCK_NB)` で取得。プロセス終了で自動解放されるため、異常終了時の残留ロックが起きない。
- 通知：`osascript -e 'display notification ...'`。対象日と結果の要約のみを載せる。
- ログ：`~/Library/Logs/laborman-agent/`（`700`）。解析失敗時の本文は `hr_mail/<日時>.txt`（`600`）。起動ごとに `retention_days`（既定 14）より古いファイルを削除する。

### D9. 人事メールの検索条件

`automation_settings` に `hr_mail_from`・`hr_mail_subject_keyword`（`text NOT NULL DEFAULT ''`）を追加し、設定画面で編集する。エージェントは `GET /api/automation-settings` から読み、設定ファイルの `search_query` テンプレートに埋め込む。条件が空の場合は検索せず、終了コード 3（設定不足）とする。

## Risks / Trade-offs

- [条件付きアクセスで自動操作のブラウザからサインインできない（§13-6）] → `channel` を Chrome / Edge に切り替えられるようにする。それでも不可なら Phase 2 のエージェント部分は保留し、UI の手入力のみで運用する（backend・UI は単独で価値がある）
- [人事メールの書式が想定と違う（§13-1）] → 解析規則を設定で差し替え可能にし、実サンプル入手後にフィクスチャと既定規則を確定するタスクを分けて置く
- [OWA の画面変更でセレクタが壊れる] → セレクタを設定で上書き可能にし、`doctor` と解析失敗の通知で早期に気付けるようにする
- [ブラウザプロファイルにセッション Cookie が残る] → 権限 `700`、FileVault 前提を `SETUP_GUIDE.md` に明記する
- [手入力済みの日に誤った人事メールの値が来ても気付けない] → 手入力を優先する仕様どおりとし、スキップした旨を出力に残す

## Migration Plan

1. Alembic マイグレーションで `work_reports` に列を追加（既存行は NULL、`attendance_kind='work'`）し、`automation_settings` に列を追加する
2. `task build && task start` で backend・SPA を更新する
3. ホストで `uv sync`（workspace）→ `uv run --directory agent playwright install chromium`（または Chrome を使う設定）→ `config.toml` を作成（`600`）→ `laborman-agent login owa` → `laborman-agent doctor`
4. ロールバック：`alembic downgrade -1` で列を削除。エージェントは使わなければ影響しない

## Open Questions

- 人事メールの差出人・件名・本文書式・休暇や休憩の表記（仕様書 §13-1）：解析規則とフィクスチャの確定に使う。設定で吸収するため設計・タスクは変わらない
- OWA へのサインイン方式と、自動操作のブラウザが条件付きアクセスを通るか（§13-6）：`browser.channel` の既定値に影響する
- 日をまたぐ勤務・半休の表記（§13-7）：半休を `work` として扱うか、解析規則で吸収できるかをサンプルで確認する
