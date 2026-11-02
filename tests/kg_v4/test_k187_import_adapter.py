"""Adapter forwards optional metadata only to an upgraded service."""
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('import_lesson_rows', root / 'kg_v4/setup/import_lesson_rows.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
seen = []
class Endpoint:
    def __init__(self, method, path, lines, **kwargs):
        self.lines = lines
class Router:
    def run(self, ep, form, user):
        seen.append((ep.lines[0], form))
        return {'total': 1, 'imported': 1, 'file_rows': 1, 'item_links': 0, 'point_links': 0, 'rejected': []}, 200, None
project = types.ModuleType('gen.project')
project.make_app = lambda *args, **kwargs: (None, Router())
http = types.ModuleType('tools.dsl_http')
http.Endpoint = Endpoint
sys.modules['gen.project'] = project
sys.modules['tools.dsl_http'] = http
with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    (p / 'services').mkdir(); (p / 'routes').mkdir(); (p / 'app.db').touch()
    rows = p / 'rows.json'; rows.write_text(json.dumps([{'code': 'python.l1'}]))
    svc = p / 'services/lesson.zs'
    svc.write_text('  公开 函数 写入系列课文并重灌 series_code rows_json intro? intro_given? sort_order?\n')
    base = [str(p), str(rows), '--subject', '2', '--series-code', 'python.core_v1']
    assert mod.main(base) == 0
    assert 'intro=' not in seen[-1][0] and 'sort_order=' not in seen[-1][0]
    assert 'intro' not in seen[-1][1] and 'sort_order' not in seen[-1][1]
    assert 'intro_given' not in seen[-1][0] and 'intro_given' not in seen[-1][1]
    assert mod.main(base + ['--intro', '', '--sort-order', '0']) == 0
    assert 'intro={intro}' in seen[-1][0] and 'sort_order={sort_order}' in seen[-1][0]
    assert seen[-1][1]['intro'] == '' and seen[-1][1]['sort_order'] == '0'
    assert 'intro_given={intro_given}' in seen[-1][0] and seen[-1][1]['intro_given'] == '1'
    assert mod.main(base + ['--sort-order', '0']) == 0
    assert 'intro_given' not in seen[-1][0] and 'intro_given' not in seen[-1][1]
    n = len(seen)
    svc.write_text('  公开 函数 写入系列课文并重灌 series_code rows_json intro? sort_order?\n')
    assert mod.main(base + ['--intro', 'hello']) == 2 and len(seen) == n
    svc.write_text('  公开 函数 写入系列课文并重灌 series_code rows_json\n')
    assert mod.main(base + ['--intro', 'hello']) == 2 and len(seen) == n
    assert (p / 'app.db').stat().st_size == 0
print('adapter: absent, explicit empty/zero and old service guard passed')
