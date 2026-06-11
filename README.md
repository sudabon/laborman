# laborman — 労務報告カレンダー

始業・終業の打刻を記録し、登録済みテンプレートから **Outlook 等のメーラーを起動する `mailto:` リンク**を組み立てる、個人向けの労務報告支援アプリです。報告状況は月次カレンダーで一覧でき、本日の報告はワンクリックで作成できます。

> メール送信そのものはアプリでは行いません。`mailto:` でユーザーのメールクライアントに下書きを渡し、送信は本人が行う方式です。

## 主な機能

- **本日の報告**: 始業／終業の打刻、勤務区分（オフィス／リモート）・メモの記録
- **メール下書き作成**: 始業・終業メールの件名／本文をテンプレートから生成し、`mailto:` で起動
- **月次カレンダー**: 日ごとの報告ステータス（未報告 → 始業記録 → 始業メール → 終業記録 → 終業メール）を可視化
- **メール設定**: 宛先（上司・労務 ML）、CC／BCC、件名・本文テンプレートの編集
- **送信確認チェック**: 「送信済み」フラグをブラウザの localStorage に保持

## 技術スタック

| 領域 | 採用技術 |
|------|----------|
| バックエンド | Python 3.12+ / FastAPI / SQLAlchemy 2.0 / Alembic |
| データベース | PostgreSQL 17（psycopg 3） |
| 設定管理 | pydantic-settings |
| フロントエンド | React 19 / TypeScript 5.9 / Vite 7 / Tailwind CSS 4 / shadcn-ui 系コンポーネント |
| 補助ライブラリ | react-day-picker / date-fns / lucide-react |
| テスト | pytest（backend） / Vitest（frontend） |
| インフラ | Docker Compose / Nginx（フロント配信） / uv（Python 依存管理） / pnpm（JS 依存管理） |

## 前提条件

- Docker / Docker Compose（最短で動かす場合）
- ローカル開発する場合: Python 3.12+ ・ [uv](https://docs.astral.sh/uv/) ・ Node.js 20+（Docker は 24 系）・ pnpm 10+ ・ PostgreSQL 17

## クイックスタート（Docker）

```bash
git clone <repository-url> laborman
cd laborman
cp .env.example .env          # 必要に応じて編集
docker compose up --build
```

- フロントエンド: <http://localhost:5173>
- バックエンド API: <http://localhost:8888> （Swagger UI: <http://localhost:8888/docs>）

バックエンドコンテナは起動時に Alembic マイグレーション（`upgrade head`）を自動実行します。

## ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [SETUP_GUIDE.md](./SETUP_GUIDE.md) | 環境構築手順（Docker / ローカル）・よくある問題 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | システム構成図・レイヤー構成・設計方針 |
| [API_REFERENCE.md](./API_REFERENCE.md) | 全 API エンドポイント一覧 |
| [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) | ER 図・テーブル定義 |

## 環境変数

ルートの [`.env.example`](../.env.example) を参照してください。主な変数:

| 変数 | 既定値 | 説明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+psycopg://laborman:laborman@db:5432/laborman` | DB 接続文字列 |
| `BACKEND_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | CORS 許可オリジン（カンマ区切り） |
| `VITE_API_BASE_URL` | `http://localhost:8000` | フロントから見た API ベース URL（ビルド時引数） |
