"""Research hypotheses, execution attempts and documents have independent identities."""
import unittest
from unittest.mock import Mock, patch

from pi_rsi.memory import ResearchMemory
from pi_rsi.orchestrator import Orchestrator
from pi_rsi.tree import Node
from pi_rsi.worker import run_node
from tests import test_stage_recovery
from tests.test_research_loop import decision


class ArchitectureTests(unittest.TestCase):
    setUp = test_stage_recovery.StageRecoveryTests.setUp
    tearDown = test_stage_recovery.StageRecoveryTests.tearDown

    def test_research_frontier_can_return_to_a_full_root(self):
        self.cfg.search.max_nodes = 3
        self.cfg.search.width_root = 1
        self.assertEqual(len(self.orch.tree.children('root')), 1)
        self.assertTrue(self.orch.scheduler.expandable(self.orch.tree.get('root')))
        snapshot = self.orch.research._snapshot(self.orch.scheduler)
        self.assertIn('root', [p['id'] for p in snapshot['parents']])
        cycle = self.orch.research._new_cycle()
        self.assertEqual(self.orch.research._validate(decision('root'), snapshot, cycle)['candidates'][0]['parent'], 'root')

    def test_completed_task_redelivery_cannot_reexecute_or_republish(self):
        with patch('pi_rsi.worker.run_eval', side_effect=AssertionError('no evaluation replay')):
            run_node(self.orch, self.node)
            receipt = self.orch.executions.path(self.node).read_bytes()
            self.node.status = 'failed'  # stale compatibility projection, not execution authority
            self.node.worker['resume_implementation'] = True
            self.orch.research.analyze = Mock(side_effect=AssertionError('no analysis replay'))
            self.orch.utility.audit = Mock(side_effect=AssertionError('no audit replay'))
            run_node(self.orch, self.node)
        self.assertEqual(self.node.status, 'done')
        self.assertEqual(self.orch.executions.path(self.node).read_bytes(), receipt)
        self.assertEqual(len(self.orch.tree.non_root()), 1)
        self.orch.worker_runner.run_agent.assert_not_called()

    def test_journal_first_measurement_commit_survives_tree_write_crash(self):
        reference = {'state': 'validated', **self.node.worker['evaluation_validated']}
        self.orch.executions.measured(self.node, reference)
        self.orch.tree.update(self.node, status='planned', score=None, commit=None, measurement={}, worker={})
        restarted = Orchestrator(self.cfg, verbose=False)
        restarted.recover()
        node = restarted.tree.get('n001')
        self.assertEqual(node.score, 1.2)
        self.assertTrue(node.measurement_valid)
        restarted.research.analyze = Mock()
        restarted.utility.audit = Mock(return_value=self.audit)
        restarted.worker_runner = self.orch.worker_runner
        with patch('pi_rsi.worker.run_eval', side_effect=AssertionError('no evaluation replay')):
            run_node(restarted, node)
        self.assertEqual(node.status, 'done', node.failure)
        self.assertEqual(len(restarted.tree.non_root()), 1)

    def test_legacy_retry_nodes_are_provenance_not_extra_hypotheses(self):
        self.cfg.search.max_nodes = 5
        first = Node('n002','root',1,'same idea','same hypothesis',status='failed',score=.9,commit='old',
                     worker={'evaluation_validated':{'score':.9,'commit':'old'}})
        retry = Node('n003','root',1,'same idea','same hypothesis',status='done',score=.9,commit='new',attempt=2,retry_of='n002')
        self.orch.tree.add(first);self.orch.tree.add(retry)
        self.orch.executions.migrate(self.orch.tree)
        self.assertEqual(first.hypothesis_key, retry.hypothesis_key)
        self.assertEqual(self.orch.scheduler.launched_count(), 2)
        self.assertEqual(self.orch.scheduler.execution_count(), 3)
        self.assertEqual(len(self.orch.tree.nodes), 4)  # no provenance was deleted
        self.assertIsNone(self.orch.scheduler.stop_reason())  # obsolete failed document cannot stop its completed hypothesis
        self.assertNotIn('n002',[p['id'] for p in self.orch.research._snapshot(self.orch.scheduler)['parents']])

    def test_pending_attempt_reservation_prevents_budget_oversubscription(self):
        self.cfg.search.max_nodes = 5
        self.cfg.search.max_attempts = 2
        self.assertTrue(self.orch.scheduler.can_launch())
        self.orch.tree.add(Node('n002','root',1,'another idea','another hypothesis'))
        self.assertEqual(self.orch.scheduler.launched_count(), 2)
        self.assertEqual(self.orch.scheduler.reserved_attempts(), 1)
        self.assertFalse(self.orch.scheduler.can_launch())

    def test_controller_lease_rejects_duplicate_execution(self):
        second = Orchestrator(self.cfg, verbose=False)
        with self.orch.executions.controller_lease():
            with self.assertRaises(RuntimeError):
                second.run()
        self.orch.worker_runner.run_agent.assert_not_called()

    def test_ai_document_revision_is_not_new_scientific_evidence(self):
        self.cfg.memory.enabled = True
        memory = ResearchMemory(self.cfg)
        original = {'kind':'experiment','protocol':memory.protocol,'role':'selection','commit':'fixed',
                    'metrics':{'score':1.2},'worker_interpretation':{'text':'Original interpretation.'}}
        memory._capture(original)
        before = memory.evidence_fingerprint()
        changed = {**original,'worker_interpretation':{'text':'Revised wording.'},'status':'incomplete'}
        memory._capture(changed)
        self.assertEqual(memory.evidence_fingerprint(), before)
        memory._capture({**changed,'metrics':{'score':1.3}})
        self.assertNotEqual(memory.evidence_fingerprint(), before)

    def test_recovery_cannot_replace_a_measurement_but_explicit_revision_keeps_history(self):
        original = {'state':'validated',**self.node.worker['evaluation_validated']}
        self.orch.executions.measured(self.node, original)
        changed = {**original,'score':1.3}
        with self.assertRaises(ValueError):
            self.orch.executions.measured(self.node, changed)
        self.orch.executions.revise_measurement(self.node, changed)
        record = self.orch.executions.read(self.node)
        self.assertEqual(record['measurement_history'], [original])
        self.assertEqual(record['measurement']['score'], 1.3)
        self.assertEqual(self.metrics_path.read_bytes(), self.before[self.metrics_path])


if __name__ == '__main__':
    unittest.main()
