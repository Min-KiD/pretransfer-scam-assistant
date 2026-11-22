"""E1b: open OCR / VLM models on the shared GPU, one model per process.

Groups
- T (text): the model returns plain text; e1.extract regex pulls the strings (like method A).
- J (JSON): same prompt + schema as Gemini method B (e1.vlm.PROMPT / SCHEMA). Local models have no
  constrained decoding, so the schema is appended to the prompt as text (the only model-specific part).

Usage (on the server; ~/vidoc-dev/.venvs/mineru python, read-only, PYTHONPATH=.cache/pylib:.):
  python -m e1.open_models download --model glm-ocr
  python -m e1.open_models run --model glm-ocr --mode T [--budget-min 20 --min-images 60]
  python -m e1.open_models clean --model glm-ocr

Writes data/<E1|E1b>/runs/<T|J>__<model>/<image_id>.json (resumable) and data/E1b/open/<T|J>__<model>.json
(repo, revision, load time, VRAM peak, weights size, versions, how many images ran, budget stop).
Images are interleaved across both sets and all variants, so a run stopped by the time budget still
covers every variant.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import threading
import time
from pathlib import Path

from e1.vlm import PROMPT, RUN_DIRS, SCHEMA, SET_DIRS, set_items

MODELS = {
    # PaddleOCR's transformers engine fetches PP-OCRv6_medium_{det,rec}_safetensors into $PADDLE_PDX_CACHE_HOME itself
    "pp-ocrv6-gpu": {"repos": [], "modes": ["T"], "quant": "paddlex default dtype"},
    "qwen3-vl-8b": {"repos": ["Qwen/Qwen3-VL-8B-Instruct"], "modes": ["J"], "quant": "nf4"},
    "qwen3-vl-4b": {"repos": ["Qwen/Qwen3-VL-4B-Instruct"], "modes": ["J"]},
    "paddleocr-vl-1.6": {"repos": ["PaddlePaddle/PaddleOCR-VL-1.6"], "modes": ["T"]},
    "mineru2.5-pro": {"repos": ["opendatalab/MinerU2.5-Pro-2605-1.2B"], "modes": ["T"], "quant": "mineru-vl-utils default"},
    "glm-ocr": {"repos": ["zai-org/GLM-OCR"], "modes": ["T", "J"]},
    "gemma-4-e4b": {"repos": ["google/gemma-4-E4B-it"], "modes": ["J"], "quant": "nf4"},
    # E4 (2026-11-22). All Apache-2.0, not gated; sizes are in scripts/e4_part0.sh.
    "qwen3-vl-2b": {"repos": ["Qwen/Qwen3-VL-2B-Instruct"], "modes": ["J"]},
    # Extra model (E4 allows two): Qwen3.5 is the generation after Qwen3-VL and is natively multimodal.
    # Dropped from E4 on 2026-11-22 (Minh): qwen3.5-9b, gemma-4-e4b (disk ~24 GB free) and qwen3-vl-8b-fp8.
    "qwen3.5-4b": {"repos": ["Qwen/Qwen3.5-4B"], "modes": ["J"]},
}
JSON_SUFFIX = ("\n\nTrả về đúng một đối tượng JSON hợp lệ theo JSON Schema dưới đây, không thêm chữ nào khác "
               "ngoài JSON:\n" + json.dumps(SCHEMA, ensure_ascii=False))
# GLM-OCR's information-extraction format from its model card: a fixed lead-in plus an empty JSON template.
GLM_TEMPLATE = {"messages": [{"order": 0, "side": "", "text": ""}],
                "accounts": [{"number": "", "bank": "", "holder": ""}],
                "phones": [""], "links": [""], "amounts": [""]}
GLM_JSON_PROMPT = "请按下列JSON格式输出图中信息:\n" + json.dumps(GLM_TEMPLATE, ensure_ascii=False)
ALLOW = ["*.json", "*.safetensors", "*.model", "*.txt", "*.py", "*.jinja", "*.yml", "*.yaml", "*.tiktoken"]


def root() -> Path:
    return Path(__file__).resolve().parent.parent


def snapshot(repo: str, download: bool):
    from huggingface_hub import snapshot_download
    return Path(snapshot_download(repo, allow_patterns=ALLOW, local_files_only=not download))


def weights_bytes(path: Path) -> int:
    return sum(p.resolve().stat().st_size for p in path.rglob("*") if p.is_file())


# ---------------------------------------------------------------- JSON parsing / schema check
def parse_json(text: str):
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < i:
        return None, "no JSON object"
    try:
        obj = json.loads(t[i:j + 1])
    except json.JSONDecodeError as e:
        return None, f"JSONDecodeError: {e}"
    return obj, check_schema(obj)


def check_schema(o) -> str | None:
    if not isinstance(o, dict):
        return "not an object"
    for k in SCHEMA["required"]:
        if not isinstance(o.get(k), list):
            return f"missing or non-list '{k}'"
    for m in o["messages"]:
        if not (isinstance(m, dict) and isinstance(m.get("text"), str) and m.get("side") in ("left", "right")):
            return "bad messages item"
    for a in o["accounts"]:
        if not (isinstance(a, dict) and isinstance(a.get("number"), str)):
            return "bad accounts item"
    for k in ("phones", "links", "amounts"):
        if not all(isinstance(x, str) for x in o[k]):
            return f"bad {k} item"
    return None


# ---------------------------------------------------------------- VRAM sampler (whole process, incl. context)
class VramPeak:
    def __init__(self):
        self.peak_mib = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        me = os.getpid()
        while not self._stop.wait(1.0):
            try:
                for p in pynvml.nvmlDeviceGetComputeRunningProcesses(h):
                    if p.pid == me and p.usedGpuMemory:
                        self.peak_mib = max(self.peak_mib, p.usedGpuMemory // 2 ** 20)
            except Exception:
                pass

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()


# ---------------------------------------------------------------- model wrappers
class HFChat:
    """Chat-template VLM via transformers: Qwen3-VL, Gemma 4, GLM-OCR, PaddleOCR-VL."""

    def __init__(self, path: Path, quant: str | None, chat_kwargs=None, max_new_tokens=4096):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
        kw = {"dtype": torch.bfloat16, "device_map": "cuda:0"}
        if quant == "nf4":
            from transformers import BitsAndBytesConfig
            kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                           bnb_4bit_compute_dtype=torch.bfloat16)
        self.model = AutoModelForImageTextToText.from_pretrained(str(path), **kw).eval()
        self.proc = AutoProcessor.from_pretrained(str(path))
        self.chat_kwargs = chat_kwargs or {}
        self.max_new_tokens = max_new_tokens
        self.boxes = False

    def __call__(self, img_path: Path, prompt: str) -> dict:
        import torch
        from PIL import Image
        img = Image.open(img_path).convert("RGB")
        msgs = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt}]}]
        inputs = self.proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True,
                                               return_tensors="pt", **self.chat_kwargs).to(self.model.device)
        n_in = inputs["input_ids"].shape[1]
        with torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        gen = out[0][n_in:]
        return {"raw": self.proc.decode(gen, skip_special_tokens=True), "tokens_in": int(n_in),
                "tokens_out": int(gen.shape[0])}


class MinerU:
    def __init__(self, path: Path):
        from mineru_vl_utils import MinerUClient
        from mineru_vl_utils.transformers_loading import load_transformers_model, load_transformers_processor
        model = load_transformers_model(str(path), device_map="cuda:0")
        self.client = MinerUClient(backend="transformers", model=model,
                                   processor=load_transformers_processor(str(path)))
        self.boxes = True

    def __call__(self, img_path: Path, prompt: str) -> dict:
        from PIL import Image
        blocks = self.client.two_step_extract(Image.open(img_path).convert("RGB"))
        get = lambda b, k: b.get(k) if isinstance(b, dict) else getattr(b, k, None)  # noqa: E731
        bl = [{"type": get(b, "type"), "bbox": list(get(b, "bbox") or []), "content": get(b, "content") or ""}
              for b in blocks]
        return {"raw": "\n".join(b["content"] for b in bl if b["content"]), "blocks": bl}


class PPOCR:
    """PP-OCRv6 medium det+rec through PaddleOCR's transformers engine (torch on the GPU, no paddle)."""

    def __init__(self):
        from paddleocr import PaddleOCR
        self.ocr = PaddleOCR(text_detection_model_name="PP-OCRv6_medium_det",
                             text_recognition_model_name="PP-OCRv6_medium_rec",
                             engine="transformers", device="gpu:0", use_doc_orientation_classify=False,
                             use_doc_unwarping=False, use_textline_orientation=False)
        self.boxes = True

    def __call__(self, img_path: Path, prompt: str) -> dict:
        res = self.ocr.predict(str(img_path))[0]
        texts = list(res["rec_texts"])
        return {"raw": "\n".join(texts), "lines": [{"text": t, "box": [float(v) for v in b]}
                                                  for t, b in zip(texts, res["rec_boxes"])]}


