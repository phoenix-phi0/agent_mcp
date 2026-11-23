import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""trace_server 带口令（经隧道公开到外网时用）：登录页 + 签名 cookie，地址里不再带口令。

1. 没登录：页面跳登录页（next 带回来）；接口回 401；口令不对的老地址也一样。
2. 登录：GET 是表单；口令不对 401、不发 cookie；别的网页发来的登录 403；
   对了 303 回 next、发 cookie（HttpOnly、SameSite=Lax、Path=base，值不是口令本身）。next 只认本服务的路径。
3. 带 cookie：页面、接口、会议页都能用；页面里加了「401 跳登录页」的脚本，还有 trace-live 标记。
   伪造的、过期的、换了口令以后的 cookie 都不认。
4. 写接口：带 cookie 能过鉴权；没 cookie 401；别的网页发来的照样 403。
5. 老地址 /<口令>/… 照旧能用：页面顺手发 cookie，脚本确认 cookie 能用后把地址栏换成不带口令的。
6. 退出：清 cookie、回登录页。X-Forwarded-Proto: https 时 cookie 带 Secure。
7. 挂在子路径（/trace）下同样；不给口令时和以前一样（本机用）。
不外带来源地址；不暴露服务器上的绝对路径。
"""
import json
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from tools import trace_server

TOKEN = 'logintesttoken0123456789'


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def req(url, method='GET', body=None, headers=None):
    opener = urllib.request.build_opener(NoRedirect)
    r = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with opener.open(r, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode('utf-8')


def cookie_of(h):
    sc = h.get('Set-Cookie') or ''
    return sc.split(';', 1)[0], sc


def serve(runs, token=None, base='', write=False):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), trace_server.make_handler(runs, token, base, write))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}'


def login(url, key, nxt='', origin=None, headers=None):
    h = {'Content-Type': 'application/x-www-form-urlencoded'}
    if origin:
        h['Origin'] = origin
    h.update(headers or {})
    return req(url, 'POST', urllib.parse.urlencode({'key': key, 'next': nxt}).encode(), h)


def run():
    with tempfile.TemporaryDirectory() as d:
        runs = Path(d) / 'runs'
        runs.mkdir()
        (runs / 'r1.json').write_text(json.dumps({'status': 'done', 'events': [], 'script': ''}), encoding='utf-8')

        srv, base = serve(runs, TOKEN, write=True)
        host = base[len('http://'):]
        try:
            print('没登录')
            code, h, _ = req(base + '/?x=1')
            check(code == 302 and h['Location'] == '/login?' + urllib.parse.urlencode({'next': '/?x=1'}),
                  '页面跳登录页，next 带上原地址')
            for path in ('/api/runs', '/api/run?name=r1.json'):
                code, _, body = req(base + path)
                check(code == 401 and json.loads(body)['login'] == '/login', f'接口 {path} → 401（带登录页地址）')
            code, h, _ = req(base + '/wrongtoken123456789/api/runs')
            check(code == 302 and h['Location'].startswith('/login?'), '口令不对的老地址：当成没登录，跳登录页')
            code, h, _ = req(base + '/meeting/')
            check(code == 302 and 'next=%2Fmeeting%2F' in h['Location'], '会议页也跳登录页')

            print('登录')
            code, h, body = req(base + '/login?next=/meeting/%22%3E')
            check(code == 200 and 'name="key"' in body and 'type="password"' in body and '"><' not in body.split('name="next"')[1][:40],
                  '登录页是表单（next 转义过）')
            code, h, body = login(base + '/login', 'wrong-key-0123456789')
            check(code == 401 and '口令不对' in body and 'Set-Cookie' not in h, '口令不对：401，不发 cookie')
            code, _, _ = login(base + '/login', TOKEN, origin='https://evil.example')
            check(code == 403, '别的网页发来的登录：403')
            code, _, _ = req(base + '/login', 'POST', b'key=' + TOKEN.encode(), {'Content-Type': 'application/json'})
            check(code == 415, '登录不是表单编码：415')
            code, h, _ = login(base + '/login', TOKEN, '/meeting/#/room/r1.json', origin=base)
            ck, raw = cookie_of(h)
            check(code == 303 and h['Location'] == '/meeting/#/room/r1.json', '对了：303 回到原来要去的页面')
            check(ck.startswith('trace_session=') and TOKEN not in raw and 'HttpOnly' in raw and 'SameSite=Lax' in raw
                  and 'Path=/' in raw and 'Secure' not in raw, 'cookie：HttpOnly、SameSite=Lax，值不是口令本身')
            for bad in ('https://evil.example/', '//evil.example/x', '/\\evil', '/a/../../x'):
                _, h2, _ = login(base + '/login', TOKEN, bad)
                check(h2['Location'] == '/', f'next={bad!r}：不跳外站，回首页')
            code, h2, _ = req(base + '/login?next=/api/runs', headers={'Cookie': ck})
            check(code == 303 and h2['Location'] == '/api/runs', '已登录再开登录页：直接回 next')

            print('带 cookie')
            code, h, body = req(base + '/', headers={'Cookie': ck})
            check(code == 200 and '<meta name="trace-live" content="1">' in body and "r.status===401" in body
                  and 'replaceState' not in body, '查看器能开：带 trace-live 标记和「401 跳登录页」的脚本')
            check(h.get('Referrer-Policy') == 'no-referrer', '不外带来源地址')
            code, _, body = req(base + '/api/runs', headers={'Cookie': 'a=b; ' + ck + '; c=d'})
            data = json.loads(body)
            check(code == 200 and [r['name'] for r in data['runs']] == ['r1.json'] and data['dir'] == 'runs' and d not in body,
                  '接口能用（cookie 夹在别的 cookie 中间也认），不暴露绝对路径')
            code, _, body = req(base + '/meeting/', headers={'Cookie': ck})
            check(code == 200 and 'trace-live' in body and 'r.status===401' in body, '会议页能开')
            exp, sig = ck.split('=', 1)[1].split('.')
            for bad, why in ((f'trace_session={int(exp) + 999}.{sig}', '改了过期时间'),
                             ('trace_session=' + trace_server.make_session(TOKEN, now=time.time() - 30 * 86400), '过期的'),
                             ('trace_session=' + trace_server.make_session('another-token-0123456789'), '别的口令签的（换了口令）'),
                             ('trace_session=' + TOKEN, '口令本身'), ('trace_session=', '空的')):
                check(req(base + '/api/runs', headers={'Cookie': bad})[0] == 401, f'{why} cookie：不认')

            print('写接口')
            wh = {'Content-Type': 'application/json', 'Origin': base}
            code, _, body = req(base + '/api/abort', 'POST', json.dumps({'name': 'nope.json'}).encode(), dict(wh, Cookie=ck))
            check(code == 404 and '没有 nope.json' in json.loads(body)['error'], '带 cookie：过了鉴权（到了找运行这一步）')
            code, _, _ = req(base + '/api/abort', 'POST', b'{}', wh)
            check(code == 401, '没 cookie：401')
            code, _, _ = req(base + '/api/abort', 'POST', b'{}', dict(wh, Cookie=ck, Origin='https://evil.example'))
            check(code == 403, '带 cookie 但是别的网页发来的：403')

            print('老地址')
            code, h, _ = req(base + '/' + TOKEN)
            check(code == 301 and h['Location'] == '/' + TOKEN + '/', '/<口令> 跳到 /<口令>/')
            code, h, body = req(base + '/' + TOKEN + '/')
            ck2, _ = cookie_of(h)
            check(code == 200 and ck2.startswith('trace_session=') and 'replaceState' in body and '"/api/runs"' in body,
                  '老地址的页面：能开，顺手发 cookie，脚本确认能用后把地址栏换成不带口令的')
            check(req(base + '/api/runs', headers={'Cookie': ck2})[0] == 200, '老地址发的 cookie 能用')
            code, h, body = req(base + '/' + TOKEN + '/meeting/')
            check(code == 200 and 'Set-Cookie' in h and '"/meeting/"' in body, '老地址的会议页：同样')
            check(req(base + '/' + TOKEN + '/api/runs')[0] == 200, '老地址的接口照旧能用（过渡）')

            print('退出')
            code, h, _ = req(base + '/logout', headers={'Cookie': ck})
            check(code == 303 and h['Location'] == '/login' and 'Max-Age=0' in h['Set-Cookie'], '退出：清 cookie，回登录页')
            _, h, _ = login(base + '/login', TOKEN, headers={'X-Forwarded-Proto': 'https'})
            check('Secure' in h['Set-Cookie'], '经 https 代理（X-Forwarded-Proto: https）：cookie 带 Secure')
            check(host in base, '（本机测试）')
        finally:
            srv.shutdown()
            srv.server_close()

        print('子路径 /trace')
        srv, base = serve(runs, TOKEN, '/trace')
        try:
            check(req(base + '/' + TOKEN + '/')[0] == 404, '少了 /trace：404')
            code, h, _ = req(base + '/trace/')
            check(code == 302 and h['Location'].startswith('/trace/login?next=%2Ftrace%2F'), '没登录：跳 /trace/login')
            code, h, _ = login(base + '/trace/login', TOKEN, '/trace/')
            ck, raw = cookie_of(h)
            check(code == 303 and h['Location'] == '/trace/' and 'Path=/trace' in raw, '登录：cookie 只给 /trace')
            check(req(base + '/trace/', headers={'Cookie': ck})[0] == 200
                  and req(base + '/trace/api/runs', headers={'Cookie': ck})[0] == 200, '页面和接口都能用')
            _, h, _ = login(base + '/trace/login', TOKEN, '/elsewhere/')
            check(h['Location'] == '/trace/', 'next 不在 /trace 下：回 /trace/')
            code, h, _ = req(base + '/trace/' + TOKEN)
            check(code == 301 and h['Location'] == '/trace/' + TOKEN + '/', '老地址 /trace/<口令> 跳到带斜杠的地址')
            check(req(base + '/trace/' + TOKEN + '/api/runs')[0] == 200, '老地址接口能用')
        finally:
            srv.shutdown()
            srv.server_close()

        print('不给口令')
        srv, base = serve(runs)
        try:
            code, _, body = req(base + '/')
            check(code == 200 and 'r.status===401' not in body and req(base + '/api/runs')[0] == 200,
                  '本机照旧能用，不加登录脚本')
            check(req(base + '/login')[0] == 404, '没有登录页')
        finally:
            srv.shutdown()
            srv.server_close()
    print('trace token passed')


if __name__ == '__main__':
    run()
