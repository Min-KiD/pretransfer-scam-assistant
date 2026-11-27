"""Chat-verdict tables for the E7 generator, counted from the chat models' sessions on test set v2.

For every true scenario the table lists how often a model ended a session with each (`muc`, `kich_ban`)
pair. The generator draws the verdict of a mock report from the row of the report's true scenario, so the
mock chat errs where the measured model errs (for example `dat_coc_gia_re` read as an ordinary purchase).

The session files are not in git (`experiments/` is ignored); `e7/chat_confusion.json` holds the counts.

Usage:
    python -m e7.chat_confusion --flash-lite experiments/T6/sessions.jsonl \
        --qwen-lora experiments/E13/sessions.jsonl --qwen-untrained experiments/E12/sessions.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

TABLE_PATH = Path(__file__).resolve().parent / "chat_confusion.json"
UNSURE = "chua_du_can_cu"


def verdict_of(session: dict) -> tuple[str, str]:
    """(`muc`, `kich_ban`) of one test session. An unsure ending keeps the last scenario the model named."""
    final = session["preds"][-1]
    if final == UNSURE:
        named = [p for p in session["preds"] if p != UNSURE]
        return UNSURE, named[-1] if named else session["kich_ban"]
    return ("giong_binh_thuong" if final.startswith("bt_") else "giong_chieu_lua"), final


def count_table(path: Path) -> dict:
    sessions = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    models = sorted({s["model"] for s in sessions})
    assert len(models) == 1, f"{path}: expected one model, found {models}"
    counts: dict[str, Counter] = {}
    for s in sessions:
        counts.setdefault(s["kich_ban"], Counter())[verdict_of(s)] += 1
    return {
        "model": models[0],
        "n_sessions": len(sessions),
        "by_true_scenario": {
            sid: [[muc, pred, n] for (muc, pred), n in sorted(c.items())] for sid, c in sorted(counts.items())
        },
    }


def load_table(name: str) -> dict[str, list[tuple[str, str, int]]]:
    tables = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    assert name in tables, f"unknown chat model {name!r}; known: {sorted(tables)}"
    return {sid: [tuple(row) for row in rows] for sid, rows in tables[name]["by_true_scenario"].items()}


def main() -> None:
    ap = argparse.ArgumentParser(description="Count chat-verdict tables from test set v2 session files.")
    ap.add_argument("--flash-lite", type=Path, required=True)
    ap.add_argument("--qwen-lora", type=Path, required=True)
    ap.add_argument("--qwen-untrained", type=Path, required=True)
    args = ap.parse_args()
    tables = {
        "flash_lite": count_table(args.flash_lite),
        "qwen_lora": count_table(args.qwen_lora),
        "qwen_untrained": count_table(args.qwen_untrained),
    }
    TABLE_PATH.write_text(json.dumps(tables, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, t in tables.items():
        print(f"{name}: {t['model']}, {t['n_sessions']} sessions, {len(t['by_true_scenario'])} scenarios")


if __name__ == "__main__":
    main()
