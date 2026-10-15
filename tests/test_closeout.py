"""Editorial recovery must preserve measurements and never start training."""
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pi_rsi.closeout import recover, validated_measurement
from pi_rsi.config import ExperimentCfg, TaskCfg
from pi_rsi.research import ResearchLoop
from pi_rsi.runner import RunResult
from pi_rsi.tree import Node,Tree
from pi_rsi.util import atomic_write_json


class CloseoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
        self.cfg=ExperimentCfg('test',base/'exp',TaskCfg(name='fixture',dir=str(base/'task')))
        self.cfg.dir.mkdir();self.tree=Tree(self.cfg.tree_path)
        atomic_write_json(self.cfg.dir/'final.json',{'stop_reason':'wallclock','elapsed_s':42})
        self.tree.add(Node('root',None,0,'base','',status='done',score=.5,commit='root'))
        self.node=Node('n001','root',1,'candidate','test a hypothesis',status='failed',score=.6,commit='abc',base_commit='root',
            failure='harness error: RuntimeError: timeout',worker={'evaluation_validated':{'commit':'abc','score':.6}})
        self.tree.add(self.node)
        run=self.cfg.nodes_dir/'n001/eval/run.proxy';run.mkdir(parents=True)
        (run/'model.pt').write_bytes(b'fixed checkpoint');(run/'predictions.npy').write_bytes(b'fixed predictions')
        self.metrics={'score':.6,'model_sha256':hashlib.sha256((run/'model.pt').read_bytes()).hexdigest(),
                      'predictions_sha256':hashlib.sha256((run/'predictions.npy').read_bytes()).hexdigest(),
                      '_eval':{'run_dir':str(run)}}
        atomic_write_json(self.cfg.nodes_dir/'n001/eval/metrics.validation.json',self.metrics)
        self.analysis={'observations':['Official fixed score is 0.6 against baseline 0.5.'],
                      'belief_revisions':[], 'competing_explanations':['Sampling variation.'],
                      'limitations':['Synthetic unit test.'], 'next_experiments':[],
                      'interpretation':'No causal proof.','noise_assessment':'Noise not estimated.',
                      'reason':'Search is over.','recommendation':'saturated'}
        self.runner=Mock(model='openai-codex/gpt-6.1-sol',ask_json=Mock(return_value=(self.analysis,RunResult(ok=True,exit_code=0))))
        self.orch=SimpleNamespace(cfg=self.cfg,tree=self.tree,costs={},research=SimpleNamespace(runner=self.runner),
           log=Mock(),add_cost=Mock(),noise_level=Mock(return_value=.01),render=Mock(),
           memory=SimpleNamespace(context=Mock(return_value=''),sync=Mock(),reflect=Mock(return_value=False)),
           maintainer=Mock(),utility=SimpleNamespace(audit=Mock(return_value={'summary':'Measured 0.6.',
            'verdict':'improved','claim_check':{'consistent':True,'note':'fixed metric'},'insights':[],'deadends':[]})))

    def tearDown(self):self.tmp.cleanup()

    def test_changed_prediction_artifact_is_rejected(self):
        p=Path(self.metrics['_eval']['run_dir'])/'predictions.npy';p.write_bytes(b'changed')
        with patch('pi_rsi.closeout.gitops.head',return_value='abc'),patch('pi_rsi.closeout.gitops.git',return_value=''):
            with self.assertRaises(ValueError):validated_measurement(self.orch,self.node)

    def test_recovery_publishes_existing_measurement_without_evaluation(self):
        before=(self.cfg.nodes_dir/'n001/eval/metrics.validation.json').read_bytes()
        with patch('pi_rsi.closeout.gitops.head',return_value='abc'),patch('pi_rsi.closeout.gitops.git',return_value=''), \
             patch('pi_rsi.closeout.gitops.log_oneline',return_value='abc candidate'), \
             patch('pi_rsi.closeout.gitops.diff_stat',return_value='model.py'), \
             patch('pi_rsi.evaluator.run_eval',side_effect=AssertionError('must not train or score again')):
            self.assertEqual(recover(self.orch,seconds=30),['n001'])
        self.assertEqual(self.node.status,'done');self.assertEqual(self.tree.best_id(),'n001')
        self.assertEqual((self.cfg.nodes_dir/'n001/eval/metrics.validation.json').read_bytes(),before)
        self.assertTrue((self.cfg.nodes_dir/'n001/closeout.original.json').exists())
        self.assertTrue((self.cfg.nodes_dir/'n001/analysis.json').exists())

    def test_expired_admission_budget_still_allows_bounded_handoff(self):
        loop=object.__new__(ResearchLoop)
        loop.cfg=SimpleNamespace(search=SimpleNamespace(max_wallclock_s=10))
        loop.o=SimpleNamespace(stop_flag=SimpleNamespace(is_set=lambda:False),started_ts=time.time()-20)
        with self.assertRaises(RuntimeError):loop._remaining(30)
        self.assertEqual(loop._remaining(30,completion=True),30)


if __name__=='__main__':unittest.main()
