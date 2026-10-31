# 各科目自定义等级（K161）上线手册

给下一个任务用：把 K161 的代码更新到正式服务 8119（`/workspace/dslagent_exp/kg_v4_data`），再迁移 Python 科目的等级。
设计见 `subject_levels_design.md`（D1–D3 已定稿），实施记录见 `data/reports/kg_K161.md`。
**重启要用户批准**；正式库动之前先备份。

## 0. 结论先说
- **没有表结构变化**：`subject_info.levels` 列早就有了；实体只改了页面实体（`subject_view.subj_levels`、`quiz_view.pick_level`、`lesson_view.lesson_level`，都不进库）。**不用跑 ensure_db、不用迁移表**。
- 代码上线后、数据迁移前：Python 科目 levels 还是空串，按兼容规则当 N5–N1，旧的 99 道 N5 题照样能出，**不存在断档**。日语科目完全不变。
- 数据迁移三件事：① Python 科目 `levels='入门,基础,进阶'`；② 99 道题第 3 列换成新等级（`content/python_v1/quiz_v2.txt`）；③ `quiz_progress` 里科目 2 那一行的 `level=N5` 改成 `入门`。
- 为什么 ① 用 SQL 不用「科目管理」页面：D2 规则不许删在用的等级。库里 levels 为空串时旧等级按 N5–N1 算，N5 有 99 道题在用，从页面把等级改成 入门,基础,进阶 会被 400「等级「N5」还有…条记录在用」拒掉（这是预期行为）。所以迁移在停服窗口里直接写库。

## 1. 要覆盖的文件（相对 kg_v4/，以合并后的提交为准，用 `git diff --stat 9a45f19..<K161 最后提交> -- kg_v4` 再核一遍）
| 类 | 文件 |
|---|---|
| 契约 | contracts/subject.md、quiz.md、lesson.md、progress.md、report.md、tutor.md、assist_draft.md、textbook_import.md |
| 实体 | entities/subject.entity、quiz.entity、lesson.entity |
| 界面 | ui/subject.ui、quiz.ui、textbook.ui |
| 服务 | services/subject.zs、lesson.zs、quiz.zs、progress.zs、tutor.zs、assist_draft.zs、textbook_import.zs |
| 路由 | routes/subject.zs |
| 查询（改） | queries/subject_info_full.sql、subject_info_insert_general.sql、subject_info_insert_language.sql、subject_info_update.sql、lesson_level_by_point.sql |
| 查询（新） | queries/subject_levels_by_id.sql、subject_table_exists.sql、subject_use_quiz_question.sql、subject_use_lesson_text.sql、subject_use_quiz_progress.sql、subject_use_textbook_import_draft.sql、lesson_level_by_point_quiz.sql、lesson_count_by_point.sql、textbook_import_subject_caps.sql（共 9 个） |
| 计划 | plan/top.zs（subject 提供加 科目等级） |

不覆盖：app.db、.auth_secret、uploads/、sessions/、web/（start.sh 起服务时 `gen run` 会重新编译 web/）。

## 2. 步骤
### 2.1 上线前（服务照常跑）
```bash
cd /workspace/dslagent_exp
git -C /workspace/agent_mcp archive <K161 最后提交> kg_v4 | tar -x -C /tmp/k16x_src    # 导出新代码
diff -rq /tmp/k16x_src/kg_v4/contracts kg_v4_data/contracts   # 只应差上表里的文件（逐目录核 contracts entities queries routes services ui plan/top.zs）
# 只读看一眼 Python 科目（确认 id=2、code、levels 为空串）
sqlite3 "file:kg_v4_data/app.db?mode=ro" "SELECT id,code,name,kind,levels FROM subject_info"
sqlite3 "file:kg_v4_data/app.db?mode=ro" "SELECT level,count(*) FROM quiz_question WHERE subject_id=2 GROUP BY level"   # 期望 N5|99
sqlite3 "file:kg_v4_data/app.db?mode=ro" "SELECT learner,level,current_no FROM quiz_progress WHERE subject_id=2"
```
记下各表行数（同 K159 的 pre_stat）：日语 kg_point/kg_edge/kg_item/quiz_question/lesson_text = 69/112/192/466/125，Python kg_point/kg_item/quiz_question = 34/110/99。

### 2.2 停服窗口
1. 停看门狗（按进程组 `kill -TERM -<看门狗 PGID>`，`kill -0` 确认已停、watch.lock 可拿到），再 `./stop.sh`。不用 pkill/pgrep -f。
2. 备份：`cp -a kg_v4_data /workspace/dslagent_exp/backups/kg_v4_<时间>_before_K161`（含 .auth_secret，只拷不读），`diff -rq` 核对，app.db 记 sha256。
3. 覆盖第 1 节的文件；逐目录 diff 与提交一致。
4. 写库（一个事务；Python 科目按 2.1 查到的 id，下面写的是 2）：
```sql
BEGIN;
UPDATE subject_info SET levels = '入门,基础,进阶', updated_at = datetime('now','localtime') WHERE id = 2 AND levels = '';
SELECT changes();          -- 必须是 1；不是 1 就 ROLLBACK 停下查（id 不对，或已经迁过）
-- quiz_progress：科目 2 那一行 level=N5 → 入门（首级；学生下次点「开始」照常，选「全部」也按新顺序逐级）
UPDATE quiz_progress SET level = '入门' WHERE subject_id = 2 AND level = 'N5';
SELECT changes();          -- 期望 1（2.1 查到几行就是几）
SELECT id, code, levels FROM subject_info WHERE id = 2;     -- 核对：python | 入门,基础,进阶
COMMIT;
```
   两次 `changes()` 都在 COMMIT 之前看（`changes()` 只报最近一条语句），不对就 ROLLBACK。quiz_progress 那行也可以选择直接删掉让学生重开一轮（`DELETE FROM quiz_progress WHERE subject_id=2`），推荐改成 入门：保留轮次计数，不丢「这一轮」的成绩。
