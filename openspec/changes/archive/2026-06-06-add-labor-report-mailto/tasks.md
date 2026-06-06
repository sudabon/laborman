## 1. プロジェクト基盤

- [x] 1.1 React + TypeScript + Vite プロジェクトを初期化し、Tailwind CSS + shadcn/ui を導入する
- [x] 1.2 FastAPI + SQLAlchemy + Alembic のバックエンド雛形を作成し、DB接続情報を環境変数で整備する
- [x] 1.3 フロントエンド・バックエンド・PostgreSQL の3サービスを `docker-compose` で起動できるようにする（各 Dockerfile / compose 定義）
- [x] 1.4 カレンダーライブラリ（FullCalendar または React DayPicker）を選定・導入する

## 2. データモデル

- [x] 2.1 Alembic マイグレーションで `work_reports` を作成（id, work_date, start_time, end_time, start_mail_created_at, end_mail_created_at, note, work_style, end_mail_body, created_at, updated_at）。`work_date` を1日1レコードの一意制約にする。`work_style` は office/remote の2値、`end_mail_body`（終業メール本文・ヘッダ/フッタ除く）は nullable とし、始業メール本文用カラムは設けない
- [x] 2.2 Alembic マイグレーションで `mail_settings` を単一行テーブルとして作成（id, boss_email, labor_ml_email, cc_emails, bcc_emails, start_subject_template, start_body_template, end_subject_template, end_body_template, end_footer_template, created_at, updated_at）。ユーザー単位のカラムは持たない
- [x] 2.3 SQLAlchemy モデルと FastAPI のデータアクセス層（取得・upsert）を実装する

## 3. 設定画面（mail-settings）

- [x] 3.1 設定画面で上司・労務ML・CC・BCC を入力・保存できるフォームを実装する（CC/BCC は任意）
- [x] 3.2 始業/終業の件名・本文テンプレート、および終業メールのヘッダ/フッタテンプレートを編集・保存できる UI を実装し、未設定時は DESIGN 既定テンプレートを表示する
- [x] 3.3 宛先未設定時にメール作成操作を抑止し、設定画面へ誘導するガードを実装する

## 4. 記録機能（work-report-logging）

- [x] 4.1 始業記録（当日レコードの新規作成/更新、現在日時を start_time に保存、ステータス start_recorded）を実装する
- [x] 4.2 終業記録（end_time 保存、始業ありなら勤務時間計算、ステータス end_recorded、始業なしは勤務時間不明扱い）を実装する
- [x] 4.3 タイムスタンプ系カラムからステータス（not_started〜end_mail_created）を導出するロジックを実装する
- [x] 4.4 メモ欄を実装し、mailto URL 長対策として文字数制限を設ける
- [x] 4.5 勤務区分（オフィス/リモートの2択）を選択して当日レコードの `work_style` に保存する UI とロジックを実装する

## 5. メール生成と Outlook 起動（outlook-mail-compose）

- [x] 5.1 テンプレート変数置換関数（{{date}}/{{start_time}}/{{end_time}}/{{work_duration}}/{{work_style}}/{{note}}、work_style は office→オフィス・remote→リモートに展開）を実装し、終業メールはヘッダ＋本文＋フッタを連結して全文を構成する
- [x] 5.2 `buildMailtoUrl({ to, cc, bcc, subject, body })` を実装する（to は encodeURIComponent 後カンマ結合、cc/bcc 空なら付与しない、From 指定なし）
- [x] 5.3 作成前の確認画面（宛先・件名・本文、From確認の注意喚起）を実装する
- [x] 5.4 確定時に mailto を実行して Outlook を開き、対応する `*_mail_created_at` を記録してステータスを前進させる
- [x] 5.5 「Outlookで送信しました」自己申告チェックを実装する（送信検知ではないことを明示、文言は「メール作成済み」を使用）
- [x] 5.6 終業メール作成時、本文テンプレートの置換結果（ヘッダ/フッタ除く）を `end_mail_body` に保存する。ヘッダ/フッタおよび始業メール本文は保存しない

## 6. フォールバックUI（outlook-mail-compose）

- [x] 6.1 宛先・件名・本文を個別にクリップボードへコピーするボタンを実装する
- [x] 6.2 Outlook を開けない場合の案内文と手動送信導線を表示する

## 7. カレンダー表示（report-calendar）

- [x] 7.1 月単位カレンダーで各日のステータスを表示し、前月/翌月へ移動できるようにする
- [x] 7.2 未報告の過去日を強調表示する
- [x] 7.3 本日の報告画面（日付・始業/終業操作・始業時刻・終業時刻・勤務時間・メモ）を実装し、カレンダーから遷移できるようにする

## 8. 検証

- [x] 8.1 `buildMailtoUrl`・テンプレート置換（work_style 展開含む）・終業メールのヘッダ＋本文＋フッタ連結のユニットテストを spec シナリオに沿って作成する
- [x] 8.2 始業→始業メール作成→終業→終業メール作成 のステータス遷移と `end_mail_body` 保存（始業本文は非保存）を結合テストで検証する
- [x] 8.3 宛先未設定ガード・CC/BCC空・始業なし終業の境界ケースを検証する
- [x] 8.4 `docker-compose up` で全サービスが起動し、フロント→API→PostgreSQL が疎通することを確認する
- [x] 8.5 実機（Mac + Outlook）で mailto によるメール作成画面起動を手動確認する
