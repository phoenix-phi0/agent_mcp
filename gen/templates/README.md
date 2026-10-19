# gen 模板集

<!-- 由 `python -m gen tpl doc` 按各套的 set.json 生成，不要手改 -->

> 区别：仓库根的 `templates/`（db/、frontend/）是建库和前端页面模板；这里的 `gen/templates/` 是 `gen` 按实体生成 SQL / 接口 / 界面用的模板集。

每套一个目录，目录里 `set.json` 是清单（名、说明、继承、要求字段、参数、项目级文件）。继承的套只写与基础套的差异；`python -m gen tpl show <套>` 看细节。

## _base（抽象基础套）

抽象基础套：default / full / private 共用的模板骨架（Jinja extends + 变量/块留出差异点）。不能直接用。

- 继承：无
- 要求字段：无
- 本套文件：`delete.sql.j2`（本套）、`insert.sql.j2`（本套）、`list.sql.j2`（本套）、`one.sql.j2`（本套）、`routes.zs.j2`（本套）、`screens.ui.j2`（本套）、`update.sql.j2`（本套）

## default

默认：列表 / 编辑表单 / 详情三个界面，只取前几个短字段；增删改后不回传列表。

- 继承：_base
- 要求字段：无
- 本套文件：`list.sql.j2`（覆盖）、`routes.zs.j2`（覆盖）、`screens.ui.j2`（覆盖）、`update.sql.j2`（覆盖）
- 继承来的文件：`delete.sql.j2`（来自 _base）、`insert.sql.j2`（来自 _base）、`one.sql.j2`（来自 _base）

## full

完整：一个列表界面 + 浮层（新建、编辑共用），增删改后返回最新列表，取全部列。

- 继承：_base
- 要求字段：无
- 本套文件：无
- 继承来的文件：`delete.sql.j2`（来自 _base）、`insert.sql.j2`（来自 _base）、`list.sql.j2`（来自 _base）、`one.sql.j2`（来自 _base）、`routes.zs.j2`（来自 _base）、`screens.ui.j2`（来自 _base）、`update.sql.j2`（来自 _base）

## private

私有：在 full 上加登录隔离——每人只看、只改自己的（owner 列），附带账号（用户表、注册登录、角色）项目级文件。

- 继承：full → _base
- 要求字段：owner
- 本套文件：`delete.sql.j2`（覆盖）、`insert.sql.j2`（覆盖）、`list.sql.j2`（覆盖）、`one.sql.j2`（覆盖）、`routes.zs.j2`（覆盖）、`screens.ui.j2`（覆盖）、`update.sql.j2`（覆盖）

项目级文件（每个项目一次）：

- `entities/user.entity` ← `project/user.entity.j2`
- `queries/user_insert.sql` ← `project/user_insert.sql.j2`
- `queries/user_by_name.sql` ← `project/user_by_name.sql.j2`
- `routes/auth.zs` ← `project/auth.zs.j2`
- `ui/auth.ui` ← `project/auth.ui.j2`
- `queries/user_auth.sql` ← `project/user_auth.sql.j2`，当参数「角色」非空
- `routes/auth_roles.zs` ← `project/auth_roles.zs.j2`，当参数「角色」非空

| 参数 | 默认 | 说明 |
|---|---|---|
| 认证 | `"必须"` | 必须＝整个项目要求登录；可选＝平时不用登录，启动加 --登录 才要求 |
| 开放注册 | `true` | false 时 /auth/register 保留接口头但回 403（账号由教师建） |
| 角色 | `[]` | 角色代号列表（来自功能清单）。非空时 user 加 role 列（默认最后一个）并生成 user_auth.sql、auth_roles.zs |
| 角色名 | `{"teacher": "教师", "student": "学生", "admin": "管理员", "manager": "经理", "user": "用户", "owner": "店主"}` | 角色代号 → 中文名（auth_roles.zs 的「认证 角色」行）；不在表里的用代号本身 |
| 关注册标记 | `"# 自助注册已关闭"` | 关注册后写进接口体的标记行；close_register 靠它判断是否已关 |
