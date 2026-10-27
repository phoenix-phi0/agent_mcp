迁移 只加
迁移 重建 quiz_progress dictation_progress lesson_pref


# 现在是谁（顶栏 auth_me）：用户、显示名、角色，以及 subjects（[{id,name}]，当前用户可见的科目）和 subject（当前科目 id）。
# 公开：没登录也能问，回空用户。依赖方向：account → subject（subject 是叶子模块）。
接口 POST /auth/me 动作 auth_me 公开
  设 r = 调用 account.认证信息 current_user={current_user} current_role={current_role} auth_mode={auth_mode}
  返回 {r}
结束
