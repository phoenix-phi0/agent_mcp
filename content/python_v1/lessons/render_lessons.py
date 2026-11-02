#!/usr/bin/env python3
"""Render reviewable Markdown and exact lesson module rows; no database access."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
LABELS={
'zh':dict(level='等级',points='关联知识点（按学习顺序）',goals='学习目标',explain='讲解',examples='代码示例',input='标准输入',output='预期输出',errors='常见错误',exercises='小练习',answer='参考答案',note='答案说明',none='（空）',lesson='第 {n} 课'),
'ja':dict(level='レベル',points='関連する知識ポイント（学習順）',goals='学習目標',explain='解説',examples='コード例',input='標準入力',output='予想される出力',errors='よくある間違い',exercises='練習',answer='解答例',note='解答の説明',none='（空）',lesson='第 {n} 課')}

def fenced(code,language=''):
    return f'```{language}\n{code}'+('' if code.endswith('\n') else '\n')+'```\n'

def body(d,lang):
    t=LABELS[lang]
    s=f"## {t['goals']}\n\n"+'\n'.join('- '+x for x in d['objectives'])+'\n\n'
    s+=f"## {t['explain']}\n\n"+'\n\n'.join(d['explanation'])+'\n\n'
    s+=f"## {t['examples']}\n\n"
    for i,e in enumerate(d['examples'],1):
        s+=f"### {i}. {e['title']}\n\n"+fenced(e['code'],'python')+'\n'
        s+=f"{t['input']}:\n\n"+(fenced(e['stdin'],'text') if e['stdin'] else t['none']+'\n')+'\n'
        s+=f"{t['output']}:\n\n"+fenced(e['stdout'],'text')+'\n'
    s+=f"## {t['errors']}\n\n"+'\n'.join('- '+x for x in d['common_errors'])+'\n\n'
    s+=f"## {t['exercises']}\n\n"
    for i,q in enumerate(d['exercises'],1):
        a=q['answer']
        s+=f"### {i}. {q['prompt']}\n\n{t['answer']}:\n\n"+fenced(a['code'],'python')+'\n'
        s+=f"{t['input']}:\n\n"+(fenced(a['stdin'],'text') if a['stdin'] else t['none']+'\n')+'\n'
        s+=f"{t['output']}:\n\n"+fenced(a['stdout'],'text')+'\n'
        s+=f"{t['note']}: {a['explanation']}\n\n"
    return s

def markdown(doc):
    lang=doc['language'];t=LABELS[lang]
    s=f"# {doc['series_name']}\n\n"
    s+=('每个代码块独立运行。输出块以最后一个换行结束；行尾空格有意义。精确的输入输出以 JSON 字段为准。\n\n' if lang=='zh' else '各コードブロックは独立して実行します。出力ブロックは末尾の改行を含み、行末の空白にも意味があります。正確な入出力は JSON のフィールドを参照してください。\n\n')
    for d in doc['lessons']:
        s+=f"# {t['lesson'].format(n=d['seq'])} · {d['title']}\n\n`{d['code']}` · {t['level']}: {d['level_label']}\n\n"
        s+=f"{t['points']}:\n\n"+'\n'.join(f'- `{p}` — {title}' for p,title in zip(d['point_codes'],d['point_titles']))+'\n\n'
        s+=body(d,lang)
    return s

def import_rows(doc):
    # Exact lesson rows_json/JSONL field schema. All teaching material remains in
    # explain so the legacy jp^^zh examples parser cannot corrupt code delimiters.
    return [dict(code=d['code'],level=d['level'],title=d['title'],summary=d['objectives'][0],explain=body(d,doc['language']),connection='',examples='',examples_edited=0,orig_title=d['title'],seq=d['seq'],item_codes=d['item_codes'],point_codes=d['point_codes']) for d in doc['lessons']]

def main():
    for lang in ('zh','ja'):
        doc=json.loads((HERE/f'lessons.{lang}.json').read_text(encoding='utf-8'))
        (HERE/f'lessons.{lang}.md').write_text(markdown(doc),encoding='utf-8')
        rows=import_rows(doc)
        (HERE/f'lesson_import.{lang}.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
        (HERE/f'lesson_rows.{lang}.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Rendered zh/ja Markdown, lesson JSONL and rows_json arrays (13 rows each).')
if __name__=='__main__':main()
