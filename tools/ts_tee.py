"""给子进程的标准输出逐行打时间戳，另存一份；标准输出原样转发，标准输入、标准错误直接继承。

    python ts_tee.py <日志文件> -- <命令> [参数…]

日志每行「开始后的秒数<TAB>原始一行」。给 codex exec --json 用：哪一步慢，看日志里两行之间的间隔。
退出码跟子进程一致。上层按进程组杀（SubmitChannel.run 用 start_new_session），子进程一起结束。
"""
import subprocess
import sys
import time


def main(argv):
    if len(argv) < 3 or argv[1] != "--":
        sys.stderr.write("用法：ts_tee.py <日志文件> -- <命令> [参数…]\n")
        return 2
    log, cmd = argv[0], argv[2:]
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as f:
        f.write(f"0.0\t# {time.strftime('%Y-%m-%dT%H:%M:%S%z')} 开始\n")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        for line in p.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            f.write(f"{time.time() - t0:.1f}\t{line}")
            f.flush()
        rc = p.wait()
        f.write(f"{time.time() - t0:.1f}\t# 结束，退出码 {rc}\n")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