def load(name: str, mode: str, paths: list[Path]):
    spec = MODELS[name]
    if name == "pp-ocrv6-gpu":
        return PPOCR()
    if name == "mineru2.5-pro":
        return MinerU(paths[0])
    chat_kwargs = {"enable_thinking": False} if name.startswith("gemma") else None
    return HFChat(paths[0], spec.get("quant"), chat_kwargs)


def prompt_for(name: str, mode: str) -> str:
    if mode == "J":
        return GLM_JSON_PROMPT if name == "glm-ocr" else PROMPT + JSON_SUFFIX
    return {"paddleocr-vl-1.6": "OCR:", "glm-ocr": "Text Recognition:"}.get(name, "")


def image_order(base: Path, sets=("E1", "E1b")):
    """Round-robin over (set, variant) groups, shuffled within each group with a fixed seed."""
    groups = {}
    for s in sets:
        for m in set_items(base / SET_DIRS[s], s):
            groups.setdefault((s, m["variant"]), []).append((s, m))
    for k, v in groups.items():
        random.Random(f"e1b-{k}").shuffle(v)
    order, lists = [], list(groups.values())
    while any(lists):
        for v in lists:
            if v:
                order.append(v.pop(0))
    return order


def versions():
    out = {}
    for mod in ("torch", "transformers", "accelerate", "bitsandbytes", "mineru_vl_utils", "paddleocr", "paddlex"):
        try:
            out[mod] = __import__(mod).__version__
        except Exception:
            pass
    return out


