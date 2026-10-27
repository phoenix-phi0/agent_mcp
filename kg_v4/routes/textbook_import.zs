接口 POST /textbook_import/home 动作 import_home 角色 teacher
  设 r = 调用 textbook_import.导入首页 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /textbook_import/poll 动作 import_poll 角色 teacher
  设 r = 调用 textbook_import.任务视图 task_id={job} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /textbook_import/load 动作 import_load 角色 teacher
  设 r = 调用 textbook_import.导入视图 task_id={job 或} draft_id={draft 或} series_code={manage 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /textbook_import/task/create 动作 import_create 角色 teacher
  设 document_path = 存文件 document 类型=pdf,docx,md,txt 上限=20MB
  如果 {document_path} 开头是 [
    返回 {"error":"{document_path}"} 400
  结束
  设 document_info = 上传信息 document
  设 file_name = {document_info.name}
  设 file_size = {document_info.size}
  设 file_ext = {document_info.ext}
  设 r = 调用 textbook_import.创建导入任务 series_code={series} series_name={label} document_path={document_path} code_prefix={prefix 或} source={source 或} license={license 或} lesson_level={lesson_level 或} rewrite={rewrite 或} overwrite={overwrite 或} file_name={file_name 或} file_size={file_size 或} file_ext={file_ext 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 已建任务
  消息 系统 {_msg} ok
  响应 go #教材导入?job={r.task_id}
结束

接口 POST /textbook_import/task/approve-mapped 动作 import_pass_mapped 角色 teacher
  设 r = 调用 textbook_import.一键通过页面 task_id={job} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /textbook_import/task/confirm 动作 import_confirm 角色 teacher
  设 r = 调用 textbook_import.确认导入页面 task_id={job} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /textbook_import/task/delete 动作 import_job_delete 角色 teacher
  设 r = 调用 textbook_import.删除任务 task_id={job} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 已删除这个导入任务
  消息 系统 {_msg} ok
  响应 go #教材导入
结束

接口 POST /textbook_import/chunk/retry 动作 import_chunk_retry 角色 teacher
  设 r = 调用 textbook_import.重试块页面 chunk_id={chunk_id} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /textbook_import/draft/pass 动作 import_draft_pass 角色 teacher
  设 r = 调用 textbook_import.审核草稿页面 draft_id={draft} decision=approve job={job 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /textbook_import/draft/reject 动作 import_draft_reject 角色 teacher
  设 r = 调用 textbook_import.审核草稿页面 draft_id={draft} decision=reject job={job 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /textbook_import/draft/save 动作 import_draft_save 角色 teacher
  设 r = 调用 textbook_import.保存草稿页面 draft_id={draft} title={title} draft_level={draft_level} seq={seq} summary={summary 或} formation={formation 或} explanation={explanation 或} examples={examples 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /textbook_import/draft/map-add 动作 import_map_add 角色 teacher
  设 r = 调用 textbook_import.加映射页面 draft_id={draft} map_typed={map_typed 或} map_add={map_add 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /textbook_import/draft/map-remove 动作 import_map_remove 角色 teacher
  设 r = 调用 textbook_import.去掉映射页面 draft_id={draft} map_code={map_code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /textbook_import/series/withdraw 动作 import_series_withdraw 角色 teacher
  设 r = 调用 textbook_import.撤下系列页面 series_code={manage} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 GET /textbook_import/tasks 角色 teacher
  设 r = 调用 textbook_import.列任务 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /textbook_import/task 角色 teacher
  设 r = 调用 textbook_import.取任务 task_id={task_id} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /textbook_import/draft 角色 teacher
  设 r = 调用 textbook_import.取草稿课 draft_id={draft_id} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /textbook_import/draft/update 角色 teacher
  设 r = 调用 textbook_import.修改草稿课 draft_id={draft_id} title={title} level={level} summary={summary} explain={explain} connection={connection} examples={examples} seq={seq} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /textbook_import/draft/mapping 角色 teacher
  设 r = 调用 textbook_import.改映射 draft_id={draft_id} kind={kind} action={action} code={code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /textbook_import/draft/review 角色 teacher
  设 r = 调用 textbook_import.审核草稿课 draft_id={draft_id} decision={decision} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /textbook_import/series 角色 teacher
  设 r = 调用 textbook_import.列已导入系列 series_code={series_code 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /textbook_import/chunk/prompt 角色 teacher
  设 r = 调用 textbook_import.块提示词 chunk_id={chunk_id} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束
