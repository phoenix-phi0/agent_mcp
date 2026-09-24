-- 由 DSL 生成，请勿手改。改 .entity 后重新生成。
-- 第一版不做迁移：字段变更后请删库重建。

-- 外键默认是关的，而且是**每个连接**都要开一次——建库时开了不代表
-- 后面查询时也开着。应用侧连接后要自己 PRAGMA foreign_keys = ON，
-- 不然外键约束只是摆设。
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS rating;
DROP TABLE IF EXISTS post;
DROP TABLE IF EXISTS author;

-- 作者
CREATE TABLE author (
    code VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    level VARCHAR(32) CHECK (level IN ('新手', '熟练', '资深')) NOT NULL DEFAULT '新手',
    joined VARCHAR(255) NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (code)
);

-- 文章
CREATE TABLE post (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author VARCHAR(255) NOT NULL REFERENCES author(code) ON DELETE RESTRICT,
    title VARCHAR(255) NOT NULL UNIQUE,
    body TEXT,
    views INTEGER NOT NULL DEFAULT 0,
    published INTEGER NOT NULL DEFAULT 0,
    created VARCHAR(255) NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_post_author
    ON post(author);
-- 评分
CREATE TABLE rating (
    author VARCHAR(255) NOT NULL REFERENCES author(code) ON DELETE RESTRICT,
    post INTEGER NOT NULL,
    score INTEGER NOT NULL DEFAULT 3,
    at VARCHAR(255) NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (author, post)
);

