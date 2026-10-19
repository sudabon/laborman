# SETUP GUIDE

laborman をローカルで動かすための手順です。最短で動かすなら **Docker Compose**、開発でホットリロードを使うなら **ローカル開発** の手順を参照してください。

## 前提条件

| ツール | 推奨バージョン | 用途 |
|--------|---------------|------|
| Docker / Docker Compose | 最新 | コンテナ一括起動 |
| Python | 3.12+ | バックエンド（ローカル開発時） |
| [uv](https://docs.astral.sh/uv/) | 0.8+ | Python 依存管理・仮想環境 |
| Node.js | 20+（Docker は 24） | フロントエンドビルド |
| pnpm | 10+ | JS 依存管理 |
| PostgreSQL | 17 | データベース（ローカル開発時） |
| Microsoft 365 | 会社アカウントで Outlook on the web を利用可能 | 報告メールの作成と送信、人事メールの取込（laborman-agent） |
| macOS + FileVault | — | laborman-agent（ホスト側 CLI）。ブラウザプロファイルにセッション Cookie が残るため FileVault を有効にする |

---

## 方法 A: Docker Compose（推奨・最短）

```bash
# 1. クローン
git clone <repository-url> laborman
cd laborman

# 2. 環境変数ファイルを用意（必要に応じて編集）
cp .env.example .env

# 3. ビルド & 起動
docker compose up --build
```

起動するサービス:

| サービス | ポート | 説明 |
|---------|--------|------|
| `backend` | <http://localhost:8888>（`127.0.0.1` のみ） | FastAPI。画面（`backend/public/` に置いたフロントエンドの本番ビルド）と API を配信（Swagger UI: `/docs`） |
| `db` | `localhost:5432` | PostgreSQL 17 |

- バックエンドコンテナは起動時に `alembic upgrade head` を自動実行するため、**マイグレーションの手動実行は不要**です。
- backend のポートは `127.0.0.1:8888` にだけ公開しています。認証が無いため、同じ LAN の他の端末からは到達できません（意図した設定です）。
- 画面を含めてビルドする場合は `task build`（フロントエンドをビルドして `backend/public/` へコピー）を使います。
- 停止: `docker compose down`（データも消す場合は `docker compose down -v`）。

---

## 方法 B: ローカル開発（ホットリロード）

### 1. データベースを用意

Docker で DB だけ起動するのが簡単です:

```bash
docker compose up -d db
```

（独自の PostgreSQL を使う場合は `laborman` ロール／DB を作成し、接続文字列を後述の `DATABASE_URL` に合わせてください。）

### 2. バックエンド

```bash
# 依存関係をインストール（uv が仮想環境 .venv を作成）
uv sync

# 環境変数（ローカル DB に向ける）
export DATABASE_URL="postgresql+psycopg://laborman:laborman@localhost:5432/laborman"
export BACKEND_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
# 勤務日の境界（00:00〜翌 06:00）の判定に使うタイムゾーン（任意、既定 Asia/Tokyo）
export APP_TIMEZONE="Asia/Tokyo"

# マイグレーション適用
cd backend && uv run alembic upgrade head

# 開発サーバー起動（リロード付き）
uv run uvicorn app.main:app --reload --app-dir backend --port 8000
```

> `.env` をルートに置けば `pydantic-settings` が自動で読み込みます（`export` は省略可）。

### 3. フロントエンド

```bash
cd frontend
pnpm install

# API のベース URL を指定（未指定時は http://localhost:8888）
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local

pnpm dev   # http://localhost:5173
```

### 4. 環境変数

| 変数 | 既定値 | 説明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+psycopg2://laborman:laborman@localhost:5432/laborman` | DB 接続文字列 |
| `BACKEND_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 許可するオリジン（カンマ区切り） |
| `APP_TIMEZONE` | `Asia/Tokyo` | タスク・休憩の勤務日（00:00〜翌 06:00）を判定するタイムゾーン。フロントエンドの `APP_TIME_ZONE`（`lib/date.ts`）と同じ値にします |
| `VITE_API_BASE_URL`（フロントエンド） | `http://localhost:8888` | API のベース URL（ビルド時に埋め込み） |

---

## メール作成前のブラウザ準備

1. laborman を利用するブラウザで [Outlook on the web](https://outlook.office.com/mail/) を開き、会社の Microsoft 365 アカウントでサインインします。
2. 複数の Microsoft 365 アカウントにサインインしている場合は、会社のメールボックスを開いていることを確認します。compose deep link は From を指定しません。
3. laborman に戻ってメールを作成します。確認後は Outlook on the web が新しいタブで開き、元の laborman タブは残ります。
4. Outlook on the web の作成画面で From（差出人）、宛先（To）、件名、本文を確認してから送信します。登録上の To・CC・BCC はすべて To へ統合され、BCC を含む全宛先が受信者全員に表示されます。

---

## laborman-agent（人事メールから出退勤を取り込む）

人事から届く出退勤のメール（件名 `[勤怠情報]YYYY/MM/DD:開始HH:MM/終了HH:MM`）を Outlook on the web から読み、laborman の出退勤実績に登録するホスト側 CLI です。Docker の中ではなく、利用者の Mac で動かします。laborman（Docker Compose）が起動している必要があります。

### 1. 導入

```bash
# リポジトリのルートで（uv workspace の agent を含めて同期）
uv sync --all-packages

# 自動操作に使うブラウザ。会社の条件付きアクセスで同梱 Chromium が弾かれる場合は、
# config.toml の browser.channel で "chrome"（既定）/ "msedge" を使う
uv run --directory agent playwright install chromium

uv run --directory agent laborman-agent --help
```

### 2. 設定ファイル（`~/.config/laborman-agent/config.toml`、権限 `600`）

ファイルがなくても既定値で動きますが、`doctor` は作成を求めます。パスワードやトークンは書かないでください。

```bash
mkdir -p ~/.config/laborman-agent
cat > ~/.config/laborman-agent/config.toml <<'TOML'
[laborman]
api_base_url = "http://127.0.0.1:8888"

[browser]
channel = "chrome"   # "chrome" / "msedge"。空文字なら Playwright の Chromium
headless = true

[owa]
url = "https://outlook.office.com/mail/"
search_query = '{from_clause}subject:"{hr_mail_subject_keyword}{target_date}"'

# OWA の画面が変わったときだけ上書きする（既定値は agent/README.md）
# [owa.selectors]
# search_box = "#topSearchInput"

[logs]
dir = "~/Library/Logs/laborman-agent"
retention_days = 14
TOML
chmod 600 ~/.config/laborman-agent/config.toml
```

laborman の **設定 → 人事メール（出退勤の取込）** で件名キーワード（`[勤怠情報]`）を保存します。差出人は任意です（担当者の個人アドレスのため、変わる可能性があります）。

### 3. Outlook on the web にサインイン

```bash
uv run --directory agent laborman-agent login owa
```

開いたブラウザで会社の Microsoft 365 にサインインし、メールが表示されたらブラウザを閉じます。セッションは `~/Library/Application Support/laborman-agent/profiles/owa`（権限 `700`）に保存されます。エージェントはパスワードを入力・保存しません。セッションが切れたら（終了コード 3・通知「サインインが必要です」）、同じコマンドでサインインし直します。

### 4. 診断と取込

```bash
uv run --directory agent laborman-agent doctor             # 設定・API・人事メールの条件・プロファイル・ブラウザ
uv run --directory agent laborman-agent fetch-attendance   # 前営業日（土日・祝日を除く）の出退勤を取り込む
uv run --directory agent laborman-agent fetch-attendance --date 2026-10-09
```

| 終了コード | 意味 | 例 |
|-----------|------|----|
| 0 | 完了・スキップ | 取込済み、手入力（休暇を含む）の日、別の実行が進行中 |
| 1 | 想定外のエラー | laborman API に接続できない |
| 2 | 後で再試行 | 人事メールがまだ届いていない |
| 3 | 人の対応が必要 | サインイン切れ、件名キーワード未設定、解析失敗、画面を認識できない |

- 休暇の日は人事メールが届きません。本日の報告の **出退勤（人事メール）→ 手入力** で区分「休暇」を登録すると、エージェントはその日を取り込みません。
- 手入力した日は人事メールで上書きされません。
- 解析に失敗したメールは `~/Library/Logs/laborman-agent/hr_mail/`（`600`）に保存され、14 日で削除されます。DB には保存しません。

### 5. zac への登録（laborman-agent run）

laborman の業務明細・休憩・出退勤から zac の業務報告に入力します。入力内容（ドラフト）と検証結果は、本日の報告の **zac 登録** パネルで確認できます。VPN に接続している必要があります。

1. `config.toml` に zac の設定を追加します。画面のセレクタは 2026-10-14 に確認した既定値がコードに入っているので、通常は書かなくて構いません（画面が変わったときだけ `[zac.selectors]` で上書きします。既定値は `agent/README.md`）。

   ```toml
   [zac]
   base_url = "https://tribeck2.zac.ai/tribeck2"
   login_id = "yu-suda"                       # zac のログイン ID（パスワードはキーチェーンへ）
   keychain_service = "laborman-agent.zac"    # 既定値
   reachability_url = ""                      # VPN 接続の確認に使う URL（空なら base_url）
   # report_url_template = "{base_url}/b/daily_report/{date}"   # 既定値

   # zac は保存しても画面にメッセージを出さないため、保存の通信の成功で保存完了を判定する（既定値で動く）
   # save_response_pattern = "/api/v2/daily_report/daily_reports/{date}/save"

   [schedule]
   notify_retry_after = "13:00"       # VPN 未接続・メール未着の通知はこの時刻以降の起動だけ
   ```

2. zac は独自のログイン ID とパスワードで、セッションは翌日に切れます。エージェントがサインインできるよう、**パスワードを macOS キーチェーンに登録**します（パスワードはその場で入力を求められます。設定ファイルには書きません）。

   ```bash
   security add-generic-password -s laborman-agent.zac -a yu-suda -w
   ```

   `uv run --directory agent laborman-agent doctor` で、zac への到達性・プロファイル・パスワードの登録（値は表示しません）を確認します。手動でサインインしたいときは `laborman-agent login zac` を使います。

3. zac の作業内容・案件・売上項目の選択肢を laborman に取り込みます（**zac には何も保存しません**。作業登録を開いて選択肢を読み、キャンセルで閉じます。確定済みの日では読めないので、未確定の日を指定します）。

   ```bash
   uv run --directory agent laborman-agent sync-zac               # 今日の画面で読む
   uv run --directory agent laborman-agent sync-zac --date 2026-10-13
   ```

   取り込んだ選択肢は **設定 → 業務明細・zac** のジョブマスタ（売上項目）と「zac の作業内容」で確認・追加・無効化できます。月ごとに JOB 番号が変わる案件（例：`bizoceanAPPs開発(26/10)` → `(26/11)`）は、案件名の年月から自動でシリーズにまとまります。翌月分は zac に案件ができてから `sync-zac` で取り込んでください。

   運用中に JOB 番号が変わったとき（月替わり・期替わり）も同じコマンドで取り込みます。手順は `agent/README.md` の「期替わり・月替わりで JOB 番号が変わったとき」を参照してください。

4. laborman の **設定 → zac 連携** で実行モードを選びます。最初は `dry_run`（入力してスクリーンショットを残し、保存しない）にしてください。zac は作業登録で追加した工数明細を自動保存するため、`dry_run` でも工数明細は zac に残ります。同じ日をやり直すときは、zac で明細を削除してから実行してください。

   ```bash
   uv run --directory agent laborman-agent run --date 2026-10-09 --mode dry_run --headed
   uv run --directory agent laborman-agent register --date 2026-10-09   # 人事メールの取込を行わない
   ```

   スクリーンショットは `~/Library/Logs/laborman-agent/screenshots/`（`600`、保持期間で削除）に保存されます。段階運用（`dry_run` → `assist` → `auto`）は `agent/README.md` を参照してください。`auto` は社内規程の確認後に使います（2026-10-15、人事に確認し zac への自動入力は可）。

### 6. 定時実行と画面からの実行（launchd）

`agent/launchd/` の例をコピーし、`USERNAME` と uv・リポジトリのパスを書き換えてから登録します。

画面のボタンだけで運用する場合は、`requests` だけを登録します（人事メールが届いたら「この日を zac に登録」を押す。依頼の処理は人事メールの取込から行う）。平日朝の自動実行が必要なときだけ、もう一方も登録します。

```bash
cp agent/launchd/jp.sudabon.laborman-agent.plist.example ~/Library/LaunchAgents/jp.sudabon.laborman-agent.plist
cp agent/launchd/jp.sudabon.laborman-agent.requests.plist.example ~/Library/LaunchAgents/jp.sudabon.laborman-agent.requests.plist
# パスを編集してから
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/jp.sudabon.laborman-agent.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/jp.sudabon.laborman-agent.requests.plist

# 解除
launchctl bootout gui/$(id -u)/jp.sudabon.laborman-agent
launchctl bootout gui/$(id -u)/jp.sudabon.laborman-agent.requests
```

| 設定例 | 起動 | 内容 |
|--------|------|------|
| `jp.sudabon.laborman-agent` | 平日 9:20・10:20・11:20・13:20 | 前営業日の `run`。完了済みの日はすぐに終わるので重複しない。スリープ中に過ぎた時刻は復帰時に 1 回実行される |
| `jp.sudabon.laborman-agent.requests` | 60 秒ごと | 本日の報告の **この日を zac に登録** で記録された依頼を `process-requests` で実行する。依頼がなければブラウザを起動せずに終わる |

前提：Mac がログイン中で、Docker Desktop と laborman が起動していること。画面から依頼して 1 分ほどで処理が始まり、パネルに結果が表示されます（依頼中は取り消せます）。

---

## 動作確認

```bash
# ヘルスチェック
curl http://localhost:8000/api/health
# => {"status":"ok"}

# メール設定の取得（初回は既定値で初期化される）
curl http://localhost:8000/api/mail-settings
```

- ブラウザで <http://localhost:5173>（Docker Compose では <http://localhost:8888>）を開き、「本日の報告」「カレンダー」「設定」が表示されれば成功です。
- API ドキュメント: <http://localhost:8000/docs>（Docker Compose では <http://localhost:8888/docs>）
- 平日の本日の報告を開くと、業務明細に既定の休憩（設定の既定値、初期 12:00–13:00）が入っていることを確認します。時刻は行の編集で直せます。
- 業務明細でジョブ・内容・開始・終了（例 `09:00`・`10:30`）を入力して「追加」を押し、一覧に表示されることを確認します（ジョブは設定画面のジョブマスタか、ジョブ欄からその場で登録できます）。

## テスト

```bash
# バックエンド（pytest）— public/ を配信するため backend で実行する
cd backend && uv run pytest

# laborman-agent（pytest。OWA のテストは静的モックに Playwright の Chromium で接続する）
cd agent && uv run pytest

# フロントエンド（Vitest）
cd frontend && pnpm test
```

---

## よくある問題

### `connection refused` / DB に接続できない

- DB コンテナが起動済みか確認: `docker compose ps`。
- ローカル実行時は `DATABASE_URL` のホストが `localhost`、Docker 内は `db` である点に注意（`.env.example` は Docker 用に `db` を指しています）。
- `psql` などで `localhost:5432` に到達できるか確認。

### CORS エラー（ブラウザコンソールに `blocked by CORS policy`）

- バックエンドの `BACKEND_CORS_ORIGINS` にフロントの URL（既定 `http://localhost:5173`）が含まれているか確認。
- フロントの `VITE_API_BASE_URL` が正しい API ホストを指しているか確認（変更時は再ビルド／再起動が必要）。

### マイグレーションが当たらない / テーブルが無い

- ローカル開発では `cd backend && uv run alembic upgrade head` を手動実行する必要があります（Docker では自動）。
- `alembic.ini` の `sqlalchemy.url` よりも環境変数 `DATABASE_URL` が優先されます（`backend/alembic/env.py` が `get_settings()` から取得）。

### Outlook on the web の新しいタブが開かない

- ブラウザのアドレスバー付近にポップアップ／新しいタブのブロック表示があれば、laborman からのポップアップを許可します。
- 元の laborman タブと確認画面は残るため、許可後に「Outlook on the webを開く」をもう一度押してください。
- 開けないままでも、確認画面の「手動送信用コピー」から「宛先」「件名」「本文」を個別にコピーし、Outlook on the web の新規メールへ貼り付けて送信できます。

### サインイン画面になり、入力内容が引き継がれない

- 先に会社の Microsoft 365 アカウントで Outlook on the web へのサインインを完了し、laborman の確認画面へ戻ってもう一度開きます。
- 再試行しても入力されない場合は、確認画面の「宛先（To）」「件名」「本文」を順番にコピーして新規メールへ貼り付けます。コピーされる宛先には、登録上の To・CC・BCC がこの順ですべて含まれます。
- 本文が長い場合は作成URLを処理できないことがあります。長いURLの警告が出たときも同じコピー手順を使用してください。

### 複数アカウントで意図しない From が選ばれる

- Outlook on the web 右上のアカウント表示で会社アカウント／会社メールボックスを選び直してください。
- compose deep link では From を指定できません。作成画面の From（差出人）が会社メールアドレスでない場合は送信せず、正しいアカウントへ切り替えてください。

### CC/BCCがOutlookの宛先（To）へ表示される

- Outlook on the web の compose deep link では CC/BCC が安定して反映されないため、laborman は登録上の To・CC・BCC をすべて To へ統合します。
- BCC の秘匿性も失われ、全宛先が受信者全員に表示されます。確認画面と Outlook の作成画面で宛先を確認し、この運用で問題がある宛先は送信前に削除してください。

### 他の端末から laborman を開けない

- Docker Compose の backend は `127.0.0.1:8888` にだけ公開しています。laborman を動かしている端末のブラウザから <http://localhost:8888> を開いてください。

### タスク・休憩の時間帯が重なっている

- 重なっていても保存でき、エラーは出ません（例：既定の休憩 12:00–13:00 と 11:30–12:30 のタスク）。一覧で時刻を確認し、行の編集で調整してください。
- 時刻は勤務日基準の `HH:MM` で入力します。日付をまたぐ場合は `24:00`〜`29:59` を使います（翌 06:00 以降は保存できません）。

### 宛先が不足してメール作成ボタンを押せない

- 設定画面で「上司メール」「労務 ML メール」の両方を入力してください（`hasRequiredRecipients`）。
