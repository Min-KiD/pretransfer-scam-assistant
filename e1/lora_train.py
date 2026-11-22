"""E4 phase B: LoRA fine-tune of an open VLM (Qwen3-VL-4B/2B, Qwen3.5-4B) to read a chat screenshot into
e1.vlm.SCHEMA JSON. Runs on the server in .venv-e4 (torch, transformers 5, peft); `check` needs no weights and no GPU.

  python -m e1.lora_train check --base Qwen/Qwen3-VL-4B-Instruct [--ocr] [--n 4]
  python -m e1.lora_train train --base Qwen/Qwen3-VL-4B-Instruct --out .cache/e4/lora/B1 [--n-train N] [--ocr]
      [--rank 16 --alpha 32 --lr 1e-4 --epochs 1 --batch 1 --grad-accum 8 --max-pixels 2097152 --seed 20261125
       --eval-every 250 --save-every 250]

--base is a HF repo id (resolved offline with e1.open_models.snapshot) or a local snapshot dir.

Every example is exactly what phase-A J mode sends to `vllm serve` (e1.e4_run -> core.llm._generate_openai, provider
"local"): no system message, one user turn whose content is [image, text], text = e1.vlm.PROMPT, rendered by the
model's own chat template with add_generation_prompt=True and enable_thinking=False; the image goes through the HF
processor with size.longest_edge = max_pixels (what vLLM does with --mm-processor-kwargs {"max_pixels": ...}).
The answer is json.dumps(target, ensure_ascii=False) (one line, ", " and ": " separators; vLLM's JSON-schema guided
decoding accepts any whitespace, so the model's learned style passes the grammar) followed by the end-of-turn token.
Prompt and answer are tokenized separately and concatenated: generation in vLLM starts at the same boundary.
Loss is on the answer tokens only (prompt, image tokens: label -100).

--ocr (run B3): the user text is PROMPT + PROMPT_OCR with the PP-OCRv6 lines formatted by e1.e4_run.ocr_text
("[x=<left>-<right>] <text>", positions as a fraction of image width), see user_text(). The B3 inference must build the
same text: import user_text from here. OCR comes from data/E4/<split>/runs/T__pp-ocrv6-gpu/<id>.json.

LoRA: q,k,v,o,gate,up,down of the language model only (Qwen3-VL's vision tower and merger use other module names; the
script asserts no adapter lands outside language_model). bf16 weights, fp32 adapters while training (saved as bf16,
~66 MB per checkpoint for the 4B at r16), gradient checkpointing, AdamW, linear warmup 3% then cosine. Logits are
computed only for the answer span (logits_to_keep), which keeps the 151k-vocab logits small.

Outputs in --out: log.jsonl (train rows every optimizer step, val rows every --eval-every steps and at the end),
ckpt-<step>/ (peft save_pretrained: adapter_config.json + adapter_model.safetensors, loadable by
`vllm serve <base> --enable-lora --lora-modules <name>=<out>/ckpt-<step>`), meta.json (hyperparameters, base
repo/revision, data hash, wall time, peak VRAM, val loss per checkpoint, best step by val loss, finished).
A run is not resumable: `train` starts over (log.jsonl rewritten); scripts/e4_phaseB.sh skips finished runs.

  python -m e1.lora_train pick --run B1
Checkpoint choice, rule fixed before any score existed: highest string match pooled over val + web-dev (odd web ids)
of the e4_run configs <J|JO>__<run>-<step>; tie -> fewer made-up strings ("chuỗi bịa", e1.score_e1b.fabricated);
tie -> earlier step. Reads only data/E4/val and the web-dev half of web. Writes <out>/pick.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from pathlib import Path

from e1.vlm import PROMPT, PROMPT_OCR

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/E4"
OCR_RUN = "T__pp-ocrv6-gpu"  # data/E4/<split>/runs/T__pp-ocrv6-gpu/<id>.json: {"lines": [{"text", "box"}]}
VAL_N = 100  # fixed val subset for val loss
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
IGNORE = -100


# ---------------------------------------------------------------- data
def resolve_base(base: str, need_weights: bool = True) -> Path:
    """Local snapshot dir of --base. `check` only needs the processor files, so it also accepts a snapshot whose
    weights are still downloading (e1.open_models.snapshot refuses an incomplete one)."""
    p = Path(base)
    if p.is_dir():
        return p
    if not need_weights:
        from huggingface_hub import try_to_load_from_cache
        cfg = try_to_load_from_cache(base, "preprocessor_config.json")
        if isinstance(cfg, str):
            return Path(cfg).parent
    from e1.open_models import snapshot
    return snapshot(base, download=False)


def items(split: str) -> list[dict]:
    d = DATA / split
    return [json.loads(l) for l in open(d / "manifest.jsonl", encoding="utf-8")]


def subset(rows: list[dict], n: int | None, seed: int) -> list[dict]:
    """First n of a seeded shuffle (nested: the 500 set is inside the 2000 set, inside the full set)."""
    rows = list(rows)
    random.Random(seed).shuffle(rows)
    return rows[:n] if n else rows


def ocr_path(split: str, image_id: str) -> Path:
    return DATA / split / "runs" / OCR_RUN / f"{image_id}.json"


def require_ocr(split: str, rows: list[dict]):
    missing = [r["image_id"] for r in rows if not ocr_path(split, r["image_id"]).exists()]
    if missing:
        raise SystemExit(f"--ocr: {len(missing)}/{len(rows)} {split} images have no PP-OCRv6 text in "
                         f"{DATA / split / 'runs' / OCR_RUN}/ (first: {missing[:3]}). Write PP-OCRv6 GPU output "
                         f'({{"lines": [{{"text", "box": [x0, y0, x1, y1]}}]}}) for data/E4/{split} there first '
                         "(e1.open_models SET_DIRS has no E4 sets yet).")


def user_text(lines: list[dict] | None, width: int | None) -> str:
    """The user text of one request: PROMPT (J mode), plus the OCR block for B3."""
    if lines is None:
        return PROMPT
    from e1.e4_run import ocr_text
    return PROMPT + PROMPT_OCR.format(ocr=ocr_text(lines, width))


def messages_for(text: str) -> list[dict]:
    # core.llm sends [{"role": "user", "content": [{"type": "image_url", ...}, {"type": "text", "text": ...}]}];
    # vLLM hands the chat template {"type": "image"} for the image part.
    return [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": text}]}]


def answer_text(target: dict) -> str:
    return json.dumps(target, ensure_ascii=False)


class Builder:
    """One training example (input_ids, labels, pixel_values, image_grid_thw) per manifest row."""

    def __init__(self, processor, split: str, max_pixels: int, ocr: bool):
        self.p, self.split, self.ocr = processor, split, ocr
        tok = processor.tokenizer
        size = dict(processor.image_processor.size)
        size["longest_edge"] = max_pixels
        self.size = size
        # end of the assistant turn as rendered by the template (Qwen: <|im_end|>); generation stops on it
        self.eot = "<|im_end|>" if "<|im_end|>" in tok.get_vocab() else tok.eos_token
        self.image_token_id = tok.convert_tokens_to_ids(getattr(processor, "image_token", "<|image_pad|>"))
        # vLLM gets chat_template_kwargs {"enable_thinking": false}; only templates that read it (Qwen3.5) see it
        self.tmpl_kwargs = {"enable_thinking": False} if "enable_thinking" in (processor.chat_template or "") else {}

    def __call__(self, row: dict) -> dict:
        from PIL import Image
        d = DATA / self.split
        img = Image.open(d / row["path"]).convert("RGB")
        lines = None
        if self.ocr:
            lines = json.loads(ocr_path(self.split, row["image_id"]).read_text(encoding="utf-8")).get("lines", [])
        prompt = self.p.apply_chat_template(messages_for(user_text(lines, img.size[0] if lines is not None else None)),
                                            tokenize=False, add_generation_prompt=True, **self.tmpl_kwargs)
        enc = self.p(text=[prompt], images=[img], images_kwargs={"size": self.size}, return_tensors="pt")
        target = json.loads((d / row["target"]).read_text(encoding="utf-8"))
        ans = self.p.tokenizer(answer_text(target) + self.eot, add_special_tokens=False)["input_ids"]
        import torch
        pids = enc["input_ids"][0]
        ids = torch.cat([pids, torch.tensor(ans, dtype=pids.dtype)])
        labels = torch.full_like(ids, IGNORE)
        labels[len(pids):] = ids[len(pids):]
        return {"image_id": row["image_id"], "input_ids": ids, "labels": labels, "prompt_len": len(pids),
                "pixel_values": enc["pixel_values"], "image_grid_thw": enc["image_grid_thw"], "image_size": img.size,
                "answer": answer_text(target) + self.eot}


def collate(batch: list[dict], pad_id: int) -> dict:
    import torch
    n = max(len(b["input_ids"]) for b in batch)
    ids = torch.full((len(batch), n), pad_id, dtype=batch[0]["input_ids"].dtype)
    labels = torch.full((len(batch), n), IGNORE, dtype=torch.long)
    att = torch.zeros((len(batch), n), dtype=torch.long)
    for i, b in enumerate(batch):  # right padding
        k = len(b["input_ids"])
        ids[i, :k], labels[i, :k], att[i, :k] = b["input_ids"], b["labels"], 1
    return {"input_ids": ids, "labels": labels, "attention_mask": att,
            "pixel_values": torch.cat([b["pixel_values"] for b in batch]),
            "image_grid_thw": torch.cat([b["image_grid_thw"] for b in batch]),
            "min_prompt_len": min(b["prompt_len"] for b in batch)}


def data_hash(split_rows: dict[str, list[dict]], ocr: bool) -> str:
    """sha256 over the ids, image bytes, target bytes (and OCR bytes with --ocr) actually used, in order."""
    h = hashlib.sha256()
    for split, rows in split_rows.items():
        for r in rows:
            d = DATA / split
            h.update(f"{split}/{r['image_id']}".encode())
            h.update((d / r["path"]).read_bytes())
            h.update((d / r["target"]).read_bytes())
            if ocr:
                h.update(ocr_path(split, r["image_id"]).read_bytes())
    return h.hexdigest()


def load_processor(base: Path):
    from transformers import AutoProcessor
    return AutoProcessor.from_pretrained(base, local_files_only=True)


# ---------------------------------------------------------------- check (CPU, processor only)
def cmd_check(a):
    from qwen_vl_utils import smart_resize
    from PIL import Image
    base = resolve_base(a.base, need_weights=False)
    proc = load_processor(base)
    b = Builder(proc, a.split, a.max_pixels, a.ocr)
    rows = subset(items(a.split), None, a.seed)[:a.n]
    if a.ocr:
        require_ocr(a.split, rows)
    tok = proc.tokenizer
    ps, ms = proc.image_processor.patch_size, proc.image_processor.merge_size
    print(f"base {base} | max_pixels {a.max_pixels} | image size kwargs {b.size} | eot {b.eot!r}")
    ok = True
    for i, row in enumerate(rows):
        ex = b(row)
        ids, labels = ex["input_ids"], ex["labels"]
        sup = labels != IGNORE
        n_img = int((ids == b.image_token_id).sum())
        decoded = tok.decode(ids[sup], skip_special_tokens=False)
        same = decoded == ex["answer"]
        img_masked = bool((labels[ids == b.image_token_id] == IGNORE).all())
        prefix_masked = bool((labels[:ex["prompt_len"]] == IGNORE).all()) and bool(sup[ex["prompt_len"]:].all())
        w, h = ex["image_size"]
        rh, rw = smart_resize(h, w, factor=ps * ms, min_pixels=b.size["shortest_edge"], max_pixels=a.max_pixels)
        t, gh, gw = ex["image_grid_thw"][0].tolist()
        grid_ok = (gh * ps, gw * ps) == (rh, rw) and n_img == t * gh * gw // (ms * ms)
        ok &= same and img_masked and prefix_masked and grid_ok
        print(f"\n[{i}] {row['image_id']} variant={row.get('variant')} style={row.get('style')} image {w}x{h} -> "
              f"grid {t}x{gh}x{gw} ({gw * ps}x{gh * ps}, qwen_vl_utils.smart_resize {rw}x{rh}: "
              f"{'match' if grid_ok else 'MISMATCH'})")
        print(f"    tokens total {len(ids)} | prompt {ex['prompt_len']} (image tokens {n_img}) | supervised "
              f"{int(sup.sum())} | image tokens masked {img_masked} | prompt masked {prefix_masked}")
        print(f"    supervised span == json.dumps(target) + eot: {same}")
        if i == 0:
            shown = tok.decode(ids[:ex["prompt_len"]], skip_special_tokens=False)
            shown = shown.replace("<|image_pad|>" * n_img, f"<|image_pad|>x{n_img}")
            print("    rendered prompt:\n" + "\n".join("      | " + l for l in shown.split("\n")))
        print("    supervised decoded: " + (decoded if len(decoded) < 400 else decoded[:200] + " ... " + decoded[-120:]))
    # a typical full-HD phone screenshot (1080x2400 = 2.6 MP) is scaled down to max_pixels
    for w, h in [(1080, 2400), (1440, 3200), (1170, 2532), (2048, 1024)]:
        img = Image.new("RGB", (w, h), "white")
        enc = proc(text=[proc.apply_chat_template(messages_for(PROMPT), tokenize=False, add_generation_prompt=True)],
                   images=[img], images_kwargs={"size": b.size}, return_tensors="pt")
        print(f"image {w}x{h} at max_pixels {a.max_pixels}: grid {enc['image_grid_thw'][0].tolist()}, "
              f"{int((enc['input_ids'] == b.image_token_id).sum())} image tokens")
    print("\nCHECK", "OK" if ok else "FAILED")
    if not ok:
        raise SystemExit(1)


# ---------------------------------------------------------------- train
def cmd_train(a):
    import torch
    from peft import LoraConfig, get_peft_model
    from torch.utils.data import DataLoader
    from transformers import AutoModelForImageTextToText

    t_start = time.time()
    random.seed(a.seed)
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = resolve_base(a.base)
    proc = load_processor(base)
    train_rows = subset(items("train"), a.n_train, a.seed)
    val_rows = sorted(random.Random(a.seed).sample(items("val"), VAL_N), key=lambda r: r["image_id"])
    if a.ocr:
        require_ocr("train", train_rows)
        require_ocr("val", val_rows)
    dhash = data_hash({"train": train_rows, "val": val_rows}, a.ocr)
    btrain, bval = Builder(proc, "train", a.max_pixels, a.ocr), Builder(proc, "val", a.max_pixels, a.ocr)
    pad_id = proc.tokenizer.pad_token_id if proc.tokenizer.pad_token_id is not None else proc.tokenizer.eos_token_id

    model = AutoModelForImageTextToText.from_pretrained(base, dtype=torch.bfloat16, local_files_only=True,
                                                        attn_implementation="sdpa").cuda()
    model.config.use_cache = False
    for p in model.parameters():
        p.requires_grad_(False)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    cfg = LoraConfig(r=a.rank, lora_alpha=a.alpha, lora_dropout=a.dropout, target_modules=TARGET_MODULES,
                     bias="none", task_type="CAUSAL_LM")
    model = get_peft_model(model, cfg)
    lora_names = [n for n, p in model.named_parameters() if p.requires_grad]
    outside = [n for n in lora_names if "language_model" not in n or "lora_" not in n]
    if outside:
        raise SystemExit(f"trainable parameters outside the language model's LoRA: {outside[:5]}")
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"trainable {n_trainable / 1e6:.1f}M params in {len(lora_names)} tensors", flush=True)

    steps_per_epoch = math.ceil(len(train_rows) / (a.batch * a.grad_accum))
    total = steps_per_epoch * a.epochs
    warm = max(1, round(a.warmup * total))
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total - warm))))

    def loss_of(batch, reduction="mean"):
        ids = batch["input_ids"].cuda()
        labels = batch["labels"].cuda()
        L = ids.shape[1]
        keep = L - batch["min_prompt_len"] + 1  # logits for positions min_prompt_len-1 .. L-1
        o = model(input_ids=ids, attention_mask=batch["attention_mask"].cuda(),
                  pixel_values=batch["pixel_values"].cuda().to(torch.bfloat16),
                  image_grid_thw=batch["image_grid_thw"].cuda(), logits_to_keep=keep)
        logits = o.logits[:, :-1].float()
        tgt = labels[:, L - keep + 1:]
        return torch.nn.functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), tgt.reshape(-1),
                                                 ignore_index=IGNORE, reduction=reduction), int((tgt != IGNORE).sum())

    @torch.no_grad()
    def val_loss():
        model.eval()
        tot, n = 0.0, 0
        for r in val_rows:
            l, k = loss_of(collate([bval(r)], pad_id), reduction="sum")
            tot, n = tot + l.item(), n + k
        model.train()
        return tot / n

    log = open(out / "log.jsonl", "w", encoding="utf-8")  # a run restarts from step 0
    meta = {"base": a.base, "base_path": str(base), "revision": base.name, "run": out.name, "mode": "J+ocr" if a.ocr
            else "J", "n_train": len(train_rows), "val_subset": VAL_N, "data_hash": dhash, "rank": a.rank,
            "alpha": a.alpha, "dropout": a.dropout, "lr": a.lr, "warmup": a.warmup, "schedule": "linear warmup + cosine",
            "epochs": a.epochs, "batch": a.batch, "grad_accum": a.grad_accum, "steps": total, "max_pixels": a.max_pixels,
            "seed": a.seed, "target_modules": TARGET_MODULES, "trainable_params": n_trainable, "dtype": "bf16 weights, "
            "fp32 adapters (saved bf16)", "answer_format": "json.dumps(target, ensure_ascii=False) + <|im_end|>",
            "versions": _versions(), "checkpoints": {}, "finished": False}

    def write_meta(step):
        meta.update(wall_s=round(time.time() - t_start), last_step=step,
                    peak_vram_mib=round(torch.cuda.max_memory_allocated() / 2**20),
                    peak_reserved_mib=round(torch.cuda.max_memory_reserved() / 2**20))
        ck = {s: v for s, v in meta["checkpoints"].items() if v.get("val_loss") is not None}
        meta["best_step_by_val_loss"] = min(ck, key=lambda s: ck[s]["val_loss"]) if ck else None
        (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")

    def save(step):
        d = out / f"ckpt-{step}"
        model.save_pretrained(d)
        # adapters train in fp32; vLLM casts them to the model dtype anyway, so store bf16 (half the disk)
        from safetensors.torch import load_file, save_file
        f = d / "adapter_model.safetensors"
        save_file({k: v.to(torch.bfloat16) for k, v in load_file(f).items()}, f, metadata={"format": "pt"})

    def emit(row):
        log.write(json.dumps(row) + "\n")
        log.flush()
        print(json.dumps(row), flush=True)

    model.train()
    step, t0, acc_loss, acc_n = 0, time.time(), 0.0, 0
    for epoch in range(a.epochs):
        order = subset(train_rows, None, a.seed + epoch)
        dl = DataLoader(order, batch_size=a.batch, shuffle=False, num_workers=2,
                        collate_fn=lambda rows: collate([btrain(r) for r in rows], pad_id))
        for i, batch in enumerate(dl):
            loss, _ = loss_of(batch)
            (loss / a.grad_accum).backward()
            acc_loss, acc_n = acc_loss + loss.item(), acc_n + 1
            last = i == len(dl) - 1
            if (i + 1) % a.grad_accum and not last:
                continue
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            emit({"step": step, "epoch": epoch, "loss": round(acc_loss / acc_n, 5), "lr": sched.get_last_lr()[0],
                  "seconds": round(time.time() - t0, 1),
                  "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20)})
            acc_loss, acc_n = 0.0, 0
            final = step == total
            vl = None
            if step % a.eval_every == 0 or final:
                vl = val_loss()
                emit({"step": step, "val_loss": round(vl, 5), "seconds": round(time.time() - t0, 1)})
            if step % a.save_every == 0 or final:
                save(step)
                meta["checkpoints"][str(step)] = {"path": f"ckpt-{step}", "val_loss": vl}
            meta["finished"] = final
            write_meta(step)
    log.close()
    print(json.dumps({k: meta[k] for k in ("run", "steps", "wall_s", "peak_vram_mib", "best_step_by_val_loss")}))


# ---------------------------------------------------------------- pick
def score_configs(cfgs: list[str], parts=("val", "web-dev")) -> list[dict]:
    """Per run config: string match k/n and made-up strings on val and/or web-dev, scored with e1.score_e1b's
    functions. Never reads web-test answers."""
    from e1.score import score_strings, vlm_strings
    from e1.score_e1b import agg, empty_preds, fabricated, load_json_dir, normalize_gt
    from e1.score_e4 import web_split
    from e1.vlm import RUN_DIRS, SET_DIRS
    gts = {}
    for s, part in (("val", "val"), ("web", "web-dev")):
        if part not in parts:
            continue
        g = {k: v for k, v in load_json_dir(ROOT / SET_DIRS[s] / "gt").items()
             if not any(e.get("raw") == "*" for e in v.get("skipped") or [])}  # same placeholder rule as build()
        if s == "web":
            g = {k: v for k, v in g.items() if web_split(k) == "web-dev"}  # never read web-test answers
        gts[part] = (s, {k: normalize_gt(v, s) for k, v in g.items()})
    out = []
    for cfg in cfgs:
        row = {"config": cfg}
        k_all = n_all = fab_all = ret_all = 0
        for part, (s, g) in gts.items():
            recs = load_json_dir(ROOT / RUN_DIRS[s] / cfg)
            missing = sorted(set(g) - set(recs))
            if missing:
                raise SystemExit(f"{cfg}: {len(missing)}/{len(g)} {part} images not run yet (first {missing[:3]})")
            k = n = fab = ret = 0
            for iid, gt in g.items():
                rec = recs[iid]
                o = rec.get("output")
                preds = empty_preds() if "error" in rec or o is None else vlm_strings(o)
                r = {"pred": preds, "scores": score_strings(gt, preds, None, None)}
                kk, nn = agg([r])
                f, rt = fabricated(r, gt)
                k, n, fab, ret = k + kk, n + nn, fab + sum(f.values()), ret + sum(rt.values())
            row[part] = {"match": [k, n], "fabricated": [fab, ret], "images": len(g)}
            k_all, n_all, fab_all, ret_all = k_all + k, n_all + n, fab_all + fab, ret_all + ret
        row["pooled"] = {"match": [k_all, n_all], "fabricated": [fab_all, ret_all]}
        out.append(row)
    return out


def pick_scores(run: str, mode: str, steps: list[int]) -> list[dict]:
    rows = score_configs([f"{mode}__{run}-{s}" for s in steps])
    for r, s in zip(rows, steps):
        r["step"] = s
    return rows


def _rate(x):
    return x[0] / x[1] if x[1] else 0.0


def cmd_pick_base(a):
    """Phase-B base: the phase-A open model with the highest J string match on web-dev (only the dev split may steer
    choices); tie -> fewer made-up strings; tie -> order given. Rule fixed on 2026-11-22 before the 2B/3.5 runs."""
    rows = score_configs([f"J__{m}" for m in a.models], parts=("web-dev",))
    best = min(enumerate(rows), key=lambda x: (-_rate(x[1]["web-dev"]["match"]), x[1]["web-dev"]["fabricated"][0],
                                               x[0]))[1]
    name = best["config"].split("__", 1)[1]
    res = {"base": name, "rule": "max J string match on web-dev; tie -> fewer made-up strings; tie -> queue order",
           "candidates": rows}
    out = ROOT / ".cache/e4/lora/base_pick.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    for r in rows:
        print(f"{r['config']}: web-dev {r['web-dev']['match']} made-up {r['web-dev']['fabricated']}", flush=True)
    print(name)


def cmd_pick(a):
    d = Path(a.lora_root) / a.run
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    if not meta.get("finished"):
        raise SystemExit(f"{d}: training not finished")
    mode = "JO" if meta["mode"] == "J+ocr" else "J"
    rows = pick_scores(a.run, mode, sorted(int(s) for s in meta["checkpoints"]))
    best = min(rows, key=lambda r: (-_rate(r["pooled"]["match"]), r["pooled"]["fabricated"][0], r["step"]))
    res = {"run": a.run, "mode": mode, "config": best["config"], "step": best["step"],
           "adapter": str(d / f"ckpt-{best['step']}"),
           "rule": "max string match pooled over val + web-dev; tie -> fewer made-up strings; tie -> earlier step",
           "best_step_by_val_loss": meta.get("best_step_by_val_loss"), "checkpoints": rows}
    (d / "pick.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    for r in rows:
        print(f"{r['config']}: val {r['val']['match']} web-dev {r['web-dev']['match']} pooled {r['pooled']['match']} "
              f"made-up {r['pooled']['fabricated']}")
    print(f"pick: {best['config']}")


def _versions() -> str:
    import peft
    import torch
    import transformers
    return f"torch {torch.__version__}, transformers {transformers.__version__}, peft {peft.__version__}"


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pk = sub.add_parser("pick")
    pk.add_argument("--run", required=True, help="run name: <lora-root>/<run>/meta.json")
    pk.add_argument("--lora-root", default=str(ROOT / ".cache/e4/lora"))
    pb = sub.add_parser("pick-base")
    pb.add_argument("models", nargs="+", help="phase-A model names with J runs on web")
    for name in ("check", "train"):
        p = sub.add_parser(name)
        p.add_argument("--base", required=True, help="HF repo id (offline snapshot) or local snapshot dir")
        p.add_argument("--ocr", action="store_true", help="B3: PP-OCRv6 lines in the prompt")
        p.add_argument("--max-pixels", type=int, default=2097152)
        p.add_argument("--seed", type=int, default=20261125)
    c = sub.choices["check"]
    c.add_argument("--n", type=int, default=4)
    c.add_argument("--split", default="train", choices=["train", "val", "val_la"])
    t = sub.choices["train"]
    t.add_argument("--out", required=True)
    t.add_argument("--n-train", type=int, default=None, help="first N of the seeded shuffle of data/E4/train")
    t.add_argument("--rank", type=int, default=16)
    t.add_argument("--alpha", type=int, default=32)
    t.add_argument("--dropout", type=float, default=0.05)
    t.add_argument("--lr", type=float, default=1e-4)
    t.add_argument("--warmup", type=float, default=0.03, help="fraction of steps")
    t.add_argument("--epochs", type=int, default=1)
    t.add_argument("--batch", type=int, default=1)
    t.add_argument("--grad-accum", type=int, default=8)
    t.add_argument("--eval-every", type=int, default=250)
    t.add_argument("--save-every", type=int, default=250)
    a = ap.parse_args()
    {"check": cmd_check, "train": cmd_train, "pick": cmd_pick, "pick-base": cmd_pick_base}[a.cmd](a)


if __name__ == "__main__":
    main()