def cmd_run(args):
    import torch
    base = root()
    name, mode = args.model, args.mode
    cfg = f"{mode}__{name}"
    sets = tuple(args.sets.split(","))
    suffix = "" if sets == ("E1", "E1b") else "__" + "-".join(sets)
    meta_path = base / "data" / "E1b" / "open" / f"{cfg}{suffix}.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    paths = [snapshot(r, download=False) for r in MODELS[name]["repos"]]
    wdirs = paths or sorted((base / ".cache/paddlex/official_models").glob("PP-OCRv6_medium_*_safetensors"))
    prompt = prompt_for(name, mode)
    with VramPeak() as vp:
        t0 = time.perf_counter()
        runner = load(name, mode, paths)
        torch.cuda.synchronize()
        load_s = time.perf_counter() - t0
        meta.update(model=name, mode=mode, repos=MODELS[name]["repos"] or [p.name for p in wdirs],
                    revisions=[p.name for p in paths] or ["paddlex official_models"],
                    quant=MODELS[name].get("quant", "bf16"), load_seconds=round(load_s, 1),
                    weights_bytes=sum(weights_bytes(p) for p in wdirs), versions=versions(), prompt=prompt,
                    boxes=runner.boxes, decoding="greedy (do_sample=False)", gpu=torch.cuda.get_device_name(0),
                    sets=list(sets))
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        print(f"loaded {cfg} in {load_s:.1f}s", flush=True)
        order = image_order(base, sets)
        done = sum((base / RUN_DIRS[s] / cfg / f"{m['image_id']}.json").exists() for s, m in order)
        t_start, n_new, errors, budget_hit = time.monotonic(), 0, 0, False
        for s, m in order:
            out = base / RUN_DIRS[s] / cfg / f"{m['image_id']}.json"
            if out.exists():
                continue
            if time.monotonic() - t_start > args.budget_min * 60 and done >= args.min_images:
                budget_hit = True
                break
            out.parent.mkdir(parents=True, exist_ok=True)
            torch.cuda.synchronize()
            t1 = time.perf_counter()
            try:
                rec = runner(base / SET_DIRS[s] / m["path"], prompt)
                torch.cuda.synchronize()
                rec["seconds"] = round(time.perf_counter() - t1, 3)
            except Exception as e:  # OOM on a tall image etc.: recorded, scored as all-wrong
                torch.cuda.empty_cache()
                rec = {"error": f"{type(e).__name__}: {str(e)[:300]}", "seconds": round(time.perf_counter() - t1, 3)}
                errors += 1
            if mode == "J" and "raw" in rec:
                rec["output"], rec["parse_error"] = parse_json(rec["raw"])
            rec.update(image_id=m["image_id"], set=s, config=cfg)
            out.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            done += 1
            n_new += 1
            print(f"{done:3d} {s}/{m['image_id']} {rec['seconds']:.2f}s" + (f" ERR {rec['error'][:80]}" if "error" in rec
                                                                          else ""), flush=True)
            if n_new == 3 and errors == 3:  # broken setup, not a hard image: stop, keep weights for a fixed rerun
                for s2, m2 in order:
                    p2 = base / RUN_DIRS[s2] / cfg / f"{m2['image_id']}.json"
                    if p2.exists() and "error" in json.loads(p2.read_text(encoding="utf-8")):
                        p2.unlink()
                raise SystemExit(f"first 3 images all failed: {rec['error']}")
        meta.update(images_done=done, images_total=len(order), run_errors=meta.get("run_errors", 0) + errors,
                    budget_stop=budget_hit, run_minutes=round((time.monotonic() - t_start) / 60, 1),
                    vram_peak_torch_mib=round(torch.cuda.max_memory_reserved() / 2 ** 20),
                    vram_peak_process_mib=max(vp.peak_mib, meta.get("vram_peak_process_mib", 0)))
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(json.dumps({k: meta[k] for k in ("images_done", "budget_stop", "vram_peak_process_mib", "load_seconds")}))


