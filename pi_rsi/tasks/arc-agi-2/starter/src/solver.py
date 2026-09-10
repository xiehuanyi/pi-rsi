"""Starter ARC-AGI-2 solver: LoRA fine-tune a small causal LM on the public training tasks (text-serialized grids,
random dihedral/color augmentation) within the training budget, then decode two attempts per test input
(attempt 1: plain greedy; attempt 2: greedy on the transposed task, mapped back). Invalid outputs fall back to the
test input itself.

Contract (do not change the signature):
    solve(train_tasks, eval_tasks, budget_s, run_dir, resume, report, infer_budget_s) -> {task_id: [[attempt1, attempt2], ...]}
"""
from __future__ import annotations

import json
import random
import time
import tomllib
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

from src.grids import task_prompt, parse_grid, random_augmentation, transpose, to_text

ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    with open(ROOT / "config.toml", "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------- data
def build_examples(train_tasks: dict, rng: random.Random, augment: bool):
    """One example per (task, held-out pair): context = the other pairs, target = the held-out output."""
    examples = []
    for tid, task in train_tasks.items():
        pairs = task["train"] + task["test"]
        if len(pairs) < 2:
            continue
        for i in range(len(pairs)):
            ctx = [p for j, p in enumerate(pairs) if j != i]
            tgt = pairs[i]
            if augment:
                f, _ = random_augmentation(rng)
                ctx = [{"input": f(p["input"]), "output": f(p["output"])} for p in ctx]
                tgt = {"input": f(tgt["input"]), "output": f(tgt["output"])}
            examples.append((task_prompt(ctx, tgt["input"]), to_text(tgt["output"]) + "\n"))
    rng.shuffle(examples)
    return examples


def encode(tok, prompt: str, target: str, max_len: int):
    p = tok(prompt, add_special_tokens=False)["input_ids"]
    t = tok(target, add_special_tokens=False)["input_ids"] + [tok.eos_token_id]
    if len(p) + len(t) > max_len:
        return None
    ids = p + t
    labels = [-100] * len(p) + t
    return torch.tensor(ids), torch.tensor(labels)


# ---------------------------------------------------------------- training
def train(model, tok, examples, cfg, budget_s, run_dir: Path, resume: bool, report):
    ckpt = run_dir / "adapter"
    state_path = run_dir / "train_state.json"
    step, used = 0, 0.0
    if resume and ckpt.exists() and state_path.exists():
        st = json.loads(state_path.read_text())
        step, used = st["step"], st["used_s"]
        model.load_adapter(str(ckpt), adapter_name="default", is_trainable=True)
    model.train()
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=float(cfg["lr"]), weight_decay=0.0)
    accum = int(cfg["grad_accum"])
    t0 = time.time()
    i, micro, loss_acc = step * accum, 0, 0.0
    n = len(examples)
    while used + (time.time() - t0) < budget_s and n:
        prompt, target = examples[i % n]
        i += 1
        enc = encode(tok, prompt, target, int(cfg["max_train_tokens"]))
        if enc is None:
            continue
        ids, labels = enc
        out = model(input_ids=ids[None].cuda(), labels=labels[None].cuda())
        (out.loss / accum).backward()
        loss_acc += out.loss.item()
        micro += 1
        if micro == accum:
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            micro = 0
            if step % 10 == 0:
                report(step, loss_acc / accum / 10, phase="train")
                loss_acc = 0.0
            if step % 50 == 0:
                model.save_pretrained(str(ckpt))
                state_path.write_text(json.dumps({"step": step, "used_s": used + (time.time() - t0)}))
    model.save_pretrained(str(ckpt))
    state_path.write_text(json.dumps({"step": step, "used_s": used + (time.time() - t0)}))
    model.eval()
    return step


