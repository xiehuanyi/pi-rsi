# Trainer contract

```python
def train(budget_s: float, run_dir: str, resume: bool, data: dict, report) -> "np.ndarray":
    """Train within budget_s seconds of wall-clock.
    data: {"x_train","y_train","x_val","y_val","x_test"} numpy arrays.
    report(step: int, val_predictions: np.ndarray) -> None   # call once per epoch; the wrapper scores and logs it
    Return predictions for data["x_test"] (shape [n_test]).
    Checkpoint into run_dir; when resume is True and a checkpoint exists, continue from it (the elapsed budget is
    also restored by the wrapper through the checkpoint's own bookkeeping)."""
```
Configuration goes in `config.toml` (read by your trainer). Keep the trainer deterministic (seed everything).
