#!/usr/bin/env python3
"""Validate all source/derived content and execute every bilingual code block.
Use: python3 -I check_lessons.py [--write-evidence]
Only --write-evidence writes verification.json, never changes expected outputs.
"""
import argparse
import ast
import csv
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent

def read_csv(path, delimiter=','):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter=delimiter))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def blocks(lesson):
    for example in lesson['examples']:
        yield example['id'], 'example', example
    for exercise in lesson['exercises']:
        yield exercise['id'], 'exercise', exercise['answer']

def ensure(ok, message):
    if not ok:
        raise ValueError(message)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-evidence', action='store_true')
    args = parser.parse_args()
    points = read_csv(SOURCE / 'points.csv')
    items = read_csv(SOURCE / 'items.csv')
    edges = read_csv(SOURCE / 'edges.csv')
    known = {x['code'] for x in points}
    item_point = {x['code']: x['point_code'] for x in items}
    ensure(len(known) == 34 and len(edges) == 49, 'unexpected source point/edge counts')
    docs = {lang: json.loads((HERE / f'lessons.{lang}.json').read_text(encoding='utf-8')) for lang in ('zh', 'ja')}
    ensure(docs['zh']['language'] == 'zh' and docs['ja']['language'] == 'ja', 'wrong language metadata')
    source_ja = {r['row_key']: r['text'] for r in read_csv(SOURCE / 'ja/kg_point.tsv', '\t')}
    source_zh = {r['code']: r['title'] for r in points}
    for lang, doc in docs.items():
        ensure(doc['subject_code'] == 'python' and doc['subject_id'] == 2, f'{lang}: wrong subject')
        ensure(doc['series_code'] == 'python.core_v1', f'{lang}: wrong series')
        ls = doc['lessons']
        ensure(10 <= len(ls) <= 15, 'lesson count outside 10..15')
        ensure(len({x['code'] for x in ls}) == len(ls), 'duplicate lesson code')
        ensure([x['seq'] for x in ls] == list(range(1, len(ls)+1)), 'noncontiguous seq')
        order, linked_items = {}, []
        level_rank = {'入门':0, '基础':1, '进阶':2}
        ensure([level_rank[x['level']] for x in ls] == sorted(level_rank[x['level']] for x in ls), 'level order')
        block_ids = set()
        for lesson in ls:
            code = lesson['code']
            ensure(code == f"python.lesson{lesson['seq']:02}", 'unstable lesson code')
            ensure(len(lesson['objectives']) >= 2 and len(lesson['explanation']) >= 2, f'{code}: missing pedagogy')
            ensure(2 <= len(lesson['examples']) <= 4, f'{code}: example count')
            ensure(2 <= len(lesson['exercises']) <= 3, f'{code}: exercise count')
            ensure(1 <= len(lesson['common_errors']) <= 2, f'{code}: error count')
            ensure(lesson['title'] and lesson['point_codes'], f'{code}: empty content')
            titles = source_ja if lang == 'ja' else source_zh
            ensure(lesson['point_titles'] == [titles[p] for p in lesson['point_codes']], f'{code}: terminology drift')
            for j, point in enumerate(lesson['point_codes']):
                ensure(point in known and point not in order, f'{code}: unknown or repeated point {point}')
                order[point] = (lesson['seq'], j)
            ensure(set(lesson['item_codes']) == {k for k,v in item_point.items() if v in lesson['point_codes']}, f'{code}: incomplete item links')
            linked_items.extend(lesson['item_codes'])
            for block_id, kind, block in blocks(lesson):
                ensure(block_id not in block_ids, f'duplicate block: {block_id}')
                block_ids.add(block_id)
                ensure(all(isinstance(block[k], str) for k in ('code','stdin','stdout')), f'{block_id}: malformed executable')
                ast.parse(block['code'])
            for q in lesson['exercises']:
                ensure(q['prompt'] and q['answer']['explanation'], f'{code}: missing answer explanation')
        ensure(set(order) == known, f'{lang}: incomplete coverage')
        ensure(set(linked_items) == set(item_point) and len(linked_items) == len(item_point), 'item coverage')
        for edge in edges:
            ensure(order[edge['pre_code']] < order[edge['point_code']], f'prerequisite violation: {edge}')
    zh, ja = docs['zh']['lessons'], docs['ja']['lessons']
    ensure(len(zh) == len(ja), 'translation lesson count mismatch')
    for a,b in zip(zh,ja):
        for key in ('code','seq','level','point_codes','item_codes'):
            ensure(a[key] == b[key], f"translation mismatch: {a['code']} {key}")
        for key in ('objectives','explanation','common_errors','examples','exercises'):
            ensure(len(a[key]) == len(b[key]), f'translation shape: {key}')
        ensure(a['title'] != b['title'], 'untranslated lesson title')
        for key in ('objectives','explanation','common_errors'):
            ensure(all(x != y for x,y in zip(a[key],b[key])), f'untranslated {key}')
        for x,y in zip(a['examples'],b['examples']):
            ensure(x['title'] != y['title'], f"untranslated example {x['id']}")
        for x,y in zip(a['exercises'],b['exercises']):
            ensure(x['prompt'] != y['prompt'] and x['answer']['explanation'] != y['answer']['explanation'], f"untranslated exercise {x['id']}")
        ensure([(i,k) for i,k,_ in blocks(a)] == [(i,k) for i,k,_ in blocks(b)], 'translation block identity')
        for (_,_,x),(_,_,y) in zip(blocks(a),blocks(b)):
            for key in ('code','stdin','stdout'):
                ensure(x[key].encode('utf-8') == y[key].encode('utf-8'), f'translation changed executable {key}')
    # Derived Markdown and importer rows must be reproducible from the canonical documents.
    from_content = {}
    # -I excludes this directory from sys.path, so execute this local, reviewed renderer explicitly.
    namespace = {'__file__': str(HERE / 'render_lessons.py'), '__name__': 'lesson_renderer'}
    exec(compile((HERE / 'render_lessons.py').read_text(encoding='utf-8'), str(HERE / 'render_lessons.py'), 'exec'), namespace)
    for lang, doc in docs.items():
        ensure((HERE/f'lessons.{lang}.md').read_text(encoding='utf-8') == namespace['markdown'](doc), f'{lang}: stale Markdown')
        expected_rows = namespace['import_rows'](doc)
        rows = [json.loads(line) for line in (HERE / f'lesson_import.{lang}.jsonl').read_text(encoding='utf-8').splitlines()]
        ensure(rows == expected_rows, f'{lang}: stale importer rows')
        array = json.loads((HERE / f'lesson_rows.{lang}.json').read_text(encoding='utf-8'))
        ensure(array == rows, f'{lang}: rows_json mismatch')
    # Every run uses a fresh temporary working directory, isolated interpreter, raw byte comparison.
    # Expected outputs were hand-authored above; never populate expectations from observed output.
    executions = []
    failures = []
    for lang, doc in docs.items():
        for lesson in doc['lessons']:
            for block_id, kind, block in blocks(lesson):
                with tempfile.TemporaryDirectory(prefix='k185_') as work:
                    script = Path(work)/'snippet.py'
                    script.write_text(block['code'], encoding='utf-8')
                    try:
                        result = subprocess.run([sys.executable, '-I', str(script)], input=block['stdin'].encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work, timeout=5)
                        passed = result.returncode == 0 and result.stdout == block['stdout'].encode('utf-8') and result.stderr == b''
                        record = dict(language=lang, id=block_id, kind=kind, command='python3 -I <temp>/snippet.py', code_sha256=hashlib.sha256(block['code'].encode()).hexdigest(), stdin=block['stdin'], expected_stdout=block['stdout'], actual_stdout=result.stdout.decode('utf-8',errors='replace'), stderr=result.stderr.decode('utf-8',errors='replace'), returncode=result.returncode, passed=passed)
                    except subprocess.TimeoutExpired:
                        passed = False
                        record = dict(language=lang,id=block_id,kind=kind,passed=False,error='5-second timeout')
                    executions.append(record)
                    if not passed:
                        failures.append(record)
    summary = dict(status='passed' if not failures else 'failed',lessons=len(zh),point_coverage=f'{len(known)}/34',item_links=len(item_point),prerequisite_edges=len(edges),examples=sum(len(x['examples']) for x in zh),exercises=sum(len(x['exercises']) for x in zh),unique_executables=sum(1 for x in zh for _ in blocks(x)),executions=len(executions),passed=sum(x['passed'] for x in executions),languages=['zh','ja'],byte_exact=True,stderr_empty=not failures,python=platform.python_version(),executable=sys.executable,checks=['lesson counts','34/34 unique point coverage','110/110 item links','49 strict prerequisite orders including within each lesson','source point terminology','bilingual text shape','bilingual identical code/stdin/stdout bytes','derived Markdown/JSONL/rows_json freshness','independent isolated execution of both languages'])
    if args.write_evidence:
        evidence=dict(summary=summary,inputs={str(p.relative_to(SOURCE)):digest(p) for p in [SOURCE/'points.csv',SOURCE/'edges.csv',SOURCE/'items.csv',SOURCE/'ja/kg_point.tsv']},artifacts={p.name:digest(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name not in ('verification.json','README.md')},executions=executions)
        (HERE/'verification.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
    if failures:
        print(json.dumps(failures,ensure_ascii=False,indent=2))
        return 1
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, SyntaxError, OSError) as err:
        print(f'VALIDATION FAILED: {err}', file=sys.stderr)
        raise SystemExit(1)
