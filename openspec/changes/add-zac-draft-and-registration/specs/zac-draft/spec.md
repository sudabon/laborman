# Spec Delta

## Purpose

勤務日ごとに zac へ入力する内容（ドラフト）と、その内容で登録してよいかの検証結果を laborman が一元的に算出し、UI とエージェントが同じ結果を使えるようにするための機能。

## ADDED Requirements

### Requirement: ドラフトの提供

システムは、勤務日ごとの zac 登録ドラフトを取得する API を提供しなければならない（SHALL）。ドラフトは、出退勤（出勤・退勤・登録元）、出退勤の範囲内の休憩、実働時間（分）、入力形式、入力行、検証結果の一覧、登録可否（`error` が 0 件）、自動保存可否（`error` と `warning` が 0 件）、zac 保存成功日時を含まなければならない（SHALL）。ドラフトの算出は DB を変更してはならない（MUST NOT）。UI とエージェントは同じ API の結果を表示・使用しなければならない（MUST）。

#### Scenario: ドラフトを取得する

- **WHEN** 出退勤 09:02–18:41・休憩 12:00–13:00・タスクが記録された 2026-10-09 のドラフトを取得する
- **THEN** システムは出退勤・休憩・実働 519 分・入力行・検証結果・登録可否・自動保存可否を返し、DB は変更しない

### Requirement: 実働時間とタスクのクリップ

システムは、実働時間を「退勤 − 出勤 − 出退勤の範囲内の休憩合計」で算出しなければならない（SHALL）。出退勤には laborman の打刻ではなく出退勤実績を使わなければならない（MUST）。出退勤の範囲からはみ出したタスクは、はみ出しが許容値（既定 15 分）以内なら範囲内に切り詰めて `TASK_OUTSIDE_ATTENDANCE`（warning）とし、超える場合は `TASK_OUTSIDE_ATTENDANCE`（error）としなければならない（SHALL）。

#### Scenario: 許容値以内のはみ出し

- **WHEN** 出勤が 09:02 で、09:00 開始のタスクがある
- **THEN** システムはそのタスクを 09:02 開始として計算し、`TASK_OUTSIDE_ATTENDANCE`（warning）を「09:00開始のタスクを出勤時刻09:02に切り詰めました」として返す

#### Scenario: 許容値を超えるはみ出し

- **WHEN** 退勤が 18:00 で、18:30 終了のタスクがある
- **THEN** システムは `TASK_OUTSIDE_ATTENDANCE`（error）を返し、登録可否を false にする

### Requirement: 空き時間の扱い

システムは、出退勤の範囲内でどのタスクにも休憩にも含まれない時間（空き時間）を検出し、設定に従って扱わなければならない（SHALL）。設定が `block`（既定）の場合は `UNCOVERED_TIME`（error）とし、`assign_default_job` の場合は設定の既定ジョブに割り当てて `UNCOVERED_TIME`（warning）としなければならない（SHALL）。

#### Scenario: block の場合

- **WHEN** 空き時間の扱いが `block` で、15:00–15:20 がどのタスクにも含まれない
- **THEN** システムは `UNCOVERED_TIME`（error）を返し、登録可否を false にする

#### Scenario: 既定ジョブに割り当てる場合

- **WHEN** 空き時間の扱いが `assign_default_job`・既定ジョブが JOB-B で、15:00–15:20 がどのタスクにも含まれない
- **THEN** システムは 20 分を JOB-B に加えて入力行を作り、`UNCOVERED_TIME`（warning）を返す

### Requirement: 入力行の生成

システムは、設定の入力形式に従って入力行を生成しなければならない（SHALL）。

- `duration`（既定。zac の工数は所要時間で入力するため）：「作業内容・ジョブ・売上項目」の組み合わせごとに時間を集計し、丸めずに分単位のまま入力行にする。入力行の合計は実働時間と一致しなければならない（MUST）
- `time_range`：タスクを時刻順に 1 行ずつ出力し、連続する同一の組み合わせ・同一内容の行は結合する

内容（zac の備考）は、行に含まれるタスクの内容を開始順に重複を除いて「- 内容」の形式で改行区切りに並べ、設定の最大長で切り詰めなければならない（SHALL）。各入力行は、ジョブ ID、zac 検索文字列（未設定ならジョブ ID）、案件名、作業内容、売上項目、時間（分）または開始・終了、内容を含まなければならない（SHALL）。

#### Scenario: 丸めずに集計する

- **WHEN** 入力形式が `duration` で、実働 519 分のうちクリップ後の「プロジェクト作業・2602028・プロジェクトサポート（2026／10）」が 298 分、「プロジェクト作業・2601570・サービス開発本部 make.AI 業務」が 221 分
- **THEN** システムは前者を 298 分、後者を 221 分の入力行にし、合計は実働と同じ 519 分になる

#### Scenario: 内容を箇条書きにする

