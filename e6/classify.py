"""E6: small text classifiers that guess the scenario from what the user said (a second opinion next to the LLM).

  python -m e6.classify train --model c0|c1|c2|c3     # fit on data/E6/cases.jsonl (train), pick on val
  python -m e6.classify predict --model c0|c1|c2|c3   # every test input -> data/E6/preds/<model>.jsonl

Models
  c0  TF-IDF (word 1-2 grams + char 2-5 grams) + logistic regression (scikit-learn); C picked on val.
  c1  no training: intfloat/multilingual-e5-base embeds the text ("query: ") and each scenario's name + description
      ("passage: "); scores = cosine / T, T picked on val by log-loss (the only fitted number).
  c2  fine-tuned vinai/phobert-base-v2 (AGPL-3.0: fine for this experiment, would bind a product that ships it), input
      word-segmented with pyvi as PhoBERT expects.
  c3  fine-tuned intfloat/multilingual-e5-small (MIT).
Inputs: two kinds per case, `mo_dau` (opening message only) and `day_du` (opening + the user's answers, without the
assistant's questions). Train/val come from sim/e6_data.py (gemini-3.5-flash-lite wrote them). Test sets (never trained
on): the 300 E5 cases (`sim`: opening; `sim:<model>`: opening + the user turns of that model's E5 session, so the
classifier sees what that LLM saw) and the real narratives `data/narr/real/*.json` (`loi_ke`, label `kich_ban`, one
kind). Prediction rows: {set, kind, id, label, probs (15, in SCEN order), ms}. ms = CPU time for that one text, batch 1.
Weights go to .cache/e6/<model>/ (not committed).
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/E6"
WDIR = ROOT / ".cache/e6"
HF = {"c1": "intfloat/multilingual-e5-base", "c2": "vinai/phobert-base-v2", "c3": "intfloat/multilingual-e5-small"}
SEED = 20261124


def scenarios():
    from core.scenarios import load
    scen, issues = load()
    assert not issues, issues
    return scen


SCEN = sorted(scenarios())


def train_val():
    rows = [json.loads(l) for l in open(DATA / "cases.jsonl", encoding="utf-8")]
    out = {"train": [], "val": []}
    for r in rows:
        y = SCEN.index(r["kich_ban"])
        out[r["split"]].append({"id": r["id"], "kind": "mo_dau", "text": r["tin_mo_dau"], "y": y})
        out[r["split"]].append({"id": r["id"], "kind": "day_du", "text": " ".join([r["tin_mo_dau"], *r["tra_loi"]]),
                                "y": y})
    return out["train"], out["val"]


def test_inputs():
    """Every evaluation input: E5 openings, E5 sessions of every model that ran all 300 cases, real narratives."""
    items = []
    cases = {json.loads(p.read_text())["id"]: json.loads(p.read_text()) for p in sorted((ROOT / "sim/cases").glob("*.json"))}
    for cid, c in cases.items():
        items.append({"set": "sim", "kind": "mo_dau", "id": cid, "label": c["kich_ban"], "text": c["tin_mo_dau"]})
    sp = ROOT / "experiments/E5/sessions.jsonl"
    by_model = {}
    for l in open(sp, encoding="utf-8") if sp.exists() else []:
        r = json.loads(l)
        if "preds" in r:
            by_model.setdefault(r["model"], []).append(r)
    for m, rs in by_model.items():
        if len(rs) != len(cases):
            continue
        for r in rs:
            user = [h["text"] for h in r["history"] if h["role"] == "user"]
            items.append({"set": f"sim:{m}", "kind": "day_du", "id": r["case"], "label": r["kich_ban"],
                          "text": " ".join(user)})
    for p in sorted((ROOT / "data/narr/real").glob("*.json")):
        n = json.loads(p.read_text(encoding="utf-8"))
        items.append({"set": "real", "kind": "mo_dau", "id": n["id"], "label": n["kich_ban"], "text": n["loi_ke"]})
    return items


def softmax(z, axis=-1):
    z = z - z.max(axis=axis, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=axis, keepdims=True)


def log_loss(p, y):
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))))


def macro_f1(pred, y, k=None):
    k = k or len(SCEN)
    f = []
    for c in range(k):
        tp = int(np.sum((pred == c) & (y == c)))
        fp = int(np.sum((pred == c) & (y != c)))
        fn = int(np.sum((pred != c) & (y == c)))
        if tp + fp + fn:
            f.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f))


# ---------------------------------------------------------------- c0
def c0_train(train, val):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline, make_union
    best = None
    for C in (1.0, 4.0, 16.0, 64.0):
        vec = make_union(TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2),
                         TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2))
        pipe = make_pipeline(vec, LogisticRegression(C=C, max_iter=3000))
        pipe.fit([r["text"] for r in train], [r["y"] for r in train])
        pv = pipe.predict_proba([r["text"] for r in val])
        f1 = macro_f1(pv.argmax(1), np.array([r["y"] for r in val]))
        print(f"c0 C={C}: val macro-F1 {f1:.4f}", flush=True)
        if not best or f1 > best[0]:
            best = (f1, C, pipe)
    (WDIR / "c0").mkdir(parents=True, exist_ok=True)
    pickle.dump(best[2], open(WDIR / "c0/model.pkl", "wb"))
    return {"C": best[1], "val_macro_f1": round(best[0], 4)}


def c0_predict(texts):
    pipe = pickle.load(open(WDIR / "c0/model.pkl", "rb"))
    return pipe.predict_proba(texts), (lambda t: pipe.predict_proba([t]))


# ---------------------------------------------------------------- c1
def e5_embed(model_name, texts, prefix, device, bs=64):
    import torch
    from transformers import AutoModel, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_name)
    mod = AutoModel.from_pretrained(model_name).to(device).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            b = tok([prefix + t for t in texts[i:i + bs]], padding=True, truncation=True, max_length=256,
                    return_tensors="pt").to(device)
            h = mod(**b).last_hidden_state
            m = b["attention_mask"].unsqueeze(-1).float()
            e = (h * m).sum(1) / m.sum(1)
            out.append(torch.nn.functional.normalize(e, dim=-1).cpu().numpy())
    return np.concatenate(out), (tok, mod)


def scen_passages():
    scen = scenarios()
    return [f"{scen[s].ten}. {scen[s].mo_ta}" for s in SCEN]


def c1_train(train, val, device):
    P, _ = e5_embed(HF["c1"], scen_passages(), "passage: ", device)
    V, _ = e5_embed(HF["c1"], [r["text"] for r in val], "query: ", device)
    y = np.array([r["y"] for r in val])
    sims = V @ P.T
    best = min(((log_loss(softmax(sims / T), y), T) for T in (0.005, 0.01, 0.02, 0.03, 0.05, 0.1)))
    (WDIR / "c1").mkdir(parents=True, exist_ok=True)
    np.save(WDIR / "c1/passages.npy", P)
    json.dump({"T": best[1]}, open(WDIR / "c1/meta.json", "w"))
    return {"T": best[1], "val_log_loss": round(best[0], 4),
            "val_macro_f1": round(macro_f1(sims.argmax(1), y), 4)}


def c1_predict(texts, device):
    import torch
    P = np.load(WDIR / "c1/passages.npy")
    T = json.load(open(WDIR / "c1/meta.json"))["T"]
    E, (tok, mod) = e5_embed(HF["c1"], texts, "query: ", device)
    mod = mod.to("cpu")

    def one(t):
        with torch.no_grad():
            b = tok(["query: " + t], truncation=True, max_length=256, return_tensors="pt")
            h = mod(**b).last_hidden_state.mean(1)
            e = torch.nn.functional.normalize(h, dim=-1).numpy()
        return softmax(e @ P.T / T)
    return softmax(E @ P.T / T), one


# ---------------------------------------------------------------- c2 / c3 fine-tune
def prep(model, texts):
    if model == "c2":
        from pyvi import ViTokenizer
        return [ViTokenizer.tokenize(t) for t in texts]
    return ["query: " + t for t in texts]


def ft_train(model, train, val, device, epochs=4, bs=32, max_len=160):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup
    torch.manual_seed(SEED)
    random.seed(SEED)
    lr = 3e-5 if model == "c2" else 5e-5
    tok = AutoTokenizer.from_pretrained(HF[model])
    mod = AutoModelForSequenceClassification.from_pretrained(HF[model], num_labels=len(SCEN)).to(device)
    xt, yt = prep(model, [r["text"] for r in train]), [r["y"] for r in train]
    xv, yv = prep(model, [r["text"] for r in val]), np.array([r["y"] for r in val])
    opt = torch.optim.AdamW(mod.parameters(), lr=lr, weight_decay=0.01)
    steps = epochs * ((len(xt) + bs - 1) // bs)
    sch = get_linear_schedule_with_warmup(opt, int(0.06 * steps), steps)
    scaler = torch.amp.GradScaler(enabled=device == "cuda")
    log, best, t0 = [], None, time.time()
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    for ep in range(epochs):
        mod.train()
        idx = list(range(len(xt)))
        random.shuffle(idx)
        tot = 0.0
        for i in range(0, len(idx), bs):
            bi = idx[i:i + bs]
            b = tok([xt[j] for j in bi], padding=True, truncation=True, max_length=max_len, return_tensors="pt").to(device)
            with torch.autocast(device, dtype=torch.float16, enabled=device == "cuda"):
                loss = mod(**b, labels=torch.tensor([yt[j] for j in bi], device=device)).loss
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sch.step()
            tot += loss.item() * len(bi)
        pv = ft_logits(tok, mod, xv, device, max_len)
        f1 = macro_f1(pv.argmax(1), yv)
        log.append({"epoch": ep + 1, "train_loss": round(tot / len(xt), 4), "val_macro_f1": round(f1, 4),
                    "val_log_loss": round(log_loss(softmax(pv), yv), 4)})
        print(model, log[-1], flush=True)
        if not best or f1 > best:
            best = f1
            mod.save_pretrained(WDIR / model)
            tok.save_pretrained(WDIR / model)
    return {"hf": HF[model], "lr": lr, "epochs": epochs, "batch": bs, "max_len": max_len, "seed": SEED,
            "log": log, "best_val_macro_f1": round(best, 4), "minutes": round((time.time() - t0) / 60, 1),
            "vram_peak_mib": round(torch.cuda.max_memory_allocated() / 2 ** 20) if device == "cuda" else None}


def ft_logits(tok, mod, texts, device, max_len=160, bs=64):
    import torch
    mod.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            b = tok(texts[i:i + bs], padding=True, truncation=True, max_length=max_len, return_tensors="pt").to(device)
            out.append(mod(**b).logits.float().cpu().numpy())
    return np.concatenate(out)


def ft_predict(model, texts, device):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(WDIR / model)
    mod = AutoModelForSequenceClassification.from_pretrained(WDIR / model).to(device)
    probs = softmax(ft_logits(tok, mod, prep(model, texts), device))
    cpu = mod.to("cpu")

    def one(t):
        with torch.no_grad():
            b = tok(prep(model, [t]), truncation=True, max_length=160, return_tensors="pt")
            return softmax(cpu(**b).logits.numpy())
    return probs, one


def dir_mb(p: Path) -> float:
    return round(sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["train", "predict"])
    ap.add_argument("--model", required=True, choices=["c0", "c1", "c2", "c3"])
    ap.add_argument("--device", default=None)
    ap.add_argument("--cpu-threads", type=int, default=4)
    a = ap.parse_args()
    import torch
    device = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
    meta_p = DATA / "models.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    if a.cmd == "train":
        train, val = train_val()
        print(f"{a.model}: train {len(train)}, val {len(val)}, device {device}", flush=True)
        WDIR.mkdir(parents=True, exist_ok=True)
        info = {"c0": lambda: c0_train(train, val), "c1": lambda: c1_train(train, val, device)}.get(
            a.model, lambda: ft_train(a.model, train, val, device))()
        meta[a.model] = {**meta.get(a.model, {}), "train": info, "train_device": device,
                         "train_n": len(train), "val_n": len(val)}
        meta_p.write_text(json.dumps(meta, indent=1))
        print(json.dumps(info)[:500])
        return
    items = test_inputs()
    _, val = train_val()
    allx = [r["text"] for r in val] + [r["text"] for r in items]
    fn = {"c0": lambda: c0_predict(allx), "c1": lambda: c1_predict(allx, device),
          "c2": lambda: ft_predict("c2", allx, device), "c3": lambda: ft_predict("c3", allx, device)}[a.model]
    probs, one = fn()
    # CPU latency, one text at a time, on 200 test texts
    torch.set_num_threads(a.cpu_threads)
    rng = random.Random(SEED)
    sample = rng.sample(allx, min(200, len(allx)))
    one(sample[0])
    ms = []
    for t in sample:
        t0 = time.perf_counter()
        one(t)
        ms.append(1000 * (time.perf_counter() - t0))
    (DATA / "preds").mkdir(parents=True, exist_ok=True)
    with open(DATA / "preds" / f"{a.model}.jsonl", "w", encoding="utf-8") as f:
        for r, p in zip([{"set": "val", "kind": r["kind"], "id": r["id"], "label": SCEN[r["y"]]} for r in val] +
                        [{k: v for k, v in it.items() if k != "text"} for it in items], probs):
            f.write(json.dumps({**r, "probs": [round(float(x), 5) for x in p.ravel()]}, ensure_ascii=False) + "\n")
    size = os.path.getsize(WDIR / "c0/model.pkl") / 1e6 if a.model == "c0" else (
        dir_mb(WDIR / a.model) if a.model != "c1" else None)
    meta[a.model] = {**meta.get(a.model, {}), "cpu_ms_p50": round(float(np.median(ms)), 1),
                     "cpu_ms_mean": round(float(np.mean(ms)), 1), "cpu_threads": a.cpu_threads,
                     "size_mb": round(size, 1) if size else None, "hf": HF.get(a.model)}
    meta_p.write_text(json.dumps(meta, indent=1))
    print(f"{a.model}: {len(items)} test + {len(val)} val predictions; CPU {np.median(ms):.1f} ms/text p50")


if __name__ == "__main__":
    main()
