"""Grid serialization, parsing and augmentation for ARC tasks."""
from __future__ import annotations

import random

Grid = list[list[int]]


def to_text(g: Grid) -> str:
    return "\n".join("".join(str(v) for v in row) for row in g)


def parse_grid(text: str) -> Grid | None:
    rows: list[list[int]] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            if rows:
                break
            continue
        if not all(ch.isdigit() for ch in line):
            break
        rows.append([int(ch) for ch in line])
        if len(rows) > 30:
            return None
    if not rows or any(len(r) != len(rows[0]) or len(r) > 30 for r in rows):
        return None
    return rows


def transpose(g: Grid) -> Grid:
    return [list(r) for r in zip(*g)]


def rot90(g: Grid) -> Grid:
    return [list(r) for r in zip(*g[::-1])]


def flip_h(g: Grid) -> Grid:
    return [r[::-1] for r in g]


def apply_perm(g: Grid, perm: list[int]) -> Grid:
    return [[perm[v] for v in r] for r in g]


def random_augmentation(rng: random.Random):
    """Returns (f, f_inv) acting on grids: a dihedral transform plus a color permutation that keeps 0 fixed."""
    k = rng.randrange(4)
    flip = rng.random() < 0.5
    perm = list(range(10))
    tail = perm[1:]
    rng.shuffle(tail)
    perm = [0] + tail
    inv = [0] * 10
    for i, p in enumerate(perm):
        inv[p] = i

    def f(g: Grid) -> Grid:
        for _ in range(k):
            g = rot90(g)
        if flip:
            g = flip_h(g)
        return apply_perm(g, perm)

    def f_inv(g: Grid) -> Grid:
        g = apply_perm(g, inv)
        if flip:
            g = flip_h(g)
        for _ in range((4 - k) % 4):
            g = rot90(g)
        return g

    return f, f_inv


def task_prompt(pairs: list[dict], test_input: Grid) -> str:
    parts = []
    for i, p in enumerate(pairs):
        parts.append(f"Example {i + 1}\nInput:\n{to_text(p['input'])}\nOutput:\n{to_text(p['output'])}\n")
    parts.append(f"Test\nInput:\n{to_text(test_input)}\nOutput:\n")
    return "\n".join(parts)
