"""cmd 的 count_lines：统计目录（或单个文件）下按文件名通配选中的文件数、行数和大小。

用法：count_lines.py PATH NAME TOP
  跳过 .git、.venv、__pycache__、node_modules 目录和符号链接；前 8KB 里有 NUL 的算二进制文件，只计大小不计行数。
"""
import fnmatch
import os
import sys

SKIP = {'.git', '.venv', '__pycache__', 'node_modules'}


def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f}{unit}' if unit == 'B' else f'{n:.1f}{unit}'
        n /= 1024


def main(argv):
    root, pattern, top = argv[1], argv[2], int(argv[3])
    if os.path.isfile(root):
        base, files = os.path.dirname(root), [root]
    elif os.path.isdir(root):
        base, files = root, []
        for directory, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP and not os.path.islink(os.path.join(directory, d)))
            files += [os.path.join(directory, n) for n in sorted(names)
                      if fnmatch.fnmatch(n, pattern) and not os.path.islink(os.path.join(directory, n))]
    else:
        print(f'找不到：{root}')
        return 2
    lines = size = binary = 0
    per_file, per_dir = [], {}
    for path in files:
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except OSError:
            continue
        size += len(data)
        rel = os.path.relpath(path, base)
        first = rel.split(os.sep)[0] if os.sep in rel else '.'
        bucket = per_dir.setdefault(first, [0, 0, 0])
        bucket[0] += 1
        bucket[2] += len(data)
        if b'\0' in data[:8192]:
            binary += 1
            continue
        n = data.count(b'\n') + (1 if data and not data.endswith(b'\n') else 0)
        lines += n
        bucket[1] += n
        per_file.append((n, rel))
    print(f'文件 {len(files)} 个' + (f'（其中二进制 {binary} 个，不计行数）' if binary else '')
          + f'  行数 {lines}  大小 {human(size)}')
    if len(per_dir) > 1:
        print('按第一层目录：')
        for name, (count, n, nbytes) in sorted(per_dir.items(), key=lambda kv: -kv[1][1]):
            print(f'  {name}\t文件 {count}\t行数 {n}\t大小 {human(nbytes)}')
    if per_file:
        print(f'行数最多的 {min(top, len(per_file))} 个文件：')
        for n, rel in sorted(per_file, key=lambda x: (-x[0], x[1]))[:top]:
            print(f'  {n}\t{rel}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
