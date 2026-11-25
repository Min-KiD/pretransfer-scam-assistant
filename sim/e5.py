"""E5: swap the dialogue model. Only the `tu_do` assistant runs (the style kept after E2); the simulated user stays
`gemini-3.5-flash-lite` (sim.run.VICTIM_MODEL) for every assistant model, so only the assistant changes.

    python -m sim.e5 --models gemini-3.5-flash-lite,gemini-3.8-flash@low [--workers 8] [--cap-usd 12]
    python -m sim.e5 --report-only
Models are core.llm names: "gemini-..." (optionally "@low" thinking), "local:<served name>" for the vLLM server,
"openai:..." / "anthropic:..." / "openrouter:..." (skipped while their key is missing).
Sessions go to experiments/E5/sessions.jsonl (resumable, one row per case x model, every turn logged for E6);
the report to experiments/E5/report.md. Open-model VRAM comes from experiments/E5/open_meta.json (written by the
server runner).
"""
from __future__ import annotations

import argparse
import json
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from core import llm
from core.scenarios import ROOT, load
from e1.score import wilson
from sim.cases import CASE_DIR, PER_SCENARIO
from sim.run import CHUA_DU, K, Budget, run_tu_do

OUT = ROOT / "experiments/E5"
BASE = "gemini-3.5-flash-lite"
E2_TU_DO_V1 = 0.787  # experiments/E2/report.md, tu_do after 3 questions, run 2
# Minh 22/11 (plan section 7): only flash-lite and the open models run on all 300 cases; the other closed models run
# on the 75 `v1` cases. One mid-tier model per vendor from the official price page (2026-11-22). Claude's account has
# no credit (tried once 22/11): skipped until the planner tab says otherwise.
CLOSED = ["gemini-3.5-flash-lite", "gemini-3.8-flash@low", "gemini-4-carbon", "openai:gpt-6.2-sol"]
_NO_DISK = "bỏ ngày 22/11 theo quyết định của Minh: đĩa server dùng chung chỉ còn khoảng 24 GB trống; lý do là dung lượng, không phải kết quả"
SKIPPED = {"anthropic:claude-sonnet-5-5": "key hợp lệ nhưng tài khoản chưa có tiền (gọi thử 1 lần ngày 22/11, HTTP 400 "
                                          "\"credit balance is too low\"); bỏ qua theo mục 7 bản kế hoạch",
           "local:gemma-4-e4b": _NO_DISK, "local:qwen3.5-9b": _NO_DISK,
           "local:qwen3-vl-8b-fp8": "bỏ ngày 22/11 theo quyết định của Minh: mốc model lớn là các model đóng qua API; "
                                    "không phải vì kết quả"}


def full_set(model: str) -> bool:
    return model == BASE or is_open(model)


def is_open(model: str) -> bool:
    return model.startswith("local:")


def load_cases():
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASE_DIR.glob("*.json"))]
    for c in cases:
        c["v1"] = int(c["id"].rsplit("__", 1)[1]) < PER_SCENARIO
    return cases


def load_rows(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")] if path.exists() else []


# ---------------------------------------------------------------- scoring
def rate(k, n):
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "p": k / n if n else float("nan"), "lo": lo, "hi": hi}


def fmt(r, digits=1):
    if not r["n"]:
        return "-"
    return f"{100 * r['p']:.{digits}f}% ({r['k']}/{r['n']}) [{100 * r['lo']:.0f}-{100 * r['hi']:.0f}]"


