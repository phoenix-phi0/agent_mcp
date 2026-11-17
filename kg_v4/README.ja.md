# kg_v4：AI 教師学習システム（日本語版 README）

学習者ごとに「何が足りないか」を知識グラフ（知識图谱）で可視化し、AI 先生がその不足を補う学習システムです。日本語文法と Python プログラミングの 2 科目を提供し、学生側・教師側の画面は中国語 / 日本語で動きます。

この文書はリポジトリ内のコード・スクリプトを根拠に書いています。パスはすべてリポジトリルートからの相対表記で、特定のマシンの絶対パスは書いていません。

## 概要

- 学生は問い先生（AI 先生との対話）・問題演習・書き取り（単語・用語の暗記）・教材（課文）で学習し、知識グラフで全体像と自分の習得状況を見ます。
- 教師は学情（クラス全体と個人の学習状況）・教師アシスタント（AI による状況確認とドラフト作成）・学生管理・科目管理・グラフ管理を使って教える側を支えます。
- 実装は中国語 DSL プロジェクトの流儀に従います。契約（contracts/）→ 実体（entities/）→ サービス（services/）→ ルーティング（routes/）→ 画面（ui/）という順で書き、`gen` というコード生成器がこれを Flask + SQLite のアプリにコンパイルします。

## 主な機能

### 学生側（`/`）

| 画面 | ファイル | 説明 |
|---|---|---|
| 問い先生（问老师） | `ui/teacher.ui` | AI 先生に質問すると、知識グラフと学習記録をもとに回答。伝達（お知らせ）もここに届く |
| 問題演習（做题） | `ui/quiz.ui` | 一枚の問題カードに一問。自由練習・弱点復習・課別練習のモード付き |
| 書き取り（默写） | `ui/quiz_dictation.ui` | 一枚のカードに一語、1 回 10 問。間違えた語は間違い帳（错题本）に |
| 教材（textbook） | `ui/textbook.ui` | 課文の一覧と閲覧 |
| 知識グラフ（node） | `ui/node.ui` | テックツリー風のマップと詳細ポップアップ |
| 学習進捗（progress） | `ui/progress.ui` | 進捗の概要と弱点の確認 |

### 教師側（`/teacher`）

| 画面 | ファイル | 説明 |
|---|---|---|
| 学情（report） | `ui/report.ui` | クラス全体の表と学生ごとの詳細 |
| 教師アシスタント | `ui/teacher_assist.ui` | 全体の状況確認・特定学生・知識点ごとの習得・授業提案を質問。出題や伝達は「ドラフト → 先生が確認 → 反映（7 日以内なら取り消し可）」の二段構え |
| 学生管理 | `ui/student.ui` | 学生アカウントの作成・パスワードリセット・停止/再有効化 |
| AI 先生設定 | `ui/teacher_note.ui` | AI 先生の振る舞い設定と全体への伝達 |
| 教材インポート | `ui/textbook_import.ui` | 課文の取り込み（プレビュー → 確認） |
| 科目管理 | `ui/subject.ui` | 科目の作成・公開/非公開・有効化/停止・メンバー管理 |
| グラフ管理 | `ui/kg_manage.ui` | 知識点・前提辺・項目の編集と csv/json/md での一括导入（取り込み、プレチェック付き）・書き出し |
| 課文閲覧 | `ui/teacher_lesson.ui` | 教師用の課文閲覧（読み取り専用） |
| 教材（教学材料） | `ui/teacher_material.ui` | アシスタントが生成した教案・練習・講義資料・学情レポートの閲覧 |

ログイン画面は `ui/auth.ui`（複数人モードのときだけ使う）。

## 科目

科目ごとにレベル（levels）と機能の有効/無効（caps）を持ちます（`entities/subject.entity`、`contracts/subject.md`）。

| 科目 | コード | レベル | caps の例 |
|---|---|---|---|
| 日本語文法（日语语法） | `jp_grammar` | N5, N4, N3, N2, N1 | vocab・dictation・lesson・jp_judge・textbook_import（`setup/migrate_subject.py` の初期値） |
| Python プログラミング | `python` | 入門, 基礎, 進階 | dictation |

