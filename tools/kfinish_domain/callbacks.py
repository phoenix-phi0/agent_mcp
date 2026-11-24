"""kfinish 领域的回调：传感器读 <state>/state.json 转成事实；动作调 tools/kfinish.py 里的原语。

上下文里的 cwd 就是运行目录（state_dir）。原语实现由 tools.kfinish.run() 用 bind() 注入，
这样 `python -m tools.kfinish`（模块名是 __main__）和 `import tools.kfinish` 都用同一份、可被测试替换的实现。
"""
import json

IMPL = None


def bind(impl):
    global IMPL
    IMPL = impl


def _impl():
    if IMPL is None:
        raise RuntimeError('kfinish 回调没有绑定实现（要经 tools.kfinish.run 调用）')
    return IMPL


def state_facts(ctx):
    return json.dumps({'facts': _impl().state_facts(ctx['cwd'])})


def _action(name):
    def call(binding, ctx):
        return _impl().run_step(ctx['cwd'], name, binding.get('l'))
    call.__name__ = name
    return call


CALLBACKS = {'state_facts': state_facts}
for _name in ('pack', 'repack_index', 'verify', 'deploy_dryrun', 'deploy', 'prod_check'):
    CALLBACKS[_name] = _action(_name)
