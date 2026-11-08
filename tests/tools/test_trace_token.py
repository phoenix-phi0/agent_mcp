import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""trace_server 的令牌模式（经隧道公开到外网时用）：只认 /<令牌>/ 下的地址；页面带 trace-live
标记（外网主机名不是 localhost 也进实时模式）；不外带来源地址；不暴露服务器上的绝对路径。"""
import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from tools import trace_server

TOKEN = "abcDEF0123456789_-xyz"


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def get(url):
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url, timeout=5) as r:
            return r.status, dict(r.headers), r.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode('utf-8')


def run():
    with tempfile.TemporaryDirectory() as d:
        runs = Path(d) / 'runs'
        runs.mkdir()
        (runs / 'r1.json').write_text(json.dumps({'status': 'done', 'events': [], 'script': ''}), encoding='utf-8')
        srv = ThreadingHTTPServer(('127.0.0.1', 0), trace_server.make_handler(runs, TOKEN))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{srv.server_address[1]}'
        try:
            for path in ('/', '/index.html', '/api/runs', '/api/run?name=r1.json', '/wrongtoken123456789/api/runs'):
                check(get(base + path)[0] == 404, f'没有令牌：{path} → 404')
            code, h, _ = get(base + '/' + TOKEN)
            check(code == 301 and h.get('Location') == '/' + TOKEN + '/', '/<令牌> 跳到 /<令牌>/（页面里的相对地址才对）')
            code, h, body = get(base + '/' + TOKEN + '/')
            check(code == 200 and '<meta name="trace-live" content="1">' in body, '页面带 trace-live 标记')
            check(h.get('Referrer-Policy') == 'no-referrer', '不外带来源地址（地址里有令牌）')
            code, _, body = get(base + '/' + TOKEN + '/api/runs')
            data = json.loads(body)
            check(code == 200 and [r['name'] for r in data['runs']] == ['r1.json'], '/<令牌>/api/runs 能用')
            check(data['dir'] == 'runs' and d not in body, '不暴露服务器上的绝对路径')
            code, _, body = get(base + '/' + TOKEN + '/api/run?name=r1.json')
            check(code == 200 and json.loads(body)['status'] == 'done', '/<令牌>/api/run 能用')
        finally:
            srv.shutdown()
            srv.server_close()

        # 挂在 relay 的子路径下：/trace/<令牌>/…
        srv = ThreadingHTTPServer(('127.0.0.1', 0), trace_server.make_handler(runs, TOKEN, '/trace'))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{srv.server_address[1]}'
        try:
            check(get(base + '/' + TOKEN + '/')[0] == 404 and get(base + '/trace/')[0] == 404,
                  '子路径模式：少了 /trace 或少了令牌都 404')
            code, h, _ = get(base + '/trace/' + TOKEN)
            check(code == 301 and h.get('Location') == '/trace/' + TOKEN + '/', '/trace/<令牌> 跳到带斜杠的地址')
            check(get(base + '/trace/' + TOKEN + '/')[0] == 200
                  and get(base + '/trace/' + TOKEN + '/api/runs')[0] == 200, '/trace/<令牌>/ 页面和接口都能用')
        finally:
            srv.shutdown()
            srv.server_close()

        # 不给令牌：和以前一样（本机用）
        srv = ThreadingHTTPServer(('127.0.0.1', 0), trace_server.make_handler(runs))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{srv.server_address[1]}'
        try:
            check(get(base + '/')[0] == 200 and get(base + '/api/runs')[0] == 200, '不给令牌：本机照旧能用')
        finally:
            srv.shutdown()
            srv.server_close()
    print('trace token passed')


if __name__ == '__main__':
    run()