def cmd_download(args):
    for r in MODELS[args.model]["repos"]:
        t0 = time.time()
        p = snapshot(r, download=True)
        print(f"{r} -> {p} {weights_bytes(p) / 1e9:.2f} GB in {time.time() - t0:.0f}s", flush=True)


def cmd_clean(args):
    """Delete a model's weights. Without --force this only reports: weights are kept until the gen/web pass."""
    from huggingface_hub import constants
    hub = Path(constants.HF_HUB_CACHE)
    for r in MODELS[args.model]["repos"]:
        d = hub / ("models--" + r.replace("/", "--"))
        if d.exists() and args.force:
            # This hub version keeps blobs in a shared hub/blobs/ store, outside the models-- folder: delete the files
            # the snapshot links to as well, or the weights stay on disk.
            blobs = {p.resolve() for p in d.rglob("*") if p.is_symlink()}
            blobs = {b for b in blobs if b.is_file() and d not in b.parents}
            shutil.rmtree(d)
            for b in blobs:
                b.unlink(missing_ok=True)
                b.with_name(b.name + ".refs").unlink(missing_ok=True)
            print("removed", d, f"and {len(blobs)} shared blobs")
        elif d.exists():
            print("kept", d, "(use --force to delete)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["download", "run", "clean"])
    ap.add_argument("--model", required=True, choices=list(MODELS))
    ap.add_argument("--mode", choices=["T", "J"])
    ap.add_argument("--budget-min", type=float, default=20)
    ap.add_argument("--min-images", type=int, default=60)
    ap.add_argument("--sets", default="E1,E1b", help="comma list of " + ",".join(SET_DIRS))
    ap.add_argument("--force", action="store_true", help="clean: really delete the weights")
    args = ap.parse_args()
    {"download": cmd_download, "run": cmd_run, "clean": cmd_clean}[args.cmd](args)


if __name__ == "__main__":
    main()
