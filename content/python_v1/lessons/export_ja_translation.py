#!/usr/bin/env python3
"""Export lossless K182 TSV from bilingual lesson sources; fail on missing translations."""
import json
from pathlib import Path
from render_lessons import import_rows

HERE = Path(__file__).resolve().parent
ja = json.loads((HERE / 'lessons.ja.json').read_text(encoding='utf-8'))
zh = json.loads((HERE / 'lessons.zh.json').read_text(encoding='utf-8'))
assert ja['language'] == 'ja' and ja['series_code'] == zh['series_code'] == 'python.core_v1'
zrows, jrows = import_rows(zh), import_rows(ja)
assert len(zrows) == len(jrows) == 13
assert len({x['code'] for x in jrows}) == 13
out = ['# text-encoding: json-string', 'tbl\trow_key\tfield\ttext']
def add(tbl, key, field, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'missing translation: {tbl}/{key}/{field}')
    out.append('\t'.join((tbl, key, field, json.dumps(value, ensure_ascii=False)[1:-1])))
for z, j in zip(zrows, jrows):
    if z['code'] != j['code']:
        raise ValueError(f'lesson code mismatch: {z["code"]} {j["code"]}')
    for field in ('title', 'summary', 'explain', 'orig_title'):
        if j[field] == z[field]:
            raise ValueError(f'untranslated: {j["code"]}/{field}')
        add('lesson_text', j['code'], field, j[field])
add('lesson_series', ja['series_code'], 'name', ja['series_name'])
# Source has no intro; this short description is authored for the new series.
add('lesson_series', ja['series_code'], 'intro', 'Python の基礎を全13課で学びます。')
p = HERE.parent / 'ja' / 'lesson.tsv'
p.write_text('\n'.join(out) + '\n', encoding='utf-8')
print(f'{p}: lesson_text=52 lesson_series=2')