- **WHEN** 入力形式が `duration` で、同じ組み合わせのタスクの内容が開始順に「設計レビュー」「障害調査」「設計レビュー」
- **THEN** システムはその入力行の内容を「- 設計レビュー」「- 障害調査」の 2 行にする

#### Scenario: 作業内容が違えば別の行にする

- **WHEN** 同じジョブ 2602028・同じ売上項目で、作業内容が「プロジェクト作業」と「プロジェクト関連打ち合わせ」のタスクがある
- **THEN** システムは作業内容ごとに別の入力行を作る

#### Scenario: 時刻順の入力行

- **WHEN** 入力形式が `time_range` で、09:00–10:30 JOB-A「設計」と 10:30–11:00 JOB-A「設計」のタスクがある
- **THEN** システムは 09:00–11:00 JOB-A「設計」の 1 行にまとめる

### Requirement: 検証

システムは、ドラフトに次の検証結果を含めなければならない（SHALL）。各結果はコード・重要度・メッセージと、該当する場合は対象レコードの ID を持つ。

| コード | 重要度 | 条件 |
|--------|--------|------|
| `ATTENDANCE_MISSING` | error | 出退勤実績が未登録 |
| `ON_LEAVE` | error | 区分が休暇 |
| `NO_TASKS` | error | タスクが 0 件 |
| `TASK_RUNNING` | error | 終了時刻のないタスク・休憩がある |
| `TASK_OVERLAP` | error | タスク同士・タスクと休憩が重なる |
| `TASK_OUTSIDE_ATTENDANCE` | error / warning | 出退勤の範囲外（許容値以内は warning） |
| `UNCOVERED_TIME` | error / warning | 空き時間あり（空き時間の扱いによる） |
| `JOB_UNKNOWN` | error | タスクまたは既定ジョブのジョブ ID がジョブマスタに存在しない |
| `JOB_MONTH_MISMATCH` | error | タスクのジョブの対象年月が勤務日の年月と違う（月ごとの案件の取り違え） |
| `WORK_KIND_MISSING` | error | タスクに作業内容が設定されていない |
| `SALES_ITEM_MISSING` | error | タスクに売上項目が設定されていない |
| `SALES_ITEM_MONTH_MISMATCH` | warning | タスクの売上項目の対象年月が勤務日の年月と違う |
| `TOTAL_MISMATCH` | error | 入力行の合計が実働時間と一致しない |
| `BREAK_MISSING` | error | 出退勤の範囲内に休憩が 1 件も記録されていない |
| `ALREADY_REGISTERED` | info | zac 保存成功日時が設定済み |

`error` が 1 件でもあれば登録可否を false、`error` または `warning` が 1 件でもあれば自動保存可否を false にしなければならない（MUST）。

#### Scenario: 出退勤が未登録

- **WHEN** 出退勤実績が未登録の日のドラフトを取得する
- **THEN** システムは `ATTENDANCE_MISSING`（error）を返し、登録可否を false にする

#### Scenario: 休暇日

- **WHEN** 出退勤実績の区分が休暇の日のドラフトを取得する
- **THEN** システムは `ON_LEAVE`（error）を返し、入力行を空にする

#### Scenario: 売上項目が未設定

- **WHEN** 売上項目のないタスクがある日のドラフトを取得する
- **THEN** システムは `SALES_ITEM_MISSING`（error）とそのタスクの ID を返し、登録可否を false にする

#### Scenario: 登録済みの日

- **WHEN** zac 保存成功日時が設定済みの日のドラフトを取得する
- **THEN** システムは `ALREADY_REGISTERED`（info）を返す

### Requirement: 休憩の記録漏れ

休憩は毎日必ず記録する運用のため、システムは、出退勤の範囲内に休憩が 1 件も記録されていない日のドラフトでは、`BREAK_MISSING`（error）を返し、登録可否を false にしなければならない（SHALL）。既定の休憩で補ってはならず（MUST NOT）、休憩レコードを自動で作成してはならない（MUST NOT）。

#### Scenario: 休憩の記録がない日

- **WHEN** 出退勤 08:29–18:38・タスクはあるが休憩が 0 件の日のドラフトを取得する
- **THEN** システムは `BREAK_MISSING`（error）を返し、登録可否を false にし、休憩レコードは作成しない

### Requirement: zac 連携の設定

システムは、zac 連携の設定（実行モード `dry_run`/`assist`/`auto`〔初期値 `dry_run`〕、入力形式 `duration`/`time_range`、はみ出しの許容値、空き時間の扱い、既定ジョブ・既定の作業内容・既定の売上項目、内容の最大長）を保存・編集できなければならない（SHALL）。空き時間の扱いが `assign_default_job` の場合は既定ジョブ・既定の作業内容・既定の売上項目の指定が必須でなければならない（MUST）。

#### Scenario: 既定ジョブなしで割り当てを選ぶ

- **WHEN** ユーザーが空き時間の扱いを `assign_default_job` にし、既定ジョブを空のまま保存する
- **THEN** システムは `422` を返し、設定を保存しない
