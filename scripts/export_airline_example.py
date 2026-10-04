#!/usr/bin/env python3
"""Export a read-only airline experiment snapshot; never runs or evaluates a candidate."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone, timedelta
import html
import json
from pathlib import Path
import re
import subprocess
import tomllib

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / 'examples/airline-s6e10-2080ti-20261004'
LABELS = {
    'root': '原始基线', 'n001': '服务评分组合（结果失效）', 'n002': '仅加入服务均值',
    'n003': '数字服务与旅客分组交互', 'n004': '增加树的数量', 'n005': '复测分组交互',
    'n006': '加入低评分数量', 'n007': '降低学习率并延长训练', 'n008': '树深 8 ＋ 更强正则化',
    'n009': '浅树对照', 'n010': '深树、较弱正则化对照', 'n011': '数值评分 ＋ 类别评分',
    'n012': '双模型平均（执行失败）', 'n013': '修复后的双模型平均', 'n014': '去掉服务均值',
    'n015': '重新加入均值的对照', 'n016': '按层生长的树（Depthwise）',
    'n017': '重新评测对称树对照', 'n018': '将对称树深度从 8 提到 10',
    'n019': '按出行类型构造评分类别交互',
}
STATES = {'done': '已完成', 'failed': '失败', 'running': '实验中', 'analyzing': '结果分析中',
          'evaluating': '评测中', 'planned': '待运行', 'incomplete': '待恢复'}


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def clean(value):
    if isinstance(value, str):
        return re.sub(r'/(?:home|media|mnt|tmp|workspace)/[^\s\"\'<>`]*', '[local-path]', value)
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k not in
                ('pid', 'session_id', 'privacy_flag', 'runner_tail', 'prompt', 'heartbeat')}
    return value


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def export_source(experiment, node, output):
    commit = node.get('commit')
    if not commit:
        raise ValueError(f"No recorded source commit for {node['id']}")
    repo = experiment / 'repo'
    names = subprocess.check_output(['git', '-C', str(repo), 'ls-tree', '-r', '--name-only', commit], text=True).splitlines()
    for name in names:
        if name != 'train.py' and not (name.startswith('src/') and name.endswith('.py')):
            continue
        dest = output / 'models' / node['id'] / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(subprocess.check_output(['git', '-C', str(repo), 'show', f'{commit}:{name}']))
    dump(output / 'models' / node['id'] / 'PROVENANCE.json', {
        'node': node['id'], 'experiment_commit': commit, 'official_score': node['score'],
        'source': 'Exact committed candidate source; no trained weights or prediction tables.',
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=EXAMPLE)
    args = parser.parse_args()
    experiment, output = args.experiment.resolve(), args.output.resolve()
    if output == experiment or output.is_relative_to(experiment):
        parser.error('The export destination must be outside the live experiment.')
    source = (experiment / 'tree.html').read_text()
    match = re.search(r'window\.__RSI_DATA__ = (.*?);</script>', source, re.S)
    if not match:
        parser.error('Run rsi render on the experiment first; expected its self-contained tree.html.')
    public = copy.deepcopy(json.loads(match[1]))
    config = tomllib.loads((experiment / 'rsi.toml').read_text())
    public['state'] = {k: v for k, v in read_json(experiment / 'state.json', {}).items()
                       if k in ('status', 'stop_reason', 'experiment')}
    # An earlier pilot's final.json is not a final result of its ongoing continuation.
    if public['state'].get('status') in ('running', 'finishing'):
        public['final'] = {}
    public.pop('task_monitor', None)
    public['monitor_notes'] = 'Archived snapshot; no live job queue connection.'
    public.pop('research_loop', None)
    public['generated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    compact_nodes = []
    ledger = []
    for node in public['nodes']:
        node['worker'] = {k: v for k, v in node.get('worker', {}).items() if k in ('model', 'effort', 'kind')}
        node.pop('executions', None)
        node['docs'] = {k: v for k, v in node.get('docs', {}).items()
                        if k in ('hypothesis', 'handoff', 'summary_md', 'progress_tail', 'failure', 'analysis')}
        node.get('metrics', {}).pop('_eval', None)
        valid = node['status'] != 'failed' and node.get('measurement', {}).get('state') == 'validated'
        score = node.get('score') if valid else None
        note = node.get('summary') or '冻结的本地验证集评测；当前差异尚不能证明稳定提升。'
        if node['id'] == 'n001':
            note = '评测后模型文件发生变化，完整性校验失败；分数不计入最佳曲线。'
        elif node['id'] == public['best']:
            note = '当前数值最高分；这是自适应搜索验证结果，稳定性与独立保留集表现尚未确认。'
        compact_nodes.append({'id': node['id'], 'parent': node['parent'],
                              'order': 0 if node['id'] == 'root' else int(node['id'][1:]),
                              'label': LABELS.get(node['id'], node['title']), 'status': node['status'],
                              'state': STATES.get(node['status'], node['status']), 'score': score,
                              'valid': valid, 'note': clean(note)})
        ledger.append({'node': node['id'], 'parent': node['parent'], 'title': node['title'],
                       'status': node['status'], 'measurement_status': node.get('measurement', {}).get('state', 'unavailable'),
                       'score': score, 'commit': node.get('commit'), 'finished_at': node.get('finished_at')})
        dump(output / 'metrics' / f"{node['id']}.json", clean({
            'measurement_status': node.get('measurement', {}).get('state', 'unavailable'),
            'node_status': node['status'], 'score': score,
            'recorded_metrics': node.get('metrics', {}),
        }))
    public = clean(public)
    dump(output / 'snapshot.json', public)
    dump(output / 'results.json', ledger)
    payload = json.dumps(public, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    exported = source[:match.start(1)] + payload + source[match.end(1):]
    exported = clean(exported).replace(public['experiment'] + ' ·', public['experiment'] + ' · archived snapshot ·', 1)
    (output / 'tree.html').write_text('\n'.join(line.rstrip() for line in exported.splitlines()) + '\n')
    pending = 0
    knowledge = public.get('knowledge', {})
    for mem in experiment.parent.glob('_memory/airline-s6e10-2080ti/protocols/*'):
        pointer = read_json(mem / 'CURRENT.json', {})
        if pointer.get('revision') != knowledge.get('revision'):
            continue
        wiki = read_json(mem / 'revisions' / pointer['revision'] / 'state.json', {})
        pending = len({p.stem for p in (mem / 'raw').glob('*.json')} - set(wiki.get('consumed', [])))
    research = [n for n in compact_nodes if n['id'] != 'root']
    active = sum(n['status'] not in ('done', 'failed', 'abandoned') for n in research)
    compact = {'experiment': public['experiment'], 'timestamp': datetime.now(timezone(timedelta(hours=3))).strftime('%m 月 %d 日 %H:%M（沙特时间）'),
               'status': '阶段快照 · ' + ('实验运行中' if active else '规划／收尾中'),
               'used': len(research), 'limit': config['search']['max_nodes'],
               'done': sum(n['status'] == 'done' for n in research), 'failed': sum(n['status'] == 'failed' for n in research),
               'active': active, 'best': public['best'], 'pending': pending, 'nodes': compact_nodes}
    shell = (EXAMPLE / 'assets/dashboard-shell.html').read_text()
    compact_json = json.dumps(compact, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    (output / 'index.html').write_text(shell.replace('__RSI_PAYLOAD__', html.escape(compact_json, quote=True)))
    dump(output / 'dashboard-data.json', compact)
    config_text = re.sub(r'(?m)^dir = .*$', 'dir = "../../pi_rsi/tasks/airline-s6e10-2080ti"', (experiment / 'rsi.toml').read_text())
    (output / 'rsi.toml').write_text(clean(config_text))
    for node_id in ('root', public['best']):
        export_source(experiment, next(n for n in public['nodes'] if n['id'] == node_id), output)
    baseline = next(n for n in ledger if n['node'] == 'root')['score']
    best = next(n for n in ledger if n['node'] == public['best'])
    summary = {'snapshot_at_utc': public['generated_at'], 'run_state_at_snapshot': public['state'],
               'nodes_allocated': len(research), 'node_limit': compact['limit'], 'completed': compact['done'],
               'failed': compact['failed'], 'active': active, 'baseline_auc': baseline,
               'best_node': public['best'], 'best_auc': best['score'], 'delta_from_baseline': best['score'] - baseline,
               'wiki_claims': len(knowledge.get('claims', [])), 'wiki_pending': pending,
               'final_holdout_evaluated': bool(public.get('final', {}).get('best_final_score')),
               'interpretation': 'Adaptive search-validation evidence; repeatability and independent confirmation remain unestablished.'}
    dump(output / 'SUMMARY.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
