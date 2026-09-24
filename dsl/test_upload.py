# -*- coding: utf-8 -*-
"""文件上传的端到端测试。

    cd dsl
    py serve_http.py          先起服务（另一个窗口）
    py test_upload.py         再跑这个

    py test_upload.py --port 8092     服务起在别的端口时

不用 requests——标准库的 urllib 拼 multipart 虽然啰嗦，但省掉一个依赖，
而且拼的过程本身就是在验「前端会发成什么样」。

## 测什么

七项，每项对应 routes/upload.zs 里的一个接口：

  1 能不能收到      —— multipart 有没有被路由器认出来
  2 哈希命名        —— 同内容同名，扩展名保留
  3 同文件传两次    —— 哈希一样，不该产生第二个文件
  4 时间命名        —— 名字里带时间戳和原名
  5 文本字段混传    —— 文件和文本一起发时两边都取得到
  6 字段名写错      —— 该明确报错，不该静默成功
  7 同字段存两次    —— 预计第二次是空的（read 之后指针在末尾）

最后一项是**预期会失败的**——它存在就是为了暴露那个问题。真修好了
再把断言反过来。
"""

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"
UPLOADS = WORK / "uploads"


# ----------------------------------------------------------------------
# 拼 multipart
# ----------------------------------------------------------------------


