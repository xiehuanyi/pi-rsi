import importlib.util
import itertools
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("duel_delivery", Path(__file__).parents[1] / "scripts/duel_delivery.py")
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


def metrics(values, protocol="v1"):
    mean = sum(values) / len(values)
    return {"protocol_id": protocol, "per_item": [{"id": str(i), "value": v} for i, v in enumerate(values)],
            "per_opponent": {"one": {"score": mean}}, "errors": 0}


class DeliveryTests(unittest.TestCase):
    def test_large_confirmation_keeps_exact_test(self):
        result = delivery.paired_compare(metrics([0.5] * 64), metrics([0.75] * 64))
        self.assertEqual(result["exact_two_sided_sign_flip_p"], 2 / 2**64)

    def test_lattice_matches_exhaustive_mixed_and_tied_blocks(self):
        diffs = [0.125, -0.25, 0, 0.375, 0.125, -0.0625, 0]
        observed = abs(sum(diffs))
        expected = sum(abs(sum(s*d for s, d in zip(signs, diffs))) >= observed
                       for signs in itertools.product((-1, 1), repeat=len(diffs))) / 2**len(diffs)
        result = delivery.paired_compare(metrics([0.5] * len(diffs)), metrics([0.5 + d for d in diffs]))
        self.assertEqual(result["exact_two_sided_sign_flip_p"], expected)

    def test_identical_outcomes_are_inconclusive(self):
        m = metrics([0.5] * 12)
        result = delivery.paired_compare(m, m)
        self.assertEqual(result["delta"], 0)
        self.assertEqual(result["exact_two_sided_sign_flip_p"], 1)
        self.assertEqual(result["decision"], "inconclusive")

    def test_consistent_seed_block_gain_is_corroborated(self):
        result = delivery.paired_compare(metrics([0.5] * 12), metrics([0.75] * 12))
        self.assertEqual(result["delta"], 0.25)
        self.assertEqual(result["exact_two_sided_sign_flip_p"], 2 / 4096)
        self.assertEqual(result["decision"], "locally_corroborated")

    def test_protocol_mismatch_and_errors_do_not_promote(self):
        with self.assertRaises(ValueError):
            delivery.paired_compare(metrics([0.5]), metrics([1], "v2"))
        m = metrics([1] * 12)
        m["errors"] = 1
        self.assertEqual(delivery.paired_compare(metrics([0.5] * 12), m)["decision"], "inconclusive")

    def test_packaging_excludes_evaluation_and_external_symlinks(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside:
            root = Path(td)
            (root / "agent.py").write_text("def agent(obs): return {}")
            (root / "eval").mkdir()
            (root / "eval" / "private.json").write_text("not a deliverable")
            self.assertEqual(delivery.files_for_delivery(root), [root / "agent.py"])
            (root / "src").mkdir()
            (Path(outside) / "secret.py").write_text("not part of the candidate")
            (root / "src" / "external.py").symlink_to(Path(outside) / "secret.py")
            with self.assertRaises(ValueError):
                delivery.files_for_delivery(root)


if __name__ == "__main__":
    unittest.main()
