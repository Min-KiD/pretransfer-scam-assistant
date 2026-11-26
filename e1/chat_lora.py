"""E13 part B: LoRA fine-tune of the text-only chat model Qwen3-4B-Instruct-2507 on the T5 teacher turns
(data/T5/train.jsonl, val.jsonl; never sim/cases or sim/cases_v2). Runs on the server in .venv-e4 (torch,
transformers, peft); `check` needs only the tokenizer (CPU).

  python -m e1.chat_lora check [--base Qwen/Qwen3-4B-Instruct-2507]
  python -m e1.chat_lora train --rank 16 --epochs 1 --out .cache/e13/lora/runA [--no-grad-ckpt] [--gate-steps 0]
  python -m e1.chat_lora train --rank 16 --out /tmp/x --no-grad-ckpt --max-steps 2   # speed/memory test, no save

Every example is what sim.e5 sends to `vllm serve` (core.llm, provider "local"): no system message, one user turn
whose text is the row's `tu_do` prompt, rendered by the model's own chat template with add_generation_prompt=True
and chat_template_kwargs {"enable_thinking": false} (the same kwargs core.llm sends). The answer is the row's
assistant JSON exactly as the teacher wrote it (compact `{"du_doan","cau_hoi"}`), followed by <|im_end|>. Prompt and
answer are tokenized separately and concatenated, so training and generation split at the same boundary. Loss on the
answer tokens only; logits are computed only for the answer span (logits_to_keep). No truncation: a row longer than
--max-len stops the run.

Fixed by the brief: LoRA on q,k,v,o,gate,up,down, alpha = rank, dropout 0, bf16 base (frozen), fp32 adapters
(saved bf16), AdamW lr 2e-4, weight decay 0.01, linear warmup 5% then linear decay to 0 over the run's epochs,
batch 1 x 16 accumulation, seed 3407, a checkpoint and a validation loss (all val rows, token-weighted) after each
epoch. Gradient checkpointing on by default (--no-grad-ckpt turns it off). --max-steps N stops after N optimiser
steps and prints a TEST line (s/step, peak VRAM), saving nothing. Timing gate (--gate-steps 0 turns it off): after
--gate-steps optimiser steps the projected run time (steps + val passes) is printed as a GATE line; above
--gate-hours the run stops (exit 3) before going on.

Outputs in --out: log.jsonl (one train row per optimiser step, one val row per epoch), epoch-<k>/ (peft
save_pretrained, loadable by `vllm serve <base> --enable-lora --lora-modules <name>=<out>/epoch-<k>`), meta.json
(hyperparameters, base revision, data hash, longest row, trainable parameters, per-epoch train/val loss, minutes,
adapter size, peak VRAM, best epoch by val loss, finished). Not resumable: `train` starts over.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

from e1.open_models import snapshot

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/T5"
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
TMPL_KWARGS = {"enable_thinking": False}  # what core.llm sends to the local server
IGNORE = -100


def rows(split: str) -> list[dict]:
    return [json.loads(l) for l in open(DATA / f"{split}.jsonl", encoding="utf-8")]


def resolve(base: str) -> Path:
    p = Path(base)
    return p if p.is_dir() else snapshot(base, download=False)


class Builder:
    def __init__(self, tok):
        self.tok = tok
        self.eot = "<|im_end|>"
        assert self.eot in tok.get_vocab()

    def prompt(self, row) -> str:
        user = row["messages"][0]
        assert user["role"] == "user" and row["messages"][1]["role"] == "assistant"
        return self.tok.apply_chat_template([{"role": "user", "content": user["content"]}], tokenize=False,
                                            add_generation_prompt=True, **TMPL_KWARGS)

    def __call__(self, row) -> dict:
        import torch
        p = self.tok(self.prompt(row), add_special_tokens=False)["input_ids"]
        a = self.tok(row["messages"][1]["content"] + self.eot, add_special_tokens=False)["input_ids"]
        ids = torch.tensor(p + a)
        labels = torch.full_like(ids, IGNORE)
        labels[len(p):] = ids[len(p):]
        return {"input_ids": ids[None], "labels": labels[None], "prompt_len": len(p)}


def data_hash() -> str:
    h = hashlib.sha256()
    for split in ("train", "val"):
        h.update((DATA / f"{split}.jsonl").read_bytes())
    return h.hexdigest()


def lengths(tok, rs) -> list[tuple[int, int]]:
    b = Builder(tok)
    out = []
    for r in rs:
        p = len(tok(b.prompt(r), add_special_tokens=False)["input_ids"])
        a = len(tok(r["messages"][1]["content"] + b.eot, add_special_tokens=False)["input_ids"])
        out.append((p, a))
    return out


def cmd_check(a):
    from transformers import AutoTokenizer
    base = resolve(a.base)
    tok = AutoTokenizer.from_pretrained(base, local_files_only=True)
    b = Builder(tok)
    tr, va = rows("train"), rows("val")
    print("template tail:", repr(b.prompt(tr[0])[-80:]))
    for name, rs in (("train", tr), ("val", va)):
        ls = lengths(tok, rs)
        tot = [p + x for p, x in ls]
        print(json.dumps({"split": name, "rows": len(rs), "longest_total": max(tot), "longest_prompt": max(p for p, _ in ls),
                          "longest_answer": max(x for _, x in ls), "mean_total": round(sum(tot) / len(tot)),
                          "answer_tokens": sum(x for _, x in ls)}))


def cmd_train(a):
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    t_start = time.time()
    random.seed(a.seed)
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = resolve(a.base)
    tok = AutoTokenizer.from_pretrained(base, local_files_only=True)
    build = Builder(tok)
    train_rows, val_rows = rows("train"), rows("val")
    ls = lengths(tok, train_rows + val_rows)
    longest = max(p + x for p, x in ls)
    if longest > a.max_len:
        raise SystemExit(f"STOPPED: longest row {longest} tokens > --max-len {a.max_len} (no truncation)")

    model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.bfloat16, local_files_only=True,
                                                 attn_implementation="sdpa").cuda()
    model.config.use_cache = False
    for p in model.parameters():
        p.requires_grad_(False)
    if a.grad_ckpt:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
    cfg = LoraConfig(r=a.rank, lora_alpha=a.rank, lora_dropout=0.0, target_modules=TARGET_MODULES, bias="none",
                     task_type="CAUSAL_LM")
    model = get_peft_model(model, cfg)
    for p in model.parameters():  # fp32 adapters on a bf16 base
        if p.requires_grad:
            p.data = p.data.float()
    params = [p for p in model.parameters() if p.requires_grad]
    n_trainable = sum(p.numel() for p in params)
    print(f"trainable {n_trainable / 1e6:.2f}M params in {len(params)} tensors; longest row {longest} tokens", flush=True)

    steps_per_epoch = math.ceil(len(train_rows) / a.grad_accum)
    total = steps_per_epoch * a.epochs
    warm = max(1, round(a.warmup * total))
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=a.weight_decay)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warm if s < warm else max(0.0, (total - s) / max(1, total - warm)))

    def loss_of(ex, reduction="mean"):
        ids, labels = ex["input_ids"].cuda(), ex["labels"].cuda()
        L = ids.shape[1]
        keep = L - ex["prompt_len"] + 1  # logits for positions prompt_len-1 .. L-1
        o = model(input_ids=ids, logits_to_keep=keep)
        logits = o.logits[:, :-1].float()
        tgt = labels[:, L - keep + 1:]
        return torch.nn.functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), tgt.reshape(-1),
                                                 ignore_index=IGNORE, reduction=reduction), int((tgt != IGNORE).sum())

    @torch.no_grad()
    def val_loss():
        model.eval()
        tot, n = 0.0, 0
        for r in val_rows:
            l, k = loss_of(build(r), reduction="sum")
            tot, n = tot + l.item(), n + k
        model.train()
        return tot / n

    import peft
    import transformers
    log = open(out / "log.jsonl", "w", encoding="utf-8")
    meta = {"base": a.base, "base_path": str(base), "revision": base.name, "run": out.name,
            "train_rows": len(train_rows), "val_rows": len(val_rows), "data_hash": data_hash(),
            "longest_row_tokens": longest, "max_len": a.max_len, "rank": a.rank, "alpha": a.rank, "dropout": 0.0,
            "lr": a.lr, "weight_decay": a.weight_decay, "warmup": a.warmup, "schedule": "linear warmup + linear decay",
            "epochs": a.epochs, "batch": 1, "grad_accum": a.grad_accum, "steps": total,
            "steps_per_epoch": steps_per_epoch, "seed": a.seed, "target_modules": TARGET_MODULES,
            "trainable_params": n_trainable, "dtype": "bf16 base, fp32 adapters (saved bf16)",
            "gradient_checkpointing": a.grad_ckpt,
            "versions": f"torch {torch.__version__}, transformers {transformers.__version__}, peft {peft.__version__}",
            "epochs_done": [], "finished": False}

    def write_meta(step):
        meta.update(wall_s=round(time.time() - t_start), last_step=step,
                    peak_vram_mib=round(torch.cuda.max_memory_allocated() / 2**20),
                    peak_reserved_mib=round(torch.cuda.max_memory_reserved() / 2**20))
        done = meta["epochs_done"]
        meta["best_epoch_by_val_loss"] = min(done, key=lambda e: e["val_loss"])["epoch"] if done else None
        (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")

    def save(epoch) -> float:
        d = out / f"epoch-{epoch}"
        model.save_pretrained(d)
        from safetensors.torch import load_file, save_file
        f = d / "adapter_model.safetensors"
        save_file({k: v.to(torch.bfloat16) for k, v in load_file(f).items()}, f, metadata={"format": "pt"})
        return round(sum(p.stat().st_size for p in d.iterdir()) / 1e6, 1)

    def emit(row):
        log.write(json.dumps(row) + "\n")
        log.flush()
        print(json.dumps(row), flush=True)

    model.train()
    step, t0, acc_loss, acc_n = 0, time.time(), 0.0, 0
    for epoch in range(1, a.epochs + 1):
        te, ep_losses = time.time(), []
        order = train_rows[:]
        random.Random(a.seed + epoch).shuffle(order)
        for i, r in enumerate(order):
            loss, _ = loss_of(build(r))
            (loss / a.grad_accum).backward()
            acc_loss, acc_n = acc_loss + loss.item(), acc_n + 1
            if (i + 1) % a.grad_accum and i != len(order) - 1:
                continue
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            ep_losses.append(acc_loss / acc_n)
            emit({"step": step, "epoch": epoch, "loss": round(acc_loss / acc_n, 5), "lr": sched.get_last_lr()[0],
                  "seconds": round(time.time() - t0, 1), "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20)})
            acc_loss, acc_n = 0.0, 0
            if step == a.max_steps:
                test = {"steps": step, "grad_ckpt": a.grad_ckpt, "s_per_step": round((time.time() - t0) / step, 1),
                        "projected_hours_per_epoch": round((time.time() - t0) / step * steps_per_epoch / 3600, 2),
                        "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20),
                        "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20)}
                print("TEST " + json.dumps(test), flush=True)
                return
            if a.gate_steps and step == a.gate_steps:
                s_step = (time.time() - t0) / step
                proj_h = (s_step * total + a.epochs * len(val_rows) * s_step / a.grad_accum / 2) / 3600
                gate = {"gate_steps": step, "s_per_step": round(s_step, 1), "projected_hours": round(proj_h, 2),
                        "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20),
                        "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20)}
                meta["gate"] = gate
                write_meta(step)
                print("GATE " + json.dumps(gate), flush=True)
                if proj_h > a.gate_hours:
                    print(f"STOPPED at the timing gate: {proj_h:.1f} h > {a.gate_hours} h", flush=True)
                    sys.exit(3)
        train_min = (time.time() - te) / 60
        tv = time.time()
        vl = val_loss()
        size = save(epoch)
        meta["epochs_done"].append({"epoch": epoch, "step": step, "train_loss": round(sum(ep_losses) / len(ep_losses), 5),
                                    "val_loss": round(vl, 5), "train_minutes": round(train_min, 1),
                                    "val_minutes": round((time.time() - tv) / 60, 1), "adapter_mb": size,
                                    "path": f"epoch-{epoch}"})
        emit({"epoch": epoch, "step": step, "val_loss": round(vl, 5), "seconds": round(time.time() - t0, 1)})
        meta["finished"] = epoch == a.epochs
        write_meta(step)
    log.close()
    print("DONE " + json.dumps({k: meta[k] for k in ("run", "steps", "wall_s", "peak_vram_mib",
                                                     "best_epoch_by_val_loss")}), flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "train"):
        p = sub.add_parser(name)
        p.add_argument("--base", default="Qwen/Qwen3-4B-Instruct-2507", help="HF repo id (offline snapshot) or a dir")
    t = sub.choices["train"]
    t.add_argument("--out", required=True)
    t.add_argument("--rank", type=int, required=True)
    t.add_argument("--lr", type=float, default=2e-4)
    t.add_argument("--weight-decay", type=float, default=0.01)
    t.add_argument("--warmup", type=float, default=0.05, help="fraction of steps")
    t.add_argument("--epochs", type=int, default=3)
    t.add_argument("--grad-accum", type=int, default=16)
    t.add_argument("--seed", type=int, default=3407)
    t.add_argument("--max-len", type=int, default=8192, help="no truncation: a longer row stops the run")
    t.add_argument("--gate-steps", type=int, default=50)
    t.add_argument("--gate-hours", type=float, default=8.0)
    t.add_argument("--grad-ckpt", action=argparse.BooleanOptionalAction, default=True)
    t.add_argument("--max-steps", type=int, default=0, help="test: stop after N optimiser steps, save nothing")
    a = ap.parse_args()
    {"check": cmd_check, "train": cmd_train}[a.cmd](a)


if __name__ == "__main__":
    main()
