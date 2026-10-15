#!/usr/bin/env python3
"""Read-only, standard-library export of a research wiki and its evidence provenance."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / 'examples/airline-s6e10-2080ti-20261004'


def clean(value):
    if isinstance(value, str):
        return re.sub(r'/(?:home|media|mnt|tmp|workspace)/[^\s\"\'<>`]*', '[local-path]', value)
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    return value


def build_wiki_data(memory: Path, revision: str | None = None):
    memory = memory.resolve()
    revision = revision or json.loads((memory / 'CURRENT.json').read_text())['revision']
    state = json.loads((memory / 'revisions' / revision / 'state.json').read_text())
    evidence = []
    for evidence_id in sorted(state['consumed']):
        path = memory / 'raw' / (evidence_id + '.json')
        packet = json.loads(path.read_text())
        record = {k: packet.get(k) for k in (
            'id', 'kind', 'title', 'node', 'parent', 'observed_at', 'captured_at', 'commit',
            'status', 'measurement_status', 'selection_eligible', 'score', 'metric', 'level',
            'source_url', 'attribution', 'sha256',
        ) if packet.get(k) is not None}
        if urlsplit(record.get('source_url', '')).scheme not in ('http', 'https'):
            record.pop('source_url', None)
        record['packet_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        record['metrics'] = {k: packet.get('metrics', {}).get(k) for k in
                             ('n', 'train_n', 'model_seed', 'candidate_elapsed_s', 'budget_s', 'protocol_sha256')
                             if k in packet.get('metrics', {})}
        evidence.append(record)
    history, seen, cursor = [], set(), revision
    while cursor:
        if cursor in seen:
            raise ValueError('Revision ancestry contains a cycle')
        seen.add(cursor)
        old = json.loads((memory / 'revisions' / cursor / 'state.json').read_text())
        history.append({
            'revision': cursor, 'previous_revision': old.get('previous_revision'),
            'updated_at': old.get('updated_at'), 'claim_count': len(old['claims']),
            'counts': dict(Counter(c['status'] for c in old['claims'].values())),
            'changes': old.get('changes', []),
            'what_changed': old.get('agenda', {}).get('what_changed', ''),
        })
        cursor = old.get('previous_revision') or ''
    ids = {e['id'] for e in evidence}
    missing = {eid for c in state['claims'].values() for eid in c['supports'] + c['opposes']} - ids
    if missing:
        raise ValueError('Evidence references absent from selected revision: ' + ', '.join(sorted(missing)))
    return clean({
        'revision': revision, 'updated_at': state['updated_at'],
        'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'protocol': state['protocol'], 'claims': list(state['claims'].values()),
        'agenda': state.get('agenda', {}), 'evidence': evidence, 'history': history,
        'counts': dict(Counter(c['status'] for c in state['claims'].values())),
        'kind_counts': dict(Counter(c['kind'] for c in state['claims'].values())),
        'evidence_counts': dict(Counter(e['kind'] for e in evidence)),
        'provenance_note': 'Evidence index contains aggregate metadata and hashes, not raw packets, dataset rows or model-session logs. Multiple entries can describe the same experiment/source.',
    })


def export_wiki(memory: Path, output: Path = EXAMPLE, revision: str | None = None):
    memory, output = memory.resolve(), output.resolve()
    if output == memory or output.is_relative_to(memory):
        raise ValueError('Output must be outside the live wiki')
    data = build_wiki_data(memory, revision)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'wiki-data.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    shell = (EXAMPLE / 'assets/wiki-shell.html').read_text()
    (output / 'wiki.html').write_text(shell.replace('__WIKI_PAYLOAD__', html.escape(payload, quote=True)))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--memory', type=Path, required=True, help='protocol directory containing CURRENT.json')
    parser.add_argument('--revision', help='default: CURRENT.json; pin a revision to match an archived experiment')
    parser.add_argument('--output', type=Path, default=EXAMPLE)
    args = parser.parse_args()
    data = export_wiki(args.memory, args.output, args.revision)
    print(json.dumps({'revision': data['revision'], 'claims': len(data['claims']),
                      'evidence': len(data['evidence']), 'revisions': len(data['history'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
