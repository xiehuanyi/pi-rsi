"""Builder regression checks: no GPU fits and no final evaluation.
Run: .venv/bin/python eval/test_protocol.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import eval as evaluator
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
FAKE = '''
import argparse, time
import pandas as pd
p=argparse.ArgumentParser()
for name in ('train','predict','out'): p.add_argument('--'+name)
a,_=p.parse_known_args()
x=pd.read_csv(a.predict)
assert 'satisfaction' not in x.columns
mode=MODE
if mode=='exit': raise SystemExit(7)
if mode=='sleep': time.sleep(5)
y=pd.DataFrame({'id':x.id, 'satisfaction':0.5})
if mode=='order': y=y.iloc[::-1]
if mode=='count': y=y.iloc[:-1]
if mode=='nan': y.loc[0,'satisfaction']=float('nan')
if mode=='range': y.loc[0,'satisfaction']=1.01
if mode=='schema': y['extra']=0
if mode=='duplicate': y.loc[0,'id']=y.loc[1,'id']
y.to_csv(a.out,index=False)
'''


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '_newtask')
        self.base = Path(self.tmp.name)
        self.agent = self.base / 'worker'
        (self.agent / 'data').mkdir(parents=True)
        for name in ('quick_train.csv', 'quick_dev.csv'):
            shutil.copyfile(ROOT / 'starter/data' / name, self.agent / 'data' / name)

    def tearDown(self):
        self.tmp.cleanup()

    def candidate(self, mode):
        (self.agent / 'train.py').write_text(FAKE.replace('MODE', repr(mode)))

    def run_case(self, mode, budget=60):
        self.candidate(mode)
        out = self.base / mode / 'metrics.json'
        with patch.object(evaluator, 'verify_gpu', return_value={'test': 'no GPU work'}), \
             patch.dict(evaluator.BUDGETS, {'quick': budget}):
            code = evaluator.evaluate(self.agent, 'quick', out, sys.executable, quiet=True)
        return code, json.loads(out.read_text())

    def test_constant_auc_and_no_bogus_noise(self):
        code, m = self.run_case('constant')
        self.assertEqual(code, 0)
        self.assertEqual(m['score'], 0.5)
        self.assertEqual(m['n'], 10000)
        for key in ('per_item', 'score_std', 'score_sem'):
            self.assertNotIn(key, m)

    def test_invalid_outputs_fail_closed(self):
        for mode in ('order', 'count', 'nan', 'range', 'schema', 'duplicate', 'exit'):
            with self.subTest(mode=mode):
                code, m = self.run_case(mode)
                self.assertEqual(code, 1)
                self.assertIsNone(m['score'])
                self.assertIn('error', m)

    def test_bounded_execution(self):
        code, m = self.run_case('sleep', budget=1)
        self.assertEqual(code, 1)
        self.assertIsNone(m['score'])
        self.assertIn('TimeoutError', m['error'])
        self.assertLess(m['elapsed_s'], 4)

    def test_standalone_copied_cli(self):
        # Worker has only public quick data, candidate, copied evaluator: no private/raw root.
        self.candidate('constant')
        shutil.copytree(ROOT / 'eval', self.agent / 'eval', ignore=shutil.ignore_patterns('__pycache__'))
        out = self.base / 'copied-metrics.json'
        p = subprocess.run([sys.executable, 'eval/eval.py', '--agent-dir', '.',
                            '--seedset', 'quick', '--out', str(out),
                            '--python', sys.executable, '--quiet'],
                           cwd=self.agent, timeout=20, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(out.read_text())['score'], 0.5)
        self.assertFalse((self.agent / 'private').exists())

    def test_unknown_wrapper_budget(self):
        run_dir = self.base / 'invalid-budget'
        p = subprocess.run([sys.executable, str(ROOT / 'eval/run.py'), '--budget', '61',
                            '--run-dir', str(run_dir)], cwd=self.agent, timeout=20,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIsNone(json.loads((run_dir / 'metrics.json').read_text())['score'])

    def test_measured_scores_independently(self):
        # Validation only: final is never read here.
        for level in ('quick', 'validation'):
            m = json.loads((ROOT / f'_newtask/baseline/{level}/metrics.json').read_text())
            if level == 'quick':
                labels = pd.read_csv(ROOT / 'starter/data/quick_dev.csv')
                predictions = pd.read_csv(ROOT / '_newtask/baseline/quick/predictions.csv')
            else:
                labels = pd.read_csv(ROOT / 'private/validation_labels.csv')
                paths = [p for p in (ROOT / 'private/evaluations').glob('validation-*/predictions.csv')
                         if evaluator.sha(p) == m['prediction_sha256']]
                self.assertEqual(len(paths), 1)
                predictions = pd.read_csv(paths[0])
            self.assertTrue(labels.id.equals(predictions.id))
            self.assertEqual(roc_auc_score(labels.satisfaction, predictions.satisfaction), m['score'])
            self.assertEqual(evaluator.sha(ROOT / f'_newtask/baseline/{level}/model.cbm'), m['model_sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
