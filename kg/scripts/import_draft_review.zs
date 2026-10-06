# 一课草稿通过 / 驳回，然后回刷页面：给了 job（审阅页，行上带的 draft）回刷
# 审阅页，没给（编辑页，地址里是 draft）回刷编辑页。
#
# 参数 draft、job（没有是 -）、review（通过 / 驳回）。

用包 db http common data

如果 {draft 或} 为空
  响应 state {"job_note":"缺 draft（哪一课）"}
  返回 bad
结束
设 args.draft = {draft}
设 args.review = {review}
设 affected = 写库表 app.db import_draft_review {args}
设 owner = 查一值表 app.db import_draft_job {args}
如果 {owner} 为空
  返回 missing
结束
设 issue_args.job = {owner}
设 affected = 写库表 app.db import_issues {issue_args}
如果 {job} 等于 -
  执行 scripts/import_draft_view.zs draft={draft} with_form=否
否则
  执行 scripts/import_job_view.zs job={job}
结束
