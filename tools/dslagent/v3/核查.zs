# 核查：新建完成之后（或任何时候）找问题。程序检查用动词（全局检查 / 全量回归 方式=核查 / 接口冒烟 方式=核查，有代码才跑、只报告不重做），
# 需要判断的地方直接 派任务（规划层一个子任务：需求、top.zs、接口目录、各模块约定全文，不读代码），结果合并存成问题清单。
# 子任务的入参是文件名列表：工作目录（项目目录）内的文件由 派任务 读出，每个文件最多 400 行，超出的部分读不到；需求全文直接当一项文本放进去。
# 存问题清单 只信成功的子任务：失败的记进 unchecked（不能当作没问题），回复前后矛盾 / 缺字段的条目丢进 dropped。
# 没有 plan/top.zs 时也能跑：全局检查 0 条，回归 / 冒烟跳过，规划层照派（文件不存在的项会在入参里注明）。
# 顶层脚本的入参名用英文；model 是引擎关键字别名，不能当变量名，所以叫 llm。req 是需求全文。
# 参数：req task? llm=sonnet
用包 common v3 text
模型 {llm}
设 a = 全局检查
设 b = 全量回归 方式=核查
设 c = 接口冒烟 方式=核查
设 files = 列表加项 [] plan/catalog.md
设 top = 已有规划 顶层
如果 {top} 不为空
  设 files = 列表加项 {files} plan/top.zs
  设 layers = 依赖分层
  遍历 group 于 {layers}
    遍历 m 于 {group}
      设 files = 列表加项 {files} contracts/{m}.md
    结束
  结束
结束
设 files = 列表加项 {files} {req}
设 desc = 规划层核查：对照需求、顶层规划、接口目录和各模块约定，找职责重复、模块间缺口、跨模块调用对不上、偏离需求的地方；已知问题不要重复；只读不改。
设 logic = 回复中items的每一项必须是对象，字段：issue（问题描述）、modules（涉及模块名，逗号隔开）、basis（依据：文件或位置）；没有问题时 found 填 否、items 填空列表。
设 p = 派任务 {desc} {files} {logic} found:是否,items:列表
设 s = 存问题清单 程序={a} 回归={b} 冒烟={c} 规划={p}
返回 {"count": {s.count}, "path": "{s.path}", "unchecked": {s.unchecked}, "dropped": {s.dropped}}
