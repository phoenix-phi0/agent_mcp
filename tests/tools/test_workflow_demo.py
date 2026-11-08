import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
"""工作目录中的四个真实 agent 文件夹驱动完整编排脚本；每步的回复都要符合节点格式。"""
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools.dsl import DSLEngine
from wf_fixtures import REPLIES

ROOT = Path(__file__).resolve().parents[2]


def run():
    tmp = Path(tempfile.mkdtemp())
    try:
        demo = tmp / 'workflow_demo'
        shutil.copytree(ROOT / 'workflow_demo', demo,
                        ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
        client = ScriptClient(list(REPLIES))
        client.offline = True
        engine = DSLEngine(client=client, workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
        engine.run_file('run.zs')
        assert engine.vars['contract'] == REPLIES[2]
        assert len(engine.vars['task_results']) == 2
        assert engine.vars['task_result'] == REPLIES[8]
        assert len(client.calls) == 10
        # 提示词里带上「本次调用」和格式：模型不用再猜是哪一种调用
        first = client.calls[0]
        text = str(first)
        assert '本次调用：接口约定（提交格式 contract）' in text, text[:300]
        print('workflow demo passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