- 日本語文法は中国語話者向けの科目なので、講義や問題の本文は中国語です（画面言語は日本語にできます）。初期データは知識点（知识点）69・前提辺 112・項目（条目）192・対照（对照）20・課文シリーズ 1・課文 125・単語 8105・問題 466（`setup/init_data.py` の既定値）。
- Python 科目の内容は `content/python_v1/` にあります。教材 13 課（入門 4・基礎 4・進階 5、中国語・日本語両版）、書き取り問題 136 問（`dictation/questions.json`）、問題演習の題庫 99 問（`quiz_v2.txt`、日本語版は `ja/quiz_question.tsv`）。
- 科目は 1 番の日本語文法を保護しています（停止不可・非公開化不可）。新しい科目は既定で非公開・ドラフトで、学生を割り当てて「有効化」すると学生側に見えます。

## 多言語対応

- **画面言語**：中国語 / 日本語。ブラウザの言語とアカウント設定（`account_user.lang`）で決まります。日本語の文案は `i18n/ja.tsv`（中文原文 → 日本語の 2 列 TSV）に置き、ビルド時に `web/i18n.ja.js` へコンパイルされ、画面上で文字列まるごと置換されます（見つからない場合は中国語にフォールバック）。
- **AI の回答言語**：問い先生はアカウントの言語が日本語（ja）のとき、システムプロンプトの末尾に「日本語で答える」指示を足します（`services/tutor.zs`）。
- **内容の翻訳表**：科目名・課文シリーズ名などの翻訳は `subject_content_translation` 表（キーは テーブル + 行 + フィールド + 言語、現在は ja のみ）に持ち、訳がない場合は中国語にフォールバックします。1 番科目の名前の訳は `setup/names_ja.tsv` から `init_data.py` が書き込みます。日本語内容の导入（取り込み）スクリプトは `scripts/migrate_subject_content_translation.py` と `scripts/import_content_ja.py`（`--apply` で反映）。
- **残留チェック**：日本語画面に中国語が残っていないかを `tests/kg_v4/e2e_ja_residue.py` が機械的に確認します（サービス・ルーティングの报错文案（エラーメッセージ）と画面ラベルの静的な確認も含む）。

## アーキテクチャ

中国語 DSL（`.entity` / `.zs` / `.ui` / 契約 markdown）で書き、`gen` が Flask + SQLite のコードを生成します。旧 `kg/` とは独立して共存し、互いに依存しません。

| ディレクトリ | 内容 |
|---|---|
| `kg_v4/contracts/` | 20 モジュールの契約（公開関数と用例）。契約検査と回帰はここを根拠にする |
| `kg_v4/entities/` `kg_v4/queries/` | 実体（表）とクエリ SQL |
| `kg_v4/services/` `kg_v4/routes/` | ビジネス関数と 16 ファイル・計 221 本の API |
| `kg_v4/ui/` | 16 個の `.ui`（学生側・教師側の画面定義） |
| `kg_v4/plan/top.zs` | モジュール一覧と依存関係（契約検査・回帰が読む） |
| `kg_v4/setup/` | 初期データ投入・移行スクリプト |
| `kg_v4/scripts/` | 内容の导入（日本語訳・Python 書き取りなど） |
| `kg_v4/i18n/` | 画面の日本語文案（`ja.tsv`） |
| `content/python_v1/` | Python 科目の教材・書き取り・題庫のデータ |
| `scripts/build_bundle.sh` | 配布パッケージの作成（中国語版・日本語版共通の入口） |

サービス層の変更は dslagent v3（`tools/dslagent`）の運用を前提にしています。`audit2`（契約検査つきのチェック）→ `change2`（モジュール単位で一括変更）→ `fix2`（チェックと変更のループ）の順で回し、契約違反があると回帰に入りません。使い方は `kg_v4/plan/dslagent_brief.md` を参照してください。

## セットアップ（開発環境）

リポジトリルートで（Python はリポジトリの `.venv/bin/python` を使います）:

```bash
# 初期データを入れる（教師アカウントも作れる。パスワードは環境変数から読む）
.venv/bin/python kg_v4/setup/init_data.py --teacher admin
#   教師のパスワードは環境変数 KG_TEACHER_PASSWORD で渡す（コマンドラインには書かない）

# サービスを立てる（例としてポート 8188 を指定）
.venv/bin/python -m gen run kg_v4 --登录 --port 8188           # オフラインの仮モデル
.venv/bin/python -m gen run kg_v4 --登录 --real --port 8188    # 実モデル（環境変数 ZHIPU_API_KEY が必要。名前のみ記載）
```

