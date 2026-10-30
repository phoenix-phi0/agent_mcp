接口 POST /teacher_assist/ask 动作 assist_send 角色 teacher
  设 r = 调用 teacher_assist.问助手页面 current_user={current_user} message={content} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r.page}
结束

接口 POST /teacher_assist/history 动作 assist_state 角色 teacher
  设 r = 调用 teacher_assist.列对话页面 current_user={current_user} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 GET /teacher_assist/messages 角色 teacher
  设 r = 调用 teacher_assist.列对话 current_user={current_user} limit={limit 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /teacher_assist/draft/open 动作 assist_draft_open 角色 teacher
  设 r = 调用 teacher_assist.取草稿页面 current_user={current_user} draft_id={draft_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/draft/confirm 动作 assist_draft_confirm 角色 teacher
  设 r = 调用 teacher_assist.确认草稿页面 current_user={current_user} draft_id={draft_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/draft/discard 动作 assist_draft_discard 角色 teacher
  设 r = 调用 teacher_assist.放弃草稿页面 current_user={current_user} draft_id={draft_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/draft/undo 动作 assist_draft_undo 角色 teacher
  设 r = 调用 teacher_assist.撤销草稿页面 current_user={current_user} draft_id={draft_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/attach 动作 assist_attach 角色 teacher
  设 assist_file_path = 存文件 assist_file 上限=10MB
  如果 {assist_file_path} 开头是 [
    返回 {"error":"{assist_file_path}"} 400
  结束
  设 assist_file_info = 上传信息 assist_file
  设 file_name = {assist_file_info.name}
  设 file_size = {assist_file_info.size}
  设 file_ext = {assist_file_info.ext}
  设 r = 调用 teacher_assist.挂附件页面 current_user={current_user} assist_file_path={assist_file_path} file_name={file_name 或} file_size={file_size 或} file_ext={file_ext 或} message={content 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r.page}
结束

接口 POST /teacher_assist/attach/pick 动作 assist_attach_pick 角色 teacher
  设 r = 调用 teacher_assist.挂上附件页面 current_user={current_user} file_id={att_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/attach/drop 动作 assist_attach_drop 角色 teacher
  设 r = 调用 teacher_assist.移除附件页面 current_user={current_user} file_id={file_id 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/attach/delete 动作 assist_attach_delete 角色 teacher
  设 r = 调用 teacher_assist.删除附件页面 current_user={current_user} file_id={att_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/material/save 动作 assist_material_save 角色 teacher
  设 r = 调用 teacher_assist.材料保存页面 current_user={current_user} mat_id={mat_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/material/export 动作 assist_material_export 角色 teacher
  设 r = 调用 teacher_assist.材料导出跳转 current_user={current_user} mat_id={mat_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 打开导出
  消息 系统 {_msg} ok
  响应 go #教学材料?浮层=导出材料&mat_id={r.mat_id}
结束

接口 POST /teacher_assist/material/to_draft 动作 assist_material_to_draft 角色 teacher
  设 r = 调用 teacher_assist.材料转草稿页面 current_user={current_user} mat_id={mat_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束