def pctl(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")


def score(rows, scen, subset=None):
    rs = [r for r in rows if subset is None or r["case"] in subset]
    n = len(rs)
    m = {"n": n}
    for k in range(K + 1):
        m[f"kb{k}"] = rate(sum(r["preds"][k] == r["kich_ban"] for r in rs), n)
    last = [r["preds"][K] for r in rs]
    m["nhom"] = rate(sum(p != CHUA_DU and scen[p].nhom == r["nhom"] for p, r in zip(last, rs)), n)
    m["chua_du"] = rate(sum(p == CHUA_DU for p in last), n)
    normal = [r for r in rs if r["nhom"] == "binh_thuong"]
    scam = [r for r in rs if r["nhom"] == "lua_dao"]
    m["fp"] = rate(sum(r["preds"][K] != CHUA_DU and scen[r["preds"][K]].nhom == "lua_dao" for r in normal), len(normal))
    m["miss"] = rate(sum(r["preds"][K] != CHUA_DU and scen[r["preds"][K]].nhom == "binh_thuong" for r in scam),
                     len(scam))
    m["q"] = sum(r["n_asked"] for r in rs) / n if n else float("nan")
    m["q0"] = rate(sum(r["n_asked"] == 0 for r in rs), n)
    turns = [t for r in rs for t in r.get("turns", [])]
    m["bad_format"] = rate(sum(t["raw_du_doan"] is not None for t in turns), len(turns))
    m["retries"] = sum(t["retries"] for t in turns)
    m["turns"] = len(turns)
    secs = [t["seconds"] for t in turns]
    m["sec_mean"] = sum(secs) / len(secs) if secs else float("nan")
    m["sec_p90"] = pctl(secs, 0.9)
    m["tok_in"] = sum(t["tokens_in"] for t in turns) / n if n else 0
    m["tok_out"] = sum(t["tokens_out"] for t in turns) / n if n else 0
    m["usd"] = sum(r["usd"] for r in rs) / n if n else 0
    m["usd_total"] = sum(r["usd"] for r in rs)
    m["victim_usd"] = sum(r.get("victim_usd", 0) for r in rs)
    return m


def per_scenario(rows, scen):
    by = defaultdict(list)
    for r in rows:
        by[r["kich_ban"]].append(r)
    return {sid: rate(sum(r["preds"][K] == sid for r in by[sid]), len(by[sid])) for sid in sorted(by)}


def confusions(rows, top=8):
    c = Counter((r["kich_ban"], r["preds"][K]) for r in rows if r["preds"][K] != r["kich_ban"])
    return c.most_common(top)


# ---------------------------------------------------------------- report
def report(rows, scen, cases, cap, opening_usd):
    v1 = {c["id"] for c in cases if c["v1"]}
    models = sorted({r["model"] for r in rows}, key=lambda m: (is_open(m), CLOSED.index(m) if m in CLOSED else 9, m))
    by = {m: [r for r in rows if r["model"] == m] for m in models}
    S = {m: score(by[m], scen) for m in models}
    S1 = {m: score(by[m], scen, v1) for m in models}
    meta = json.loads((OUT / "open_meta.json").read_text()) if (OUT / "open_meta.json").exists() else {}
    full = [m for m in models if S[m]["n"] == len(cases)]
    opened = [m for m in full if is_open(m)]
    closed_v1 = [m for m in models if not is_open(m) and S1[m]["n"] == len(v1)]
    best = lambda ms, SS: max(ms, key=lambda m: (SS[m]["kb3"]["p"], -SS[m]["fp"]["p"])) if ms else None  # noqa: E731
    bc, bo = best(closed_v1, S1), best(opened, S)
    L = ["# E5 - Model hội thoại: model mở so với các model đóng\n",
         f"{len(cases)} tình huống chỉ có chữ (15 kịch bản x 20; `v1` = 75 tình huống của E2, 5 mỗi kịch bản). Trợ lý kiểu "
         f"`tu_do` (tự hỏi tối đa 3 câu rồi chọn một kịch bản hoặc `{CHUA_DU}`), prompt giữ nguyên như E2 cho mọi model. "
         f"Nạn nhân giả lập: `{BASE}` cho mọi lần chạy. Mỗi model chạy một lần, không chạy lại để chọn. Ngoặc vuông: "
         "khoảng tin cậy Wilson 95%.\n"]
    # M2 rule
    L.append("## Kết luận theo điều kiện M2 (bản kế hoạch, mục 5)\n")
    if BASE in S and bo:
        d_kb = S[BASE]["kb3"]["p"] - S[bo]["kb3"]["p"]
        d_fp = S[bo]["fp"]["p"] - S[BASE]["fp"]["p"]
        ok1, ok2 = d_kb <= 0.05, d_fp <= 0.05
        L.append(f"Model mở tốt nhất: `{bo}`.\n")
        L.append(f"- Đúng kịch bản sau 3 câu: `{bo}` {fmt(S[bo]['kb3'])} so với `{BASE}` {fmt(S[BASE]['kb3'])}: "
                 f"{'kém' if d_kb > 0 else 'hơn'} {abs(100 * d_kb):.1f} điểm. Ngưỡng: kém không quá 5 điểm. "
                 f"**{'Đạt' if ok1 else 'Không đạt'}.**")
        L.append(f"- Báo nhầm giao dịch bình thường: `{bo}` {fmt(S[bo]['fp'])} so với `{BASE}` {fmt(S[BASE]['fp'])}: "
                 f"{'cao hơn' if d_fp > 0 else 'thấp hơn'} {abs(100 * d_fp):.1f} điểm. Ngưỡng: cao hơn không quá 5 điểm. "
                 f"**{'Đạt' if ok2 else 'Không đạt'}.**")
        L.append("\n" + ("Cả hai vế đạt: không cần distill để thay model hội thoại." if ok1 and ok2 else
                         "Có vế không đạt: Minh quyết có distill không.") + "\n")
    else:
        L.append("Chưa có model mở chạy đủ 300 tình huống.\n")
    if BASE in S1:
        d = 100 * (S1[BASE]["kb3"]["p"] - E2_TU_DO_V1)
        L.append(f"Kiểm tra lặp lại E2: `{BASE}` trên `v1` đúng kịch bản sau 3 câu {fmt(S1[BASE]['kb3'])}, E2 lần 2 là "
                 f"78,7% (59/75); lệch {d:+.1f} điểm"
                 + (" (trong khoảng tin cậy)." if S1[BASE]["kb3"]["lo"] <= E2_TU_DO_V1 <= S1[BASE]["kb3"]["hi"] else
                    ", ngoài khoảng tin cậy: cần xem lại.") + "\n")
    # Main table
    for title, SS in (("Cả 300 tình huống (chỉ `gemini-3.5-flash-lite` và model mở)", S),
                      ("Tập con `v1` (75 tình huống, so với E2; mọi model)", S1)):
        L.append(f"## Đúng kịch bản và đúng nhóm: {title}\n")
        L.append("| Nhóm | Model | Số phiên | Sau 0 câu | Sau 1 câu | Sau 2 câu | Sau 3 câu | Đúng nhóm | "
                 f"`{CHUA_DU}` |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for m in models:
            s = SS[m]
            if SS is S and not full_set(m):
                continue
            L.append(f"| {'Mở' if is_open(m) else 'Đóng'} | `{m}` | {s['n']} | " + " | ".join(
                fmt(s[f"kb{k}"]) for k in range(K + 1)) + f" | {fmt(s['nhom'])} | {fmt(s['chua_du'])} |")
        for m, why in SKIPPED.items():
            L.append(f"| {'Mở' if is_open(m) else 'Đóng'} | `{m}` | không chạy: {why} | | | | | | |")
        L.append("")
    L.append("## Báo nhầm, bỏ sót, số câu hỏi\n")
    L.append("Báo nhầm: tình huống bình thường bị kết luận giống chiêu lừa (mẫu số 80 trên 300, 20 trên `v1`). Bỏ sót: "
             "tình huống lừa đảo bị kết luận giống chuyện bình thường (mẫu số 220 trên 300, 55 trên `v1`). Sau 3 câu.\n")
    L.append("| Model | Tập | Báo nhầm | Bỏ sót | Số câu hỏi TB | Kết luận ngay, không hỏi |")
    L.append("|---|---|---|---|---|---|")
    for m in models:
        for tag, SS in (("300", S), ("v1", S1)):
            if tag == "300" and not full_set(m):
                continue
            s = SS[m]
            L.append(f"| `{m}` | {tag} | {fmt(s['fp'])} | {fmt(s['miss'])} | {s['q']:.2f} | {fmt(s['q0'])} |")
    L.append("")
    L.append("## Định dạng, tốc độ, chi phí\n")
    L.append("Trả lời hỏng định dạng: `du_doan` không phải một mã kịch bản hợp lệ (tính là `chua_du_can_cu`). Gọi lại: số "
             "lần gọi hỏng (lỗi API hoặc JSON không đọc được) trước lần gọi được giữ. Giây mỗi lượt tính riêng lượt của "
             "trợ lý. USD theo giá niêm yết dùng ở E1; model mở tự host tính 0 USD.\n")
    L.append("| Model | Lượt | Hỏng định dạng | Gọi lại | Giây/lượt TB | p90 | Token vào/phiên | Token ra/phiên | "
             "USD/phiên | VRAM đỉnh |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for m in models:
        s = S[m]
        vr = meta.get(m, {}).get("vram_peak_mib")
        L.append(f"| `{m}` | {s['turns']} | {fmt(s['bad_format'])} | {s['retries']} | {s['sec_mean']:.2f} | "
                 f"{s['sec_p90']:.2f} | {s['tok_in']:.0f} | {s['tok_out']:.0f} | {s['usd']:.5f} | "
                 f"{f'{vr} MiB' if vr else '-'} |")
    L.append("")
    for m in models:
        if m in meta:
            L.append(f"- `{m}`: " + ", ".join(f"{k} {v}" for k, v in meta[m].items()))
    L.append("\nKiểm tra `trich`: kiểu `tu_do` không trả `trich` (schema chỉ có `du_doan`, `cau_hoi`; E2 giữ nguyên prompt "
             "này), nên số đo \"trích nguyên văn\" không áp dụng cho E5.\n")
    # Per scenario + confusions. The best closed model is only measured on v1, so the three are compared there; the
    # flash-lite and best open model also get the 300-case columns.
    trio = [m for m in dict.fromkeys([bc, bo, BASE]) if m]
    if trio:
        cols = [(m, "v1", [r for r in by[m] if r["case"] in v1]) for m in trio]
        cols += [(m, "300", by[m]) for m in trio if full_set(m)]
        L.append("## Theo kịch bản (đúng kịch bản sau 3 câu; `v1` 5 tình huống mỗi dòng, 300 là 20)\n")
        L.append(f"Tốt nhất nhóm đóng (trên `v1`): `{bc}`. Tốt nhất nhóm mở (trên 300): `{bo}`.\n")
        ps = [per_scenario(rs, scen) for _, _, rs in cols]
        L.append("| Kịch bản | Nhóm | " + " | ".join(f"`{m}` {t}" for m, t, _ in cols) + " |")
        L.append("|---|---|" + "---|" * len(cols))
        for sid in sorted(scen):
            L.append(f"| `{sid}` | {scen[sid].nhom} | " + " | ".join(
                f"{100 * p[sid]['p']:.0f}% ({p[sid]['k']}/{p[sid]['n']})" if sid in p else "-" for p in ps) + " |")
        L.append("")
        L.append("## Cặp nhầm nhiều nhất (kịch bản thật -> kết luận, sau 3 câu)\n")
        for (m, t, rs) in cols:
            L.append(f"- `{m}` ({t}): " + "; ".join(f"`{a}` -> `{b}` {n}" for (a, b), n in confusions(rs)))
        L.append("")
    total = sum(S[m]["usd_total"] + S[m]["victim_usd"] for m in models) + opening_usd
    L.append("## Chi phí API thật\n")
    L.append("| Model | Trợ lý (USD) | Nạn nhân giả lập (USD) |")
    L.append("|---|---|---|")
    for m in models:
        L.append(f"| `{m}` | {S[m]['usd_total']:.3f} | {S[m]['victim_usd']:.3f} |")
    L.append(f"\nSinh 225 tin mở đầu mới: {opening_usd:.3f} USD. Tổng E5: {total:.2f} USD (trần lần chạy {cap} USD; trần "
             "Gemini chung cho E4, E5, E6 là 20 USD, GPT 3 USD).\n")
    (OUT / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return S, bc, bo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(CLOSED))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cap-usd", type=float, default=5.0, help="cap on the new spend of this invocation")
    ap.add_argument("--limit", type=int, default=0, help="first N cases only (smoke test, rows still kept)")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--full", action="store_true", help="all 300 cases for every model given (E10 part B)")
    ap.add_argument("--project-after", type=int, default=0,
                    help="run N sessions, then project the cost of all jobs before starting more: above --cap-usd "
                         "run only the v1 cases (queued first); if the v1 cases alone are still above the cap, stop "
                         "at those N sessions (E10 part B, E11)")
    a = ap.parse_args()
    scen, issues = load()
    assert not issues, issues
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "sessions.jsonl"
    rows = [r for r in load_rows(path) if "preds" in r]
    cases = load_cases()
    opening_usd = sum(c.get("sinh_boi", {}).get("usd", 0) for c in cases if not c["v1"])
    if not a.report_only:
        done = {(r["case"], r["model"]) for r in rows}
        spent = sum(r["usd"] + r.get("victim_usd", 0) for r in rows) + opening_usd
        budget = Budget(a.cap_usd, 0.0)
        models = [m for m in a.models.split(",") if m]
        for m in models:
            if not llm.has_key(m):
                print(f"{m}: chưa có key, bỏ qua")
        models = [m for m in models if llm.has_key(m)]
        subset = cases[: a.limit] if a.limit else cases
        jobs = [(c, m) for m in models for c in subset
                if (c["id"], m) not in done and (a.full or full_set(m) or c["v1"])]
        jobs.sort(key=lambda j: not j[0]["v1"])  # stable: v1 cases first, so a projection stop still covers v1
        print(f"{len(jobs)} sessions to run; E5 spent so far {spent:.3f} USD", flush=True)
        lock = threading.Lock()
        v1_only = threading.Event()
        halt = threading.Event()  # projection over the cap even for the v1 cases: no new session starts
        decided = threading.Event()  # the first --project-after sessions have settled and the projection is made
        if not a.project_after:
            decided.set()
        started = [0]
        n_v1 = sum(c["v1"] for c, _ in jobs)
        finished = []  # USD (assistant + simulated user) of the sessions finished in this invocation
        settled = 0  # sessions of this invocation that returned (finished or error)

        def one(c, m):
            with lock:
                gated = started[0] >= a.project_after
                if not gated:
                    started[0] += 1
            if gated:  # wait for the projection, so exactly --project-after sessions run before it
                decided.wait()
            if budget.stop.is_set() or halt.is_set() or (v1_only.is_set() and not c["v1"]):
                return None
            base = {"case": c["id"], "model": m, "assistant": "tu_do", "kich_ban": c["kich_ban"], "nhom": c["nhom"],
                    "tinh_cach": c["tinh_cach"], "v1": c["v1"]}
            try:
                return {**base, **run_tu_do(c, scen, budget, model=m)}
            except Exception as e:
                return {**base, "error": f"{type(e).__name__}: {e}"}

        with ThreadPoolExecutor(a.workers) as ex, open(path, "a", encoding="utf-8") as f:
            futs = [ex.submit(one, c, m) for c, m in jobs]
            for i, fu in enumerate(as_completed(futs), 1):
                r = fu.result()
                settled += 1  # before the projection only the first --project-after sessions can return
                if r is not None:
                    with lock:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                        f.flush()
                    if "error" in r:
                        print(f"  {r['case']} {r['model']}: {r['error'][:160]}", flush=True)
                    else:
                        rows.append(r)
                        finished.append(r["usd"] + r.get("victim_usd", 0))
                if not decided.is_set() and settled == min(a.project_after, len(jobs)):
                    mean = sum(finished) / len(finished) if finished else float("inf")
                    proj = mean * len(jobs)
                    print(f"PROJECTION after {len(finished)} sessions ({settled - len(finished)} errors or not "
                          f"run): {proj:.3f} USD for {len(jobs)} (cap {a.cap_usd})", flush=True)
                    if proj > a.cap_usd:
                        if n_v1 < len(jobs) and mean * n_v1 <= a.cap_usd:
                            v1_only.set()
                            print("PROJECTION over the cap: running the v1 cases only", flush=True)
                        else:
                            halt.set()
                            print(f"PROJECTION over the cap for the {n_v1} v1 cases too ({mean * n_v1:.3f} USD): "
                                  f"STOPPED at the {len(finished)} sessions run", flush=True)
                    decided.set()
                if i % 25 == 0:
                    print(f"  {i}/{len(jobs)} sessions, {budget.spent():.3f} USD", flush=True)
        if budget.stop.is_set():
            print(f"STOPPED at the cost cap: {budget.spent():.3f} USD")
    S, bc, bo = report(rows, scen, cases, a.cap_usd, opening_usd)
    for m, s in S.items():
        print(f"{m:32s} n={s['n']:3d} kb3={100 * s['kb3']['p']:.1f}% fp={100 * s['fp']['p']:.1f}% "
              f"miss={100 * s['miss']['p']:.1f}% q={s['q']:.2f} usd/phien={s['usd']:.4f}")
    print("report:", (OUT / "report.md").relative_to(ROOT))


if __name__ == "__main__":
    main()
