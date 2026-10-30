接口 POST /assist_material/home 动作 material_home 角色 teacher
  设 r = 调用 assist_material.材料页面 current_user={current_user} mat_filter={mat_filter 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /assist_material/open 动作 material_open 角色 teacher
  设 r = 调用 assist_material.载入材料页面 current_user={current_user} mat_id={mat_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 form {r}
结束

接口 POST /assist_material/update 动作 material_update 角色 teacher
  设 r = 调用 assist_material.改材料页面 current_user={current_user} mat_id={mat_id} mat_title={mat_title 或} mat_kind={mat_kind 或} mat_content={mat_content 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 材料已保存
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /assist_material/save 动作 material_save 角色 teacher
  设 r = 调用 assist_material.保存材料页面 current_user={current_user} mat_id={mat_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 材料已保存
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /assist_material/export 动作 material_export 角色 teacher
  设 r = 调用 assist_material.导出材料页面 current_user={current_user} mat_id={mat_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /assist_material/delete 动作 material_delete 角色 teacher
  设 r = 调用 assist_material.删材料页面 current_user={current_user} mat_id={mat_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 材料已删除
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /assist_material/to_draft 动作 material_to_draft 角色 teacher
  设 r = 调用 assist_material.练习转草稿页面 current_user={current_user} mat_id={mat_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = {r.note}
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 GET /assist_material/list 角色 teacher
  设 r = 调用 assist_material.列材料 current_user={current_user} kind={kind 或} status={status 或} limit={limit 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束
