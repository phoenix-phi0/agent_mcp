import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""文件夹式 agent 的模型、技能与工具白名单。只使用假客户端。"""
import json
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools.dsl import DSLEngine, DSLError


VERBS = Path(__file__).resolve().parents[2] / 'verbs'
FLOW = '调用\n    任务 核对约定\n    角色 REVIEWER\n    记录 result\n'


class Client(ScriptClient):
    offline = True

    def __init__(self, replies):
        super().__init__(replies)
        self.seen = []

    def chat_messages(self, messages, temperature=None, **kw):
        self.seen.append((messages, kw))
        return super().chat_messages(messages, temperature=temperature, **kw)


def make_profile(root, **config):
    folder = Path(root, 'agents', 'REVIEWER')
    folder.mkdir(parents=True)
    (folder / 'SOUL.md').write_text('你是约定审查员。', encoding='utf-8')
    (folder / 'agent.json').write_text(json.dumps(config), encoding='utf-8')
    return folder


def run_flow(root, client):
    Path(root, 'flow.wf').write_text(FLOW, encoding='utf-8')
    engine = DSLEngine(client=client, workdir=root, verbose=False, verbs_root=VERBS)
    engine.run('用包 workflow\n编排执行 flow.wf')
    return engine


def test_model_effort_and_skill():
    with tempfile.TemporaryDirectory() as root:
        folder = make_profile(root, model='cli:claude/sonnet', effort='high',
                              tools=[], skills=['skills/review.md'])
        (folder / 'skills').mkdir()
        (folder / 'skills/review.md').write_text('逐条检查接口字段。', encoding='utf-8')
        client = Client([{'decide': '通过'}])
        engine = run_flow(root, client)
        assert engine.vars['result']['decide'] == '通过'
        messages, kwargs = client.seen[0]
        assert kwargs['model'] == 'cli:claude/sonnet@high'
        assert '你是约定审查员。' in messages[0]['content']
        assert '逐条检查接口字段。' in messages[0]['content']


def test_tool_allowlist():
    with tempfile.TemporaryDirectory() as root:
        make_profile(root, model='api:zhipu/glm-5.3', tools=['相加'],
                     packages=['common'], skills=[], max_tool_rounds=2)

        class ToolClient(Client):
            def chat_raw(self, messages, **kw):
                self.seen.append((messages[:], kw))
                if len(self.seen) == 1:
                    return {'choices': [{'message': {'role': 'assistant', 'content': '',
                        'tool_calls': [{'id': '1', 'function': {'name': '相加',
                            'arguments': '{"甲":"2","乙":"3"}'}}]}}]}
                assert any(m.get('role') == 'tool' and m['content'] == '5' for m in messages)
                return {'choices': [{'message': {'role': 'assistant',
                        'content': '{"sum":5}'}}]}

        client = ToolClient([])
        engine = run_flow(root, client)
        assert engine.vars['result'] == {'sum': 5}
        schemas = client.seen[0][1]['tools']
        assert [s['function']['name'] for s in schemas] == ['相加']
        assert client.seen[0][1]['model'] == 'api:zhipu/glm-5.3'


def test_invalid_effort_and_skill_path():
    with tempfile.TemporaryDirectory() as root:
        folder = make_profile(root, model='api:zhipu/glm-5.3', effort='high',
                              tools=[], skills=[])
        try:
            run_flow(root, Client([{}]))
        except DSLError as exc:
            assert '只有 cli:claude' in str(exc)
        else:
            raise AssertionError('不支持的思考强度应拒绝')
        (folder / 'agent.json').write_text(json.dumps({
            'model': 'cli:claude/sonnet', 'tools': [], 'skills': ['../outside.md']}),
            encoding='utf-8')
        try:
            run_flow(root, Client([{}]))
        except DSLError as exc:
            assert '越出目录' in str(exc)
        else:
            raise AssertionError('技能不能越出 agent 目录')


if __name__ == '__main__':
    test_model_effort_and_skill()
    test_tool_allowlist()
    test_invalid_effort_and_skill_path()
    print('3 agent profile tests passed')
