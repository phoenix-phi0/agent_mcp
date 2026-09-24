-- 日语学习的记录库。
--
-- 建库：py -m tools.initdb
-- 重建：py -m tools.initdb --force   （会删掉已有数据）
--
-- 设计取向：这里只存**作答流水**和由它汇总出来的东西。题目本身留在
-- jsonl 题库里，不进库——题库是人维护的文本，进了库就得写迁移脚本才能
-- 改一道题的解析，那跟「改内容不碰代码」的初衷相反。
--
-- 所以 题号 是外键但没有 REFERENCES：它指向 jsonl 里的 id，库里没有
-- 对应的表。这是有意的，不是漏写。

-- 每次作答一行。不删不改，只追加。
-- 汇总数据（对了几道、正确率）都从这张表算，不单独维护计数器——
-- 计数器和流水对不上时，没人知道该信哪个。
CREATE TABLE IF NOT EXISTS 作答 (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  学习者    TEXT    NOT NULL,
  题号      TEXT    NOT NULL,          -- 指向 jsonl 题库里的 id
  课程      TEXT    NOT NULL,
  考点      TEXT,
  作答      TEXT,                      -- 学习者实际写了什么，排查判题用
  对错      INTEGER NOT NULL,          -- 1 对 0 错
  用时秒    INTEGER,
  时间      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 查某人的记录是最高频的操作
CREATE INDEX IF NOT EXISTS idx_作答_人 ON 作答(学习者, 时间 DESC);
CREATE INDEX IF NOT EXISTS idx_作答_题 ON 作答(学习者, 题号);


-- 错题本。从作答流水里汇总出来，答对了就减一次、归零后删掉。
--
-- 单独一张表而不是每次从流水里算：复习要的是「现在还欠着哪些」，
-- 那是个会变的状态，不是历史。用流水算的话，「答错三次后来又答对两次」
-- 到底算不算错题，得在每条查询里重新定义一遍规则。
CREATE TABLE IF NOT EXISTS 错题 (
  学习者    TEXT    NOT NULL,
  题号      TEXT    NOT NULL,
  课程      TEXT    NOT NULL,
  考点      TEXT,
  错次      INTEGER NOT NULL DEFAULT 1,
  最后错于  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
  PRIMARY KEY (学习者, 题号)
);

CREATE INDEX IF NOT EXISTS idx_错题_人 ON 错题(学习者, 最后错于 DESC);


-- 知识图谱节点的掌握状态。跟 kg_store.py 的 mastery 表是同一件事，
-- 将来两边应该合并——现在分开是因为那个用的是自己的 kg.db。
CREATE TABLE IF NOT EXISTS 掌握 (
  学习者    TEXT    NOT NULL,
  节点      TEXT    NOT NULL,          -- 知识图谱的节点 id
  对数      INTEGER NOT NULL DEFAULT 0,
  总数      INTEGER NOT NULL DEFAULT 0,
  已掌握    INTEGER NOT NULL DEFAULT 0,
  更新      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
  PRIMARY KEY (学习者, 节点)
);


-- 学习者。只存稳定的东西，进度不放这儿——那是会变的状态。
CREATE TABLE IF NOT EXISTS 学习者 (
  id        TEXT PRIMARY KEY,
  称呼      TEXT,
  级别      TEXT,                      -- N5 到 N1
  开始于    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  备注      TEXT
);
