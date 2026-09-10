"""Starter trainer: one-hidden-layer MLP trained with plain SGD until the budget runs out. Checkpoints every epoch."""
from __future__ import annotations

import time
import tomllib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    with open(ROOT / "config.toml", "rb") as f:
        return tomllib.load(f)


def init(d: int, hidden: int, seed: int):
    rng = np.random.RandomState(seed)
    return {"w1": rng.randn(d, hidden) * 0.3, "b1": np.zeros(hidden), "w2": rng.randn(hidden) * 0.3, "b2": 0.0}


def forward(p, x):
    h = np.tanh(x @ p["w1"] + p["b1"])
    return h @ p["w2"] + p["b2"], h


def train(budget_s: float, run_dir: str, resume: bool, data: dict, report) -> np.ndarray:
    cfg = load_config()
    ckpt = Path(run_dir) / "ckpt.npz"
    x, y = data["x_train"], data["y_train"]
    rng = np.random.RandomState(cfg.get("seed", 0))
    p = init(x.shape[1], int(cfg.get("hidden", 32)), int(cfg.get("seed", 0)))
    epoch, used = 0, 0.0
    if resume and ckpt.exists():
        z = np.load(ckpt)
        p = {k: z[k] for k in ("w1", "b1", "w2")}
        p["b2"] = float(z["b2"])
        epoch, used = int(z["epoch"]), float(z["used"])
    lr, bs = float(cfg.get("lr", 0.01)), int(cfg.get("batch", 64))
    t0 = time.time()
    while used + (time.time() - t0) < budget_s:
        idx = rng.permutation(len(x))
        for i in range(0, len(x), bs):
            b = idx[i:i + bs]
            out, h = forward(p, x[b])
            g = (out - y[b]) / len(b)
            gw2 = h.T @ g
            gh = np.outer(g, p["w2"]) * (1 - h * h)
            p["w2"] -= lr * gw2
            p["b2"] -= lr * g.sum()
            p["w1"] -= lr * x[b].T @ gh
            p["b1"] -= lr * gh.sum(axis=0)
        epoch += 1
        report(epoch, forward(p, data["x_val"])[0])
        np.savez(ckpt, epoch=epoch, used=used + (time.time() - t0), **p)
    return forward(p, data["x_test"])[0]
