#!/usr/bin/env python3
"""Validate the bilingual bank and execute each trusted output example offline."""
import collections
import csv
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent

def check():
    data = json.loads((HERE / 'questions.json').read_text(encoding='utf-8'))
    assert data['schema'] == 'python-dictation-v1'
    questions = data['questions']
    with (HERE.parent / 'points.csv').open(encoding='utf-8', newline='') as f:
        points = {r['code'] for r in csv.DictReader(f)}
    assert len(points) == 34
    ids, counts, kinds = set(), collections.Counter(), collections.Counter()
    for q in questions:
        ident = q['id']
        assert re.fullmatch(r'python\.dict\.\d{3}', ident) and ident not in ids, ident
        ids.add(ident)
        assert q['point_code'] in points, ident
        counts[q['point_code']] += 1
        kind = q['type']
        assert kind in ('term', 'output'), ident
        kinds[kind] += 1
        for field in ('prompt_zh', 'prompt_ja', 'explain_zh', 'explain_ja'):
            assert isinstance(q[field], str) and q[field].strip(), (ident, field)
        assert q['difficulty'] in ('入门', '基础', '进阶'), ident
        assert isinstance(q['answer'], str) and q['answer'] in q['accepted'], ident
        assert len(set(q['accepted'])) == len(q['accepted']) and all(isinstance(x, str) and x for x in q['accepted']), ident
        if kind == 'output':
            code = q['code']
            fence = '```python\n' + code + '\n```'
            assert q['prompt_zh'].count(fence) == q['prompt_ja'].count(fence) == 1, ident
            proc = subprocess.run(['python3', '-I', '-c', code], input=b'', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3, cwd='/tmp')
            assert proc.returncode == 0 and not proc.stderr, (ident, proc.returncode, proc.stderr)
            assert proc.stdout == q['answer'].encode('utf-8'), (ident, proc.stdout, q['answer'])
        else:
            assert 'code' not in q and q['answer'].strip(), ident
    assert set(counts) == points and all(3 <= n <= 5 for n in counts.values()), counts
    assert 120 <= len(questions) <= 160 and all(kinds[k] for k in ('term','output'))
    print(f"PASS: {len(counts)}/34 points; {len(questions)} questions; term={kinds['term']}, output={kinds['output']}; executed={kinds['output']}/{kinds['output']} byte-exact")

if __name__ == '__main__':
    try:
        check()
    except (AssertionError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        sys.exit(1)
