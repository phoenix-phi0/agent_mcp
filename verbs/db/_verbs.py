"""db 包：查 SQLite，SQL 写在 .sql 文件里。

## 为什么 SQL 不写在 DSL 里

动词参数不能有空格，而 SQL 全是空格——硬塞的话每条查询都要先存进变量，
两行才能查一次。更要紧的是拼字符串等于开放 SQL 注入，接口场景下用户
输入会直接进 WHERE。

所以 DSL 里只报查询名，SQL 放 `queries/` 下的 `.sql`：

```sql
-- queries/作者文章.sql
SELECT id, title, views FROM post
WHERE author = :author
LIMIT CAST(:limit AS INTEGER)
```

```
用包 db

设 posts = 查询 试验.db 作者文章 author=a01 limit=3
遍历 row 于 {posts}
  打印 {row.title}（{row.views}）
结束
```

参数走 `:名字` 占位符绑定，不是字符串拼接——注入不可能发生。参数名跟脚本
变量一样用英文 snake_case（`:limit`、`:current_user`）。

## 参数一律是字符串，数值比较要 CAST

**最容易踩的一条。** DSL 里的值全是文本，绑进 SQL 也是文本。

SQLite 有列亲和性：拿字符串跟 INTEGER 列比会自动转，所以
`WHERE views > :min_views` 能工作。但左边一变成表达式——`count(*)`、
`sum(x)`、`a + b`——亲和性就没了，比较退回纯值比较，而 SQLite 的类型
序里**文本永远大于数字**。结果恒真或恒假，**而且不报错**。

    HAVING count(r.score) >= :min_ratings                    -- 恒假
    HAVING count(r.score) >= CAST(:min_ratings AS INTEGER)   -- 对

`LIMIT :limit` 同理。

考虑过在动词里自动转（看着像数字就转），没做——那会变成一条所有查询
都受影响的隐式规则，而「什么算数字」永远有边界：`007` 转成 `7` 就匹配
不上文本编号列。写在 SQL 里，每条查询自己说清楚。

## 事务

```
用包 db

事务 学习.db
  写库 学习.db 记作答 learner={who} code={q} correct=1
  写库 学习.db 加错题 learner={who} code={q}
结束
```

块正常结束就提交，块内任何一步出错就回滚再把错抛出去。

引擎不认识数据库——它只在块的三个时刻调 `事务开始` / `事务提交` /
`事务回滚` 这三个约定好的动词，由这个包提供。

**事务里的连接是复用的**：`事务开始` 建一个连接挂在线程上，块内的
`写库` 和 `查询` 认出它就不再自己开。这样它们才在同一个事务里——
各开各的连接的话，提交是各提交各的，回滚也回滚不到别人。

连接挂在 `threading.local` 上而不是模块全局：Flask 是多线程的，全局
的话两个请求的事务会互相串。

**没有嵌套事务**。块里再开一个事务会报错——SQLite 的嵌套要用
SAVEPOINT，语义跟外层回滚怎么交互得另说，现在不值得。

## 查询目录跟着 workspace 走

`<workspace>/queries/`，跟库路径同一个基准。找不到就退回项目根的
`queries/`——教学那套的 workspace 是 `workspace/japanese/`，而 SQL 在
项目根，这个退路让它继续能用。

## 动词

    查询 库 查询名 参数=值 ...     返回行列表（每行一个对象）
    查一行 库 查询名 参数=值 ...   返回单个对象，没有就是空对象
    查一值 库 查询名 参数=值 ...   第一行第一列，**只适合单列查询**
    写库 库 语句名 参数=值 ...     增删改，返回影响行数
    事务开始 库 / 事务提交 / 事务回滚   给「事务」块用，一般不直接写
    列查询                        有哪些查询可用，附各自要的参数
    表结构 库 [表名]              看有哪些表、每张表有哪些列

参数最多八个。八而不是四：三四个很快就不够用了，而位置绑定的动词
参数个数只能写死。再多就该考虑把值塞进一个 JSON 参数了。

叫「写库」而不是「执行」：那个词已经是 DSL 的语句了（执行子脚本）。

`查一值` 拿的是第一行第一列，对多列查询会得到第一个字段，不是你想要
的那个。要某一列就用 `查一行` 再取字段。

## 出错怎么表现

查询失败返回错误文本而不是抛异常——接口场景下查询失败很常见，让脚本
能判断并给出像样的响应，比整个请求崩掉强。

**但事务里不一样**：`写库` 在事务中出错会抛异常，好让块回滚。不抛的话
一步失败、后面几步照跑，最后还提交了，那比崩掉糟得多。

代价是不检查的话错误会静默变成怪输出。稳妥的写法：

    设 行表 = 查询 试验.db 某查询
    如果 {行表.0.错误} 不为空
      打印 查询失败：{行表.0.错误}
    否则
      遍历 行 于 {行表}
        ...
      结束
    结束
"""