def multipart(fields: dict, files: dict) -> tuple:
    """手拼 multipart/form-data。返回 (body, content_type)。

    files 是 {字段名: (文件名, 字节)}。

    边界串用 uuid：内容里正好出现边界串的概率要低到可以忽略，否则解析
    会从中间断开——那种错看起来像「文件损坏」，很难想到是边界撞了。
    """
    boundary = "----zs" + uuid.uuid4().hex
    out = []

    for name, value in fields.items():
        out.append(f"--{boundary}\r\n".encode())
        out.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        out.append(str(value).encode("utf-8"))
        out.append(b"\r\n")

    for name, (filename, data) in files.items():
        out.append(f"--{boundary}\r\n".encode())
        out.append((f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n').encode("utf-8"))
        out.append(b"Content-Type: application/octet-stream\r\n\r\n")
        out.append(data)
        out.append(b"\r\n")

    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def post(url: str, fields: dict = None, files: dict = None) -> dict:
    """发一次 multipart 请求，返回解析后的 JSON。"""
    body, ctype = multipart(fields or {}, files or {})
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 接口用「返回 … 400」报错时走这儿，body 仍然是 JSON
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"_http": e.code}
    except urllib.error.URLError as e:
        raise SystemExit(f"连不上 {url}：{e}\n先跑 py serve_http.py")
    except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
        # 请求体超限时 Flask 直接关连接，不等客户端发完——那是对的，
        # 服务器没道理把 33MB 收完再说「太大了」。客户端这边表现成
        # 连接被中断，而不是一个带状态码的响应。
        return {"_aborted": True}


# ----------------------------------------------------------------------
# 断言
# ----------------------------------------------------------------------

通过 = 失败 = 0


def check(名: str, 实际, 期望=None, 判据=None) -> None:
    """判据给函数时用函数判，否则比相等。"""
    global 通过, 失败
    ok = 判据(实际) if 判据 else (实际 == 期望)
    if ok:
        通过 += 1
        print(f"  ✓ {名}")
    else:
        失败 += 1
        print(f"  ✗ {名}")
        print(f"      实际：{实际!r}")
        if 期望 is not None:
            print(f"      期望：{期望!r}")


def 小节(名: str) -> None:
    print(f"\n{名}")


# ----------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description="文件上传测试")
    p.add_argument("--port", type=int, default=8091)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()

    base = f"http://{args.host}:{args.port}"

    # 用一段随机内容，免得跟上次跑剩下的文件撞
    内容 = f"测试内容 {uuid.uuid4()}".encode("utf-8")
    哈希 = hashlib.sha256(内容).hexdigest()[:16]

    print(f"目标 {base}")
    print(f"文件 {len(内容)} 字节，哈希前缀 {哈希}")

    小节("一、multipart 能不能收到")
    r = post(f"{base}/upload/peek", files={"file": ("a.txt", 内容)})
    check("列上传认出了 file 字段", r.get("带了什么", ""),
          判据=lambda s: "file" in s and "a.txt" in s)

    小节("二、哈希命名")
    r = post(f"{base}/upload/hash", files={"file": ("a.txt", 内容)})
    check("返回了路径", r.get("path", ""), f"uploads/{哈希}.txt")
    check("文件真的落盘了", (UPLOADS / f"{哈希}.txt").is_file(), True)
    if (UPLOADS / f"{哈希}.txt").is_file():
        check("内容一致", (UPLOADS / f"{哈希}.txt").read_bytes(), 内容)

    小节("三、同一个文件传两次")
    r2 = post(f"{base}/upload/hash", files={"file": ("别的名字.txt", 内容)})
    check("哈希一样，路径也一样", r2.get("path"), r.get("path"))
    check("没多出第二个文件",
          len(list(UPLOADS.glob(f"{哈希}*"))), 1)

    小节("四、时间命名")
    r = post(f"{base}/upload/time", files={"file": ("报告 v2.txt", 内容)})
    路径 = r.get("path", "")
    check("名字里有原文件名", 路径,
          判据=lambda s: "txt" in s and "_" in s)
    check("空格被洗成下划线", 路径, 判据=lambda s: " " not in s)
    check("落盘了", (WORK / 路径).is_file() if 路径 else False, True)

    小节("五、文本字段跟文件一起发")
    r = post(f"{base}/upload/mixed",
             fields={"form": json.dumps({"learner": "φ-0", "note": "带 空格"},
                                        ensure_ascii=False)},
             files={"file": ("a.txt", 内容)})
    check("文件存了", r.get("path", ""), f"uploads/{哈希}.txt")
    check("包在 form 里的文本字段取得到", r.get("learner"), "φ-0")
    check("含空格的值没被切断", r.get("note"), "带 空格")

    小节("六、字段名写错")
    r = post(f"{base}/upload/wrongname", files={"file": ("a.txt", 内容)})
    check("明确报出没有这个字段", r.get("path", ""),
          判据=lambda s: s.startswith("[") and "不存在的字段" in s)
    check("提示里列出了实际有哪些", r.get("path", ""),
          判据=lambda s: "file" in s)

    小节("七、同一个字段存两次")
    r = post(f"{base}/upload/twice", files={"file": ("a.txt", 内容)})
    print(f"      第一次：{r.get('first')}")
    print(f"      第二次：{r.get('second')}")
    # 动词里读之前 seek(0)。不加的话第二次指针停在末尾，读出来是空的，
    # 而那看起来像「用户传了个空文件」。
    check("第二次也存成功", r.get("second", ""),
          判据=lambda s: s.startswith("uploads/"))
    check("哈希和时间两种命名存的是同一份内容",
          (WORK / r.get("second", "x")).read_bytes()
          if r.get("second", "").startswith("uploads/") else None,
          内容)

    小节("八、超大的请求被挡在脚本之外")
    # 33MB，刚过 MAX_UPLOAD 那条线。Flask 在读请求体时就拒，脚本根本
    # 不会跑起来——所以动词里的检查来不及也没关系。
    #
    # 表现可能是两种：413，或者连接直接被关（服务器不等 33MB 发完）。
    # 两种都算挡住了。
    前 = set(UPLOADS.glob("*")) if UPLOADS.is_dir() else set()
    大 = b"x" * (33 * 1024 * 1024)
    r = post(f"{base}/upload/hash", files={"file": ("big.bin", 大)})
    check("被挡住了（413 或连接中断）", r,
          判据=lambda d: d.get("_http") == 413 or d.get("_aborted"))

    后 = set(UPLOADS.glob("*")) if UPLOADS.is_dir() else set()
    check("没有留下文件", 后 - 前, set())

    print(f"\n{'=' * 50}")
    print(f"通过 {通过}，失败 {失败}")
    return 1 if 失败 else 0


if __name__ == "__main__":
    sys.exit(main())
