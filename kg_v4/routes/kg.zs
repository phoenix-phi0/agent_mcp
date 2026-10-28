接口 GET /kg/point
  设 r = 调用 kg.取知识点 code={code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/points
  设 r = 调用 kg.列知识点 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/prerequisites
  设 r = 调用 kg.列前置 code={code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/successors
  设 r = 调用 kg.列后续 code={code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/ancestors
  设 r = 调用 kg.列祖先 code={code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/descendants
  设 r = 调用 kg.列后代 code={code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/roots
  设 r = 调用 kg.列根节点 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/layers
  设 r = 调用 kg.列分层 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/edge/add 角色 teacher
  设 r = 调用 kg.加前置边 pre_code={pre_code} point_code={point_code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/export
  设 r = 调用 kg.导出图 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/item
  设 r = 调用 kg.取条目 code={code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/items
  设 r = 调用 kg.列条目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/items/by-point
  设 r = 调用 kg.按知识点列条目 point_code={point_code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/contrasts
  设 r = 调用 kg.列对照 code={code 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/import/points 角色 teacher
  设 file_path = 存文件 file 类型=md,txt 上限=20MB
  如果 {file_path} 开头是 [
    返回 {"error":"{file_path}"} 400
  结束
  设 r = 调用 kg.导入知识点 file_path={file_path} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/import/items 角色 teacher
  设 file_path = 存文件 file 类型=md,txt 上限=20MB
  如果 {file_path} 开头是 [
    返回 {"error":"{file_path}"} 400
  结束
  设 r = 调用 kg.导入条目 file_path={file_path} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/import/contrasts 角色 teacher
  设 file_path = 存文件 file 类型=md,txt 上限=20MB
  如果 {file_path} 开头是 [
    返回 {"error":"{file_path}"} 400
  结束
  设 r = 调用 kg.导入对照 file_path={file_path} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/point/create 角色 teacher
  设 r = 调用 kg.建知识点 code={code} title={title} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/point/update 角色 teacher
  设 r = 调用 kg.改知识点 code={code} title={title} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/point/delete 角色 teacher
  设 r = 调用 kg.删知识点 code={code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/edge/delete 角色 teacher
  设 r = 调用 kg.删前置边 pre_code={pre_code} point_code={point_code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/item/create 角色 teacher
  设 r = 调用 kg.建条目 code={code} name={name} point_code={point_code} after_form={after_form 或} prev_code={prev_code 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/item/update 角色 teacher
  设 r = 调用 kg.改条目 code={code} name={name} point_code={point_code} after_form={after_form 或} prev_code={prev_code 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/item/delete 角色 teacher
  设 r = 调用 kg.删条目 code={code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/contrast/add 角色 teacher
  设 r = 调用 kg.加对照 a_code={a_code} b_code={b_code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/contrast/delete 角色 teacher
  设 r = 调用 kg.删对照 a_code={a_code} b_code={b_code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/refs 角色 teacher
  设 r = 调用 kg.查引用 code={code} kind={kind 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/import/edges 角色 teacher
  设 file_path = 存文件 file 类型=md,txt 上限=20MB
  如果 {file_path} 开头是 [
    返回 {"error":"{file_path}"} 400
  结束
  设 r = 调用 kg.导入前置边 file_path={file_path} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/import/preview 角色 teacher
  设 file_path = 存文件 file 类型=md,txt,csv,json 上限=20MB
  如果 {file_path} 开头是 [
    返回 {"error":"{file_path}"} 400
  结束
  设 r = 调用 kg.导入预检 kind={kind} file_path={file_path} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/import/confirm 角色 teacher
  设 r = 调用 kg.确认导入 kind={kind} file_path={file_path} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /kg/export/text 角色 teacher
  设 r = 调用 kg.导出文本 kind={kind 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /kg/manage/home 动作 kgm_home 角色 teacher
  设 r = 调用 kg.图谱管理页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /kg/manage/point/open 动作 kgm_point_open 角色 teacher
  设 r = 调用 kg.载入知识点页面 learner={learner} kgp_orig={kgp_orig 或} code={code 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 form {r}
结束

接口 POST /kg/manage/point/save 动作 kgm_point_save 角色 teacher
  设 r = 调用 kg.保存知识点页面 learner={learner} kgp_title={kgp_title} kgp_orig={kgp_orig 或} kgp_code={kgp_code 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 知识点已保存
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /kg/manage/point/delete 动作 kgm_point_delete 角色 teacher
  设 r = 调用 kg.删知识点页面 learner={learner} kgp_orig={kgp_orig} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 知识点已删除
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /kg/manage/edge/add 动作 kgm_edge_add 角色 teacher
  设 r = 调用 kg.加前置边页面 learner={learner} edge_pre={edge_pre} edge_point={edge_point} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 前置边已加上
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /kg/manage/edge/delete 动作 kgm_edge_delete 角色 teacher
  设 r = 调用 kg.删前置边页面 learner={learner} edge_key={edge_key} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 前置边已删除
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /kg/manage/item/open 动作 kgm_item_open 角色 teacher
  设 r = 调用 kg.载入条目页面 learner={learner} kgi_orig={kgi_orig 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 form {r}
结束

接口 POST /kg/manage/item/save 动作 kgm_item_save 角色 teacher
  设 r = 调用 kg.保存条目页面 learner={learner} kgi_name={kgi_name} kgi_point={kgi_point} kgi_orig={kgi_orig 或} kgi_code={kgi_code 或} kgi_after={kgi_after 或} kgi_prev={kgi_prev 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 条目已保存
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /kg/manage/item/delete 动作 kgm_item_delete 角色 teacher
  设 r = 调用 kg.删条目页面 learner={learner} kgi_orig={kgi_orig} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 条目已删除
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /kg/manage/contrast/add 动作 kgm_contrast_add 角色 teacher
  设 r = 调用 kg.加对照页面 learner={learner} ct_a={ct_a} ct_b={ct_b} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 对照已加上
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /kg/manage/contrast/delete 动作 kgm_contrast_delete 角色 teacher
  设 r = 调用 kg.删对照页面 learner={learner} ct_key={ct_key} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 对照已删除
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /kg/manage/import/preview 动作 kgm_import_preview 角色 teacher
  设 imp_upload_path = 存文件 imp_upload 类型=md,txt,csv,json 上限=20MB
  如果 {imp_upload_path} 开头是 [
    返回 {"error":"{imp_upload_path}"} 400
  结束
  设 r = 调用 kg.导入预检页面 learner={learner} imp_kind={imp_kind} imp_upload_path={imp_upload_path} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /kg/manage/import/confirm 动作 kgm_import_confirm 角色 teacher
  设 r = 调用 kg.确认导入页面 learner={learner} imp_kind={imp_kind} imp_file={imp_file} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 导入完成
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /kg/manage/export 动作 kgm_export 角色 teacher
  设 r = 调用 kg.导出页面 learner={learner} exp_kind={exp_kind 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