import re
import sqlite3
import threading
from pathlib import Path

# SQL 里的命名占位符。排除 :: 开头的（Postgres 的类型转换写法），
# 虽然 sqlite 用不到，但抄 SQL 过来时容易带进来
PARAM_RE = re.compile(r"(?<!:):([a-zA-Z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)")

# 事务期间复用的连接。挂在线程上而不是模块全局：Flask 多线程，
# 全局的话两个请求的事务会互相串。
#
# 而且**不放在这个文件里**：这个包每次「用包 db」都会被重新导入成一个新的
# 模块对象，放这儿的话每次加载都是一个新的 _tx。并发时一个请求的事务做到
# 一半，调到的动词可能来自另一次加载——事务开始挂上的连接，事务提交时找
# 不到，报「不在事务里」，那个连接没人提交也没人关，一直占着写锁，别的
# 请求等到超时报「database is locked」。90 次交错新建错过 7 到 34 次，
# 就是这个。tools/db_tx.py 是普通模块，只导入一次，所有加载共用。
from tools.db_tx import TX as _tx

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    workspace = Path(workspace).resolve()
    # 项目根：PACK_DIR 是 verbs/db，往上两级
    project_root = PACK_DIR.parent.parent

    def queries_dir() -> Path:
        """查询目录。跟 workspace 走，没有就退回项目根。

        每次调用时算而不是在 register 里定死：workspace 下的 queries/
        可能是脚本跑起来之后才建的，定死的话得重启才认。
        """
        local = workspace / "queries"
        return local if local.is_dir() else (project_root / "queries").resolve()

    def safe_db(path: str) -> Path:
        """库文件限制在工作目录内。

        路径来自脚本，而脚本内容可能是模型生成的——不检查的话
        「查询 ../../系统.db」就成立了。
        """
        p = (workspace / path).resolve()
        if p != workspace and workspace not in p.parents:
            raise ValueError(f"路径越界：{path}")
        return p

    def load_sql(name: str) -> str:
        """按名字读一条查询。名字里不能有路径分隔符。"""
        if "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"查询名不能含路径：{name}")
        d = queries_dir()
        f = d / (name if name.endswith(".sql") else f"{name}.sql")
        if not f.is_file():
            有哪些 = "、".join(sorted(p.stem for p in d.glob("*.sql")
                                     if not p.name.startswith("_")))
            raise ValueError(f"没有这条查询：{name}。{d} 下有：{有哪些 or '无'}")
        return f.read_text(encoding="utf-8")

    def parse_params(pairs) -> dict:
        """把 ["limit=3", "author=a01"] 变成字典。

        值一律保持字符串，不猜类型。数值比较由 SQL 里的 CAST 负责。

        这些键=值 是按空格切开再传进来的，所以值里不能有空格——字面量带
        空格会在源头被切成两截（「标题=第1课 第2课」的「第2课」变成下一个
        参数，早先不报错）。整个用 {变量} 传的值是切完才展开的，内部有空格
        /换行没事，但**首尾**空白会被 v.strip() 悄悄剪掉——跟 写库表（不剪）
        存的对不上，查询撞到别的行（教材导入同一文件去重失效就是这么来的）。
        所以首尾有空白直接报错；值可能含空格的（标题、正文、用户输入）装进
        一个对象，用 查询表/查一行表/查一值表/写库表 传。
        """
        out = {}
        for item in pairs:
            if not item.strip():
                continue
            k, sep, v = item.partition("=")
            if not sep:
                raise ValueError(
                    f"参数要写成 名=值，收到：{item}。这通常是前一个值里有空格，"
                    f"把它后面的词挤了出来；值可能含空格的参数装进对象，"
                    f"用 查询表/查一行表/查一值表/写库表 传")
            if v != v.strip():
                raise ValueError(
                    f"参数「{k.strip()}」的值首尾有空白：{v[:40]!r}，"
                    f"传进 SQL 前会被剪掉，存进去的就跟原值对不上"
                    f"（写库表 不剪，两边不一致）。"
                    f"把这个参数装进对象，用 查询表/查一行表/查一值表/写库表 传")
            out[k.strip()] = v.strip()
        return out

    def bind(sql: str, given: dict, pairs: bool = False) -> dict:
        """检查 SQL 要的参数都给了，返回绑定字典。

        少给直接报错而不是当 NULL：少传一个参数通常是笔误，静默当 NULL
        会让「查不到结果」变成一个要翻半天的谜。

        多给的只对 键=值 切开传的路径报错：那条路多出来的参数几乎总是值里
        有空格挤出来的「词=值」，静默丢弃会让「公式 E=mc2」存成「公式」。
        结构传参（查询表/查一行表/查一值表/写库表）不查——把整条记录当参数
        表传过去、SQL 只用其中几个字段是正常写法。
        """
        needed = set(PARAM_RE.findall(sql))
        missing = needed - set(given)
        if missing:
            raise ValueError(
                f"缺少参数：{'、'.join(sorted(missing))}。"
                f"这条查询要：{'、'.join(sorted(needed)) or '无'}")
        # 多给的不再丢掉——sqlite3 对多余的命名参数会报错，早先这里静默丢弃，
        # 值里有空格挤出来的「词=值」就无声消失了（「公式 E=mc2」存成了「公式」）
        extra = sorted(set(given) - needed)
        if extra and pairs:
            raise ValueError(
                f"用不到的参数：{'、'.join(extra)}。"
                f"这条查询要：{'、'.join(sorted(needed)) or '无'}。"
                f"多半是某个值里有空格，把它后面的「词=值」挤成了另一个参数；"
                f"值可能含空格的参数装进对象，用 查询表/查一行表/查一值表/写库表 传")
        return {k: v for k, v in given.items() if k in needed}

    def open_conn(db: str) -> sqlite3.Connection:
        p = safe_db(db)
        if not p.is_file():
            raise ValueError(f"数据库不存在：{db}")
        con = sqlite3.connect(p)
        con.row_factory = sqlite3.Row
        # 外键是每个连接各开一次的，建库时开了不算——不开的话外键约束
        # 只是摆设，插一条指向不存在的行也不报错
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def in_tx() -> sqlite3.Connection | None:
        return getattr(_tx, "con", None)

    def changed(con, sql, params) -> int:
        """执行一条增删改，返回影响的行数。

        不用 cursor.rowcount：Python 的 sqlite3 只在语句以 INSERT/UPDATE/
        DELETE 开头时才填它，以 WITH 开头的写语句（带递归检查的插入）拿到
        的是 -1——脚本里判「影响 等于 0」就永远不成立，被拒的插入看起来像
        成功了。total_changes 前后一减，不管语句怎么开头都对。
        """
        before = con.total_changes
        try:
            con.execute(sql, params)
        except sqlite3.IntegrityError as e:
            # 约束冲突（重名、必填为空、关联不存在）是用户输入的问题，不是
            # 服务器故障：翻译成人话、带上 409/400，路由器照这个回。所有写
            # 操作都经过这里，所以只在这一处翻译。
            from tools.db_errors import translate
            raise translate(e, workspace) from e
        return con.total_changes - before

    def as_dict(参数表) -> dict:
        """参数表可能是字典，也可能是 JSON 文本。

        脚本里整个参数就是一个变量引用时（`{request}`），引擎传的是原对象；
        夹在文字里时传过来的是 JSON 文本。两种都收。
        """
        if isinstance(参数表, str):
            import json as _json
            try:
                参数表 = _json.loads(参数表)
            except _json.JSONDecodeError:
                raise ValueError(f"参数表不是合法 JSON：{参数表[:80]}")
        if not isinstance(参数表, dict):
            raise ValueError(f"参数表要是一个对象，收到 {type(参数表).__name__}")
        return 参数表

    def text_values(d: dict) -> dict:
        """值一律转成字符串，跟按位置传参时一致。

        布尔要特别处理：str(True) 是 "True"，而 CAST('True' AS INTEGER)
        是 0——勾了的框会存成没勾，不报错。
        """
        out = {}
        for k, v in d.items():
            if isinstance(v, bool):
                out[k] = "1" if v else "0"
            elif v is None:
                out[k] = ""
            elif isinstance(v, (dict, list)):
                import json as _json
                out[k] = _json.dumps(v, ensure_ascii=False)
            else:
                out[k] = str(v)
        return out

    def query(db: str, name: str, pairs) -> list:
        """跑一条查询。事务里复用那个连接，否则用完就关。"""
        sql = load_sql(name)
        args = bind(sql, parse_params(pairs), pairs=True)
        con = in_tx()
        if con is not None:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        con = open_conn(db)
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @reg.verb("按名字执行 queries/ 下的查询，返回行列表。"
              "例如 查询 数据.db 作者文章 author=a01 limit=3。"
              "键=值 的值里不能有空格（带空格的字面量会被切开；值首尾空白会被剪掉——都报错），"
              "值可能含空格时装进对象用 查询表。")
    def 查询(库: str, 查询名: str, 参数一: str = "", 参数二: str = "",
             参数三: str = "", 参数四: str = "", 参数五: str = "",
             参数六: str = "", 参数七: str = "", 参数八: str = "") -> list:
        pairs = [参数一, 参数二, 参数三, 参数四, 参数五, 参数六, 参数七, 参数八]
        try:
            return query(库, 查询名, pairs)
        except (ValueError, sqlite3.Error):
            # 出错一律抛出去，不管在不在事务里。
            #
            # 早先块外返回 [{"错误": …}]，说是「脚本能判断」——但引擎没有
            # 捕获语句，实际没有脚本判断；而且那看起来就是一行数据：交给
            # 页面当表格，多一行空白，人看不到任何报错。这里的错几乎都是
            # 该修的毛病（查询名写错、少参数、SQL 写错、库被锁），不该被
            # 吞掉。抛出去之后，接口回错误、前端弹红色提示并还原输入；
            # 普通脚本停在出错那一行，带行号。
            raise

    @reg.verb("同「查询」，但只返回第一行。没有结果返回空对象。")
    def 查一行(库: str, 查询名: str, 参数一: str = "", 参数二: str = "",
               参数三: str = "", 参数四: str = "", 参数五: str = "",
               参数六: str = "", 参数七: str = "", 参数八: str = "") -> dict:
        pairs = [参数一, 参数二, 参数三, 参数四, 参数五, 参数六, 参数七, 参数八]
        try:
            rows = query(库, 查询名, pairs)
        except (ValueError, sqlite3.Error):
            # 一律抛出去，理由见「查询」。早先返回 {"错误": …}，看起来像
            # 一条查到的记录
            raise
        return rows[0] if rows else {}

    @reg.verb("第一行第一列，适合 count(*) 这类单列查询。"
              "多列查询会拿到第一个字段，要某一列请用「查一行」。")
    def 查一值(库: str, 查询名: str, 参数一: str = "", 参数二: str = "",
               参数三: str = "", 参数四: str = "", 参数五: str = "",
               参数六: str = "", 参数七: str = "", 参数八: str = "") -> str:
        pairs = [参数一, 参数二, 参数三, 参数四, 参数五, 参数六, 参数七, 参数八]
        try:
            rows = query(库, 查询名, pairs)
        except (ValueError, sqlite3.Error):
            # 一律抛出去，理由见「查询」
            raise
        if not rows:
            return ""
        return str(next(iter(rows[0].values()), ""))

    @reg.verb("执行增删改，返回影响的行数。语句同样放 queries/ 下。"
              "在「事务」块里出错会抛出去让整块回滚。"
              "键=值 的值里不能有空格（带空格的字面量会被切开；值首尾空白会被剪掉——都报错），"
              "值可能含空格时装进对象用 写库表。")
    def 写库(库: str, 语句名: str, 参数一: str = "", 参数二: str = "",
             参数三: str = "", 参数四: str = "", 参数五: str = "",
             参数六: str = "", 参数七: str = "", 参数八: str = "") -> str:
        pairs = [参数一, 参数二, 参数三, 参数四, 参数五, 参数六, 参数七, 参数八]
        try:
            sql = load_sql(语句名)
            args = bind(sql, parse_params(pairs), pairs=True)
            con = in_tx()
            if con is not None:
                # 事务里不 commit——那是「事务提交」的事
                return str(changed(con, sql, args))
            con = open_conn(库)
            try:
                n = changed(con, sql, args)
                con.commit()
                return str(n)
            finally:
                con.close()
        except (ValueError, sqlite3.Error):
            # 事务里必须抛：不抛的话一步失败、后面几步照跑、最后还提交了，
            # 那比崩掉糟得多。事务外也抛：返回 "[出错] …" 的话，调用方判
            # 「影响 等于 0」不成立，失败会被当成成功，接着回一句「已保存」
            raise

    def query_table(db: str, name: str, 参数表) -> list:
        """跟 query 一样，但参数来自一个字典，不按空格切。

        搜索就卡在这上面：关键词是用户输入的，「第一 条」按空格切之后成了
        `关键词=第一` 和 `条` 两截，绑定错位**而且不报错**。
        """
        sql = load_sql(name)
        args = bind(sql, text_values(as_dict(参数表)))
        con = in_tx()
        if con is not None:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        con = open_conn(db)
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()

    @reg.verb("同「查询」，但参数从一个结构里取——值含空格时用这个"
              "（搜索关键词几乎总是）。例如 查询表 app.db word_search {request}")
    def 查询表(库: str, 查询名: str, 参数表) -> list:
        return query_table(库, 查询名, 参数表)

    @reg.verb("同「查一行」，但参数从一个结构里取。"
              "例如 查一行表 app.db word_one {request}")
    def 查一行表(库: str, 查询名: str, 参数表) -> dict:
        rows = query_table(库, 查询名, 参数表)
        return rows[0] if rows else {}

    @reg.verb("同「查一值」，但参数从一个结构里取。"
              "例如 查一值表 app.db word_count {request}")
    def 查一值表(库: str, 查询名: str, 参数表) -> str:
        rows = query_table(库, 查询名, 参数表)
        if not rows:
            return ""
        return str(next(iter(rows[0].values()), ""))

    @reg.verb("同「写库」，但参数从一个结构里取——值含空格时用这个。"
              "例如 写库表 app.db article_insert {表单}")
    def 写库表(库: str, 语句名: str, 参数表) -> str:
        """参数装在一个字典里，不按空格切。

        表单字段的值常常带空格（标题、正文、日语例句），按位置传参时
        「标题=第一 条」会被切成两截，绑定错位而且不报错。
        """
        sql = load_sql(语句名)
        args = bind(sql, text_values(as_dict(参数表)))
        con = in_tx()
        if con is not None:
            return str(changed(con, sql, args))
        con = open_conn(库)
        try:
            n = changed(con, sql, args)
            con.commit()
            return str(n)
        finally:
            con.close()

    # ------------------------------------------------------------------
    # 事务：给引擎的「事务」块用
    # ------------------------------------------------------------------

    @reg.verb("开一个事务。一般不直接写，用「事务 库 … 结束」块。")
    def 事务开始(库: str) -> str:
        if in_tx() is not None:
            # 嵌套要用 SAVEPOINT，语义跟外层回滚怎么交互得另说，
            # 现在不值得。明确报错比默默共用一个事务清楚。
            return "[出错] 已经在事务里了，不支持嵌套事务"
        try:
            con = open_conn(库)
        except ValueError as e:
            return f"[出错] {e}"
        # sqlite3 默认在 INSERT/UPDATE 前自动开事务，显式 BEGIN 是为了
        # 让纯查询的块也处在一个一致的快照里
        con.execute("BEGIN")
        _tx.con = con
        return ""

    @reg.verb("提交事务。")
    def 事务提交() -> str:
        con = in_tx()
        if con is None:
            return "[出错] 不在事务里"
        try:
            con.commit()
        finally:
            con.close()
            _tx.con = None
        return ""

    @reg.verb("回滚事务。")
    def 事务回滚() -> str:
        con = in_tx()
        if con is None:
            return "[出错] 不在事务里"
        try:
            con.rollback()
        finally:
            con.close()
            _tx.con = None
        return ""

    # ------------------------------------------------------------------
    # 排查
    # ------------------------------------------------------------------

    @reg.verb("列出可用的查询，附各自需要的参数。")
    def 列查询() -> str:
        d = queries_dir()
        if not d.is_dir():
            return f"[没有查询目录] {d}"
        rows = [f"目录 {d}"]
        for f in sorted(d.glob("*.sql")):
            # 下划线开头的是 schema 之类的，不是查询
            if f.name.startswith("_"):
                continue
            sql = f.read_text(encoding="utf-8")
            需要 = sorted(set(PARAM_RE.findall(sql)))
            首行 = next((l.strip().lstrip("-").strip()
                        for l in sql.splitlines() if l.strip().startswith("--")),
                       "")
            rows.append(f"  {f.stem}（{'、'.join(需要) or '无参数'}）"
                        + (f"　{首行}" if 首行 else ""))
        return "\n".join(rows) if len(rows) > 1 else f"{d} 下没有查询"

    @reg.verb("看库里有哪些表；给了表名就看那张表有哪些列。")
    def 表结构(库: str, 表名: str = "") -> str:
        try:
            con = in_tx() or open_conn(库)
            close_after = in_tx() is None
            try:
                if not 表名:
                    cur = con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%' ORDER BY name")
                    return "、".join(r[0] for r in cur.fetchall()) or "(没有表)"
                # 表名不能参数化（占位符只能用在值的位置），所以自己校验：
                # 只允许字母数字下划线和汉字，挡住注入
                if not re.fullmatch(r"[\w\u4e00-\u9fff]+", 表名):
                    return f"[表名不合法] {表名}"
                cols = con.execute(f"PRAGMA table_info({表名})").fetchall()
                if not cols:
                    return f"[没有这张表] {表名}"
                return "\n".join(
                    f"{c['name']}　{c['type'] or '?'}"
                    + ("　主键" if c["pk"] else "")
                    + ("　非空" if c["notnull"] else "")
                    for c in cols)
            finally:
                if close_after:
                    con.close()
        except (ValueError, sqlite3.Error) as e:
            return f"[出错] {e}"
