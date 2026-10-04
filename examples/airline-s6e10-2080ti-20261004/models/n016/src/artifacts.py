"""Persist a byte-identical CBM alias for the generic artifact reader.

The airline evaluator hashes model.cbm; the generic harness checks model.pt.
The alias is CatBoost binary format, NOT a PyTorch checkpoint. No reserialization
and no changes to metrics/hashes/evaluator are made here.
"""
from pathlib import Path
import shutil


def copy_compatibility_alias(artifact):
    artifact = Path(artifact)
    alias = artifact.parent / 'model.pt'
    if artifact.resolve() != alias.resolve():
        shutil.copyfile(artifact, alias)
    return alias
