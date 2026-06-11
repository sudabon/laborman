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
| `frontend` | <http://localhost:5173> | Nginx で配信される本番ビルド |
| `backend` | <http://localhost:8888> | FastAPI（Swagger UI: `/docs`） |
| `db` | `localhost:5432` | PostgreSQL 17 |

- バックエンドコンテナは起動時に `alembic upgrade head` を自動実行するため、**マイグレーションの手動実行は不要**です。
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

# API のベース URL を指定（既定は http://localhost:8000）
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local

pnpm dev   # http://localhost:5173
```

---

## 動作確認

```bash
# ヘルスチェック
curl http://localhost:8000/api/health
# => {"status":"ok"}

# メール設定の取得（初回は既定値で初期化される）
curl http://localhost:8000/api/mail-settings
```

- ブラウザで <http://localhost:5173> を開き、「本日の報告」「カレンダー」「設定」が表示されれば成功です。
- API ドキュメント: <http://localhost:8000/docs>

## テスト

```bash
# バックエンド（pytest）— testpaths は backend/tests
uv run pytest

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

### `mailto:` でメーラーが起動しない

- OS で既定のメールクライアントが設定されているか確認してください。アプリはメール送信を行わず、`mailto:` リンクを開くだけです。
- 設定画面で「上司メール」「労務 ML メール」の両方が入力されていないと宛先が不足します（`hasRequiredRecipients`）。