# ---------------------------------------------------------------- inference
def trim_prompt(tok, pairs, test_input, max_tokens: int) -> str:
    pairs = list(pairs)
    while True:
        prompt = task_prompt(pairs, test_input)
        if len(tok(prompt, add_special_tokens=False)["input_ids"]) <= max_tokens or len(pairs) <= 1:
            return prompt
        pairs = pairs[:-1]


@torch.no_grad()
def generate_batch(model, tok, prompts: list[str], max_new: int) -> list[str]:
    tok.padding_side = "left"
    enc = tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
    out = model.generate(**enc, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.pad_token_id or tok.eos_token_id)
    gen = out[:, enc["input_ids"].shape[1]:]
    return tok.batch_decode(gen, skip_special_tokens=True)


def infer(model, tok, eval_tasks: dict, cfg, infer_budget_s: float, report):
    max_prompt, max_new, batch_tokens = int(cfg["max_prompt_tokens"]), int(cfg["max_new_tokens"]), int(cfg["gen_batch_tokens"])
    queries = []  # (task_id, test_idx, attempt, prompt, inverse)
    for tid, task in eval_tasks.items():
        for ti, t in enumerate(task["test"]):
            queries.append((tid, ti, 0, trim_prompt(tok, task["train"], t["input"], max_prompt), None))
            tp = [{"input": transpose(p["input"]), "output": transpose(p["output"])} for p in task["train"]]
            queries.append((tid, ti, 1, trim_prompt(tok, tp, transpose(t["input"]), max_prompt), transpose))
    lengths = {q[3]: len(tok(q[3], add_special_tokens=False)["input_ids"]) for q in queries}
    queries.sort(key=lambda q: lengths[q[3]])
    results: dict[tuple, str] = {}
    t0 = time.time()
    i = 0
    while i < len(queries):
        if time.time() - t0 > infer_budget_s:
            break
        batch, tot = [], 0
        while i < len(queries) and (not batch or tot + lengths[queries[i][3]] + max_new <= batch_tokens):
            batch.append(queries[i])
            tot += lengths[queries[i][3]] + max_new
            i += 1
        try:
            texts = generate_batch(model, tok, [q[3] for q in batch], max_new)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            texts = [""] * len(batch)
        for q, txt in zip(batch, texts):
            results[(q[0], q[1], q[2])] = txt
        report(1000000 + i, (time.time() - t0), phase="infer")
    preds = {}
    for tid, task in eval_tasks.items():
        preds[tid] = []
        for ti, t in enumerate(task["test"]):
            attempts = []
            for att in (0, 1):
                g = parse_grid(results.get((tid, ti, att), ""))
                if g is not None and att == 1:
                    g = transpose(g)
                attempts.append(g if g is not None else t["input"])
            preds[tid].append(attempts)
    return preds


def solve(train_tasks, eval_tasks, budget_s, run_dir, resume, report, infer_budget_s=600):
    cfg = load_config()
    rng = random.Random(int(cfg.get("seed", 0)))
    torch.manual_seed(int(cfg.get("seed", 0)))
    run_dir = Path(run_dir)
    tok = AutoTokenizer.from_pretrained(ROOT / cfg["model"])
    model = AutoModelForCausalLM.from_pretrained(ROOT / cfg["model"], dtype=torch.bfloat16).cuda()
    if not (resume and (run_dir / "adapter").exists()):
        lcfg = LoraConfig(r=int(cfg["lora_r"]), lora_alpha=int(cfg["lora_alpha"]), lora_dropout=0.0, bias="none", task_type="CAUSAL_LM",
                          target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
        model = get_peft_model(model, lcfg)
    else:
        model = PeftModel.from_pretrained(model, str(run_dir / "adapter"), is_trainable=True)
    examples = build_examples(train_tasks, rng, bool(cfg.get("augment", True)))
    steps = train(model, tok, examples, cfg, budget_s, run_dir, resume and (run_dir / "adapter").exists(), report)
    model.gradient_checkpointing_disable()
    return infer(model, tok, eval_tasks, cfg, infer_budget_s, report)
