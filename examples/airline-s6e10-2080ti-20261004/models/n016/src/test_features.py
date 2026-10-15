"""Non-fitting checks for the exact prior summaries and CBM compatibility."""
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from src.artifacts import copy_compatibility_alias
from src.features import (
    CABIN_RATINGS, CATEGORICAL, DIGITAL_RATINGS, SERVICE_RATINGS,
    SUMMARY_FEATURES, make_features,
)


class FeatureTests(unittest.TestCase):
    def setUp(self):
        values = np.array([[0, 1, 2, 3, 4, 5, 0, 1, 2, 3, 4, 5, 0],
                           [5] * 13, [0] * 13], dtype=float)
        self.frame = pd.DataFrame(values, columns=SERVICE_RATINGS, index=[7, 2, 9])
        for col in CATEGORICAL:
            self.frame[col] = ['category', None, 'other']
        self.frame['Arrival Delay in Minutes'] = [np.nan, 1, 2]
        self.frame['id'] = [91, 12, 33]
        self.frame['satisfaction'] = [0, 1, 0]

    def test_exact_formulas(self):
        X = make_features(self.frame, 'profile')
        ratings = self.frame.loc[:, SERVICE_RATINGS].to_numpy(dtype=np.float64)
        expected = np.column_stack([
            ratings.mean(1), ratings.std(1, ddof=0), np.ptp(ratings, axis=1),
            (ratings <= 1).sum(1), (ratings >= 4).sum(1),
            self.frame.loc[:, DIGITAL_RATINGS].to_numpy().mean(1)
            - self.frame.loc[:, CABIN_RATINGS].to_numpy().mean(1),
        ]).astype('float32')
        np.testing.assert_array_equal(X.loc[:, SUMMARY_FEATURES].to_numpy(), expected)
        self.assertTrue(all(X[col].dtype == np.float32 for col in SUMMARY_FEATURES))
        np.testing.assert_array_equal(make_features(self.frame, 'mean')['service_mean'], expected[:, 0])

    def test_preservation_and_independence(self):
        original = self.frame.copy(deep=True)
        raw = make_features(self.frame, 'raw')
        for mode in ('raw', 'mean', 'profile'):
            X = make_features(self.frame, mode)
            pd.testing.assert_frame_equal(X.loc[:, raw.columns], raw)
            self.assertEqual(X.index.tolist(), [7, 2, 9])
            self.assertNotIn('id', X)
            self.assertNotIn('satisfaction', X)
            self.assertTrue(np.isnan(X['Arrival Delay in Minutes'].iloc[0]))
            self.assertEqual(X['Gender'].iloc[1], '__MISSING__')
            changed = self.frame.assign(id=[1, 2, 3], satisfaction=[1, 0, 1])
            pd.testing.assert_frame_equal(X, make_features(changed, mode))
            pd.testing.assert_frame_equal(X, make_features(self.frame.drop(columns='satisfaction'), mode))
        pd.testing.assert_frame_equal(self.frame, original)

    def test_default_is_raw_and_mean_removes_only_one_column(self):
        # Include every remaining numeric raw predictor to check the 21-column contract.
        frame = self.frame.assign(**{
            'Age': [20, 30, 40], 'Flight Distance': [100, 200, 300],
            'Departure Delay in Minutes': [0, 1, 2],
        })
        raw = make_features(frame)
        explicit_raw = make_features(frame, 'raw')
        mean = make_features(frame, 'mean')
        self.assertEqual(len(raw.columns), 21)
        self.assertEqual(mean.columns.tolist(), raw.columns.tolist() + ['service_mean'])
        pd.testing.assert_frame_equal(raw, explicit_raw)
        pd.testing.assert_frame_equal(raw, mean.drop(columns='service_mean'))
        self.assertEqual([col for col in raw if col in CATEGORICAL], CATEGORICAL)

    def test_row_local_and_invalid_mode(self):
        X = make_features(self.frame, 'profile')
        pd.testing.assert_frame_equal(X.iloc[[1]], make_features(self.frame.iloc[[1]], 'profile'))
        with self.assertRaises(ValueError):
            make_features(self.frame, 'unknown')

    def test_byte_identical_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / 'example.cbm'
            content = b'CBM synthetic bytes\x00\xff'
            artifact.write_bytes(content)
            alias = copy_compatibility_alias(artifact)
            self.assertEqual(alias.name, 'model.pt')
            self.assertEqual(alias.read_bytes(), content)
            self.assertEqual(hashlib.sha256(alias.read_bytes()).digest(),
                             hashlib.sha256(artifact.read_bytes()).digest())
            self.assertEqual(copy_compatibility_alias(alias), alias)
            artifact.write_bytes(b'new bytes')
            copy_compatibility_alias(artifact)
            self.assertEqual(alias.read_bytes(), b'new bytes')


if __name__ == '__main__':
    unittest.main()
