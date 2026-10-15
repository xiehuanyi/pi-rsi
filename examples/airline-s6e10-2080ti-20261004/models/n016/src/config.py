"""Prespecified growth-policy intervention; invariant across evaluation budgets."""
import math

DEFAULT_ITERATIONS = 400
DEFAULT_DEPTH = 8
DEFAULT_L2 = 10.0
# Designated Depthwise/1, irrespective of quick ordering.
DEFAULT_GROW_POLICY = 'Depthwise'
GROW_POLICIES = ('SymmetricTree', 'Depthwise')
DEFAULT_MIN_DATA_IN_LEAF = 1


def validate_config(args):
    """Reject invalid settings before GPU verification or input loading."""
    if args.iterations <= 0:
        raise ValueError('Iterations must be positive')
    if not 1 <= args.threads <= 8:
        raise ValueError('CPU threads must be between 1 and 8')
    if not 1 <= args.depth <= 16:
        raise ValueError('Depth must be between 1 and 16')
    if args.grow_policy not in GROW_POLICIES:
        raise ValueError('Unsupported growth policy')
    if args.min_data_in_leaf <= 0:
        raise ValueError('Minimum split-support threshold must be positive')
    if args.grow_policy == 'SymmetricTree' and args.min_data_in_leaf != 1:
        raise ValueError('SymmetricTree does not support a non-default leaf threshold')
    if not math.isfinite(args.l2_leaf_reg) or args.l2_leaf_reg <= 0:
        raise ValueError('L2 leaf regularization must be finite and positive')