5. `./start.sh`，GET / 200；照 README 方式恢复看门狗（`setsid nohup ./watch.sh >> watch.log`）。

### 2.3 重灌 Python 题库（服务起来以后，用接口；推荐，和 K157 同一条路，也顺带验证新校验）
- 文件：`/workspace/dslagent_exp/content/python_v1/quiz_v2.txt`（K161 生成，sha256 `583dd077…5572`）。和 quiz.txt 只有第 3 列不同：points.csv 顺序 1–13 入门（38 题）、14–25 基础（34 题）、26–34 进阶（27 题），共 99 题。原 quiz.txt 未动。
- root 登录教师端后，`POST /quiz/import?subject=2`（上传字段 file），或在页面上导入。期望返回 `ok=1 total=99 imported=99 skipped=0`。
- 2.2 第 4 步到这一步之间（大约一两分钟），Python 题还都是 N5、不在新等级里：Python 学生选「全部」会 404「没有可出的题」、选具体等级出不了题。介意的话在停服窗口里改用备选 SQL（下面），就没有这个空档。
- 备选（不经接口、在停服窗口第 4 步里一起做）：
```sql
UPDATE quiz_question SET level = CASE
  WHEN (SELECT point_code FROM kg_item i WHERE i.code = quiz_question.item_code AND i.subject_id = 2) IN
       ('python.env','python.var','python.num','python.op','python.str','python.strm','python.fstr','python.io','python.bool','python.logic','python.if','python.while','python.for') THEN '入门'
  WHEN (SELECT point_code FROM kg_item i WHERE i.code = quiz_question.item_code AND i.subject_id = 2) IN
       ('python.list','python.listop','python.slice','python.tuple','python.dict','python.set','python.nest','python.func','python.param','python.ret','python.scope','python.lambda') THEN '基础'
  ELSE '进阶' END
WHERE subject_id = 2 AND level = 'N5';
```
   执行后核对 `SELECT level,count(*) FROM quiz_question WHERE subject_id=2 GROUP BY level` = 入门 38 / 基础 34 / 进阶 27（不等就 ROLLBACK）。

## 3. 实测清单（上线后）
- [ ] 库：`SELECT level,count(*) FROM quiz_question WHERE subject_id=2 GROUP BY level` = 入门 38 / 基础 34 / 进阶 27；日语五张表行数与上线前一致；`PRAGMA integrity_check` = ok。
- [ ] 日语学生：做题页等级下拉是 全部/N5/N4/N3/N2/N1；选「全部」出 N5 题、题卡「N5・…」；学习进度「各等级」5 行，和上线前数值一致。
- [ ] Python 学生（切到 Python 科目）：等级下拉是 全部/入门/基础/进阶；选「全部」先出入门题，题卡抬头「入门・选择」；学习进度「各等级」3 行（没有课文，靠题目等级兜底，不再全 0）。
- [ ] 问老师（Python 科目、没有学习记录的学生）说「出几道题」：回复「先从入门开始」，链接带 level=入门，点了能出题（真模型 1 句即可）。
- [ ] 科目管理：root 编辑 Python 科目，等级框是「入门,基础,进阶」；改成「入门,基础」保存 → 提示「等级「进阶」还有27条记录在用…」被拒；改回不动。
- [ ] 教材导入：Python 科目下点「开始解析」→ 403「本科目没开教材导入」；日语科目照常能建任务（只建不确认即可，或只看提示走到后面的校验）。
- [ ] 教师助手（Python 科目）出一道题的草稿：草稿 level 是 入门/基础/进阶 之一（不再是「-」），确认后进题库。
- [ ] server.log：Traceback 0、5xx 0；页面 JS 错误 0。

## 4. 回滚
- 代码：停看门狗和服务，把备份目录里第 1 节的文件拷回 kg_v4_data（新增的 sql 文件删掉或留着都行，旧代码不读），`start.sh`，恢复看门狗。
- 数据：旧代码不认自定义等级（「全部」只按 N5–N1 找），回滚代码时 Python 题必须改回 N5，否则 Python 学生出不了题：
```sql
BEGIN;
UPDATE quiz_question SET level = 'N5' WHERE subject_id = 2 AND level IN ('入门','基础','进阶');
UPDATE quiz_progress SET level = 'N5' WHERE subject_id = 2 AND level IN ('入门','基础','进阶');
UPDATE subject_info SET levels = '' WHERE id = 2;
COMMIT;
```
  回滚期间新产生的学习记录（progress_answer 等）不受影响，不要整库恢复备份（会丢这段时间的作答）；只有迁移本身把库弄坏时才用备份里的 app.db。
- 只回滚数据、不回滚代码也可以：新代码下 levels 为空串就按 N5–N1，上面三条 SQL 执行完就回到上线前的行为。
