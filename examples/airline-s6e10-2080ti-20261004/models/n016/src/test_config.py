"""Non-fitting tests for matched growth-policy settings and budget invariance."""
import unittest
from unittest.mock import patch

import train
from src.config import DEFAULT_DEPTH, DEFAULT_L2, validate_config

REQUIRED = ['--train', 'labeled.csv', '--predict', 'features.csv', '--out', 'out.csv']


class ConfigTests(unittest.TestCase):
    def test_defaults_and_explicit_arms(self):
        default = train.build_parser().parse_args(REQUIRED)
        self.assertEqual(default.iterations, 400)
        self.assertEqual(default.feature_mode, 'raw')
        self.assertEqual(default.seed, 20261004)
        self.assertEqual(default.threads, 8)
        self.assertEqual((default.grow_policy, default.min_data_in_leaf), ('Depthwise', 1))
        self.assertEqual((default.depth, default.l2_leaf_reg), (DEFAULT_DEPTH, DEFAULT_L2))
        for depth, l2 in [(6, 3), (8, 3), (8, 10)]:
            args = train.build_parser().parse_args(
                REQUIRED + ['--depth', str(depth), '--l2-leaf-reg', str(l2)])
            validate_config(args)
            self.assertEqual((args.depth, args.l2_leaf_reg), (depth, l2))

    def test_optional_summary_controls(self):
        for mode in ('raw', 'mean', 'profile'):
            args = train.build_parser().parse_args(REQUIRED + ['--feature-mode', mode])
            self.assertEqual(args.feature_mode, mode)
            self.assertEqual((args.iterations, args.depth, args.l2_leaf_reg), (400, 8, 10))

    def test_invalid_configuration_fails_before_gpu(self):
        cases = [('--iterations', '0', 'Iterations must be positive'),
                 ('--depth', '0', 'Depth must be between'),
                 ('--depth', '17', 'Depth must be between'),
                 ('--l2-leaf-reg', '-1', 'finite and positive'),
                 ('--l2-leaf-reg', '0', 'finite and positive'),
                 ('--l2-leaf-reg', 'nan', 'finite and positive'),
                 ('--l2-leaf-reg', 'inf', 'finite and positive'),
                 ('--threads', '9', 'CPU threads must be between'),
                 ('--min-data-in-leaf', '0', 'threshold must be positive')]
        for flag, value, message in cases:
            with self.subTest(flag=flag, value=value):
                argv = ['train.py', *REQUIRED, flag, value]
                with patch('sys.argv', argv), patch('train.verify_gpu') as verify:
                    with self.assertRaisesRegex(ValueError, message):
                        train.main()
                    verify.assert_not_called()

    def test_learner_parameters_and_budget_invariance(self):
        for policy, threshold in [('SymmetricTree', 1), ('Depthwise', 1), ('Depthwise', 100)]:
            for budget in [60, 180, 240]:
                args = train.build_parser().parse_args(REQUIRED + [
                    '--grow-policy', policy, '--min-data-in-leaf', str(threshold),
                    '--budget', str(budget)])
                validate_config(args)
                expected = {
                    'iterations': 400, 'depth': 8, 'learning_rate': .08,
                    'l2_leaf_reg': 10, 'grow_policy': policy,
                    'loss_function': 'Logloss', 'random_seed': 20261004,
                    'task_type': 'GPU', 'devices': '0', 'thread_count': 8,
                    'boosting_type': 'Plain', 'one_hot_max_size': 10,
                    'gpu_ram_part': .85, 'allow_writing_files': False, 'verbose': 100}
                if policy == 'Depthwise':
                    expected['min_data_in_leaf'] = threshold
                self.assertEqual(train.build_model(args).get_params(), expected)

    def test_unsupported_symmetric_threshold(self):
        args = train.build_parser().parse_args(REQUIRED + [
            '--grow-policy', 'SymmetricTree', '--min-data-in-leaf', '100'])
        with self.assertRaisesRegex(ValueError, 'does not support'):
            validate_config(args)


if __name__ == '__main__':
    unittest.main()