- `gen run` は `ensure_db`（表と索引の補完）→ 画面のコンパイル → サービス起動の順で動きます。既定のポートは起動ログに出ます。
- Python 科目の内容はリポジトリの内容から後入れもできます：
  `kg_v4/scripts/import_python_dictation.py`（書き取り 136 問、`--enable-caps` で dictation 機能を有効化）、`scripts/migrate_subject_content_translation.py` + `scripts/import_content_ja.py`（日本語訳の反映）。

## 配布パッケージ

```bash
bash scripts/build_bundle.sh --lang ja [出力先]   # 日本語版（--lang zh で中国語版）
```

- 基線は `git archive HEAD` なので、コミット済みの内容だけが入ります。パッケージには `engine/`・`project/`・`content/`・`scripts/`・`wheels/` と `README.md`（日本語版は `README.ja.md` も）が入ります。
- 作成時に、パッケージ内のスクリプトも生成されます：`scripts/install.sh`（venv 構築・オフラインインストール）→ `scripts/init_data.sh`（空のデータディレクトリと初期アカウント）→ `scripts/start.sh`（既定は `127.0.0.1:8119`、再実行に強い起動）→ `scripts/load_python_content.sh`（Python 内容の导入と行数の自検）。`stop.sh`・`watch.sh`・`deploy.sh` も入ります。
- 本番への反映は `deploy.sh` が担います（dry-run で確認 → 反映 → バックアップという流れ。概念としての説明で、マシン固有のパスは含みません）。
- 作成後の検査で `config.json`・`.auth_secret`・`*.db` が入っていないこと、マシン固有の絶対パスが文中に現れていないことが確認されます。

## テスト

```bash
.venv/bin/python tests/kg_v4/test_project.py   # 契約検査 + 全量回帰 + API コンパイル + 初期化スクリプト（約 1 分）
bash tests/run_all.sh                           # 全体の回帰（下記の kg_v4 関係のグループを含む）
```

`tests/run_all.sh` の kg_v4 関係の主なグループ:

- `kg_v4项目`：`test_project.py`（契約検査 + 回帰 + コンパイル + 初期化）。
- `助手草稿`・`助手材料`・`助手学情`・`教师助手人设`・`问老师人设`：教師アシスタントと問い先生の動作。人設（ペルソナ）は golden ファイル（`assist_persona_golden.json` など）と比較します。
- `科目等级`・`默写题库导入`・`课文导入脚本`：科目・导入まわり。
- `kg_v4走查`：`tests/kg_v4/e2e_walk.py`。学生側・教師側の全画面と科目管理の一連の流れを playwright + Chrome で走る（playwright を入れた別の venv `PW_PYTHON` が必要で、ないときは「跳过（スキップ）」）。
- `日语残留检查`：`tests/kg_v4/e2e_ja_residue.py`。日本語アカウントで全画面を回り、中国語の残留を探す。
- 画面多言語の単体テストは `tests/gen/test_i18n.py`（`界面多语言` グループ）。

## 運用上の注意

- 認証ファイル・鍵・トークン・パスワードをこの README やリポジトリの文書に載せないでください。実モデルの API キーは環境変数 `ZHIPU_API_KEY` で渡します（ここでは変数名だけを書いています）。
- 既知の制限（要点のみ。詳細は中文 README の「已知限制」節を参照）:
  - 一部のエラー文言がまだ中国語です（教師アシスタントの追問文・ドラフト検証の明細・エンジン由来の插值（変数埋め込み）メッセージなど。日本語残留スキャンが 0 なのは、仮モデルではこれらの分岐に入らないため）。
  - グラフ管理の書き出しポップアップの見出し（`# 知识点` など）は中国語のまま。
  - 日本語科目の N1 題庫は 10 問しかなく、N1 自由練習は 1 回で満たないことがあります。
  - 書き取りの「ランダム」はタイムスタンプの剰余による擬似乱数です（同一秒では同じ語になり得る）。
  - CPU の重いリクエストは同一プロセスの他のリクエストを遅くします（GIL）。古い SQLite では `json_each` と窗口関数（ウィンドウ関数）に依存する SQL が失敗します。

## 出典・ライセンス

- 日本語文法科目の文法ポイントは hanabira.org の内容をもとにしており、CC BY 4.0 で出典を表記して利用しています（`kg/content/NOTICE.md`、`kg_v4/setup/init_data.py` の課文シリーズ情報）。
