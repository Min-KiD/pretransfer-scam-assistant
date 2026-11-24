"""E10 part D cases: a session that starts from a chat screenshot (merged vs split image flow).

300 cases, 20 per scenario. Each case is one synthetic screenshot from data/E4 (e1/gen_train.py: the image's ground
truth has the visible chat messages, and the scenario the dialog was written for is the answer key):
- images come from `val` (13 scenarios) and `val_la` (the 2 held-out scenarios). `val` has only 17-19 usable images
  for six scenarios, so those are topped up from `train`. No model in E10 was trained on any of these images (the E4
  LoRA, the only model trained on `train`, is not used), so `train` images are as unseen as `val` ones here.
- usable = at least 3 chat messages in the ground truth (an image with 0-2 bubbles says almost nothing about the case).
- the opening message is one of 5 fixed neutral sentences (seeded, no model call): what happened is only in the image.
- the simulated user's story: the chat messages of the image (read at run time from its gt file) plus a story table.
  Table fields the image shows are set from the image, never sampled against it: `kenh` from the app template,
  `ai_bat_dau` from the first bubble of the whole dialog; `tu_xung`, `ap_luc`, `yeu_cau`, `ly_do_tien` are left empty
  and the simulated user reads them from the chat. The other fields and the account lookup (`tai_khoan`) are sampled
  from the scenario's table as in sim/cases.py.
- personas rotate as in sim/cases.py.

    python -m sim.cases_d          # writes sim/cases_d.jsonl (deterministic; committed)
"""
from __future__ import annotations

import json
import random

from core.scenarios import ROOT, load
from core.schema import FIELDS
from sim.cases import KNOWN_AT_START, PERSONAS
from sim.perfect import sample_table

OUT = ROOT / "sim/cases_d.jsonl"
SEED = 20261124
PER_SCENARIO = 20
MIN_MESSAGES = 3
OPENINGS = [
    "Mình nhận được tin nhắn này, có nên chuyển không?",
    "Bạn xem giúp mình đoạn chat này với, mình sắp chuyển tiền.",
    "Người này nhắn mình như trong ảnh, mình chuyển tiền được không?",
    "Mình đang định chuyển khoản theo đoạn chat này, có vấn đề gì không?",
    "Kiểm tra giúp mình cuộc trò chuyện này trước khi mình chuyển tiền.",
]
# app template of the screenshot -> `kenh` (iMessage and Android Messages are text messages; Viber, WhatsApp and the
# desktop web chat have no value of their own)
KENH = {"zalo": "zalo", "messenger": "messenger", "telegram": "telegram", "imessage": "sms", "android": "sms",
        "viber": "khac", "web": "khac", "whatsapp": "khac"}
FROM_CHAT = ("tu_xung", "ap_luc", "yeu_cau", "ly_do_tien")  # read from the chat by the simulated user


def pool(split: str) -> dict[str, list[dict]]:
    """scenario -> usable images of a split, in file order."""
    d = ROOT / "data/E4" / split
    manifest = {json.loads(l)["image_id"]: json.loads(l) for l in open(d / "manifest.jsonl", encoding="utf-8")}
    out: dict[str, list[dict]] = {}
    for line in open(d / "convs.jsonl", encoding="utf-8"):
        conv = json.loads(line)
        m = manifest.get(conv["id"])
        gt_path = d / "gt" / f"{conv['id']}.json"
        if m is None or not gt_path.exists():
            continue  # failed renders have no image
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        if len(gt.get("messages", [])) < MIN_MESSAGES:
            continue
        first = next((it["side"] for it in conv["items"] if it["kind"] == "text"), None)
        out.setdefault(conv["scenario"], []).append({
            "split": split, "image_id": conv["id"], "path": f"data/E4/{split}/{m['path']}",
            "template": conv["template"], "first_side": first, "n_messages": len(gt["messages"])})
    return out


def main():
    scen, issues = load()
    assert not issues, issues
    val, val_la, train = pool("val"), pool("val_la"), pool("train")
    rows = []
    for sid in sorted(scen):
        rng = random.Random(f"{SEED}:{sid}:d")
        main_pool = list((val_la if sid in val_la else val).get(sid, []))
        rng.shuffle(main_pool)
        picked = main_pool[:PER_SCENARIO]
        if len(picked) < PER_SCENARIO:
            extra = list(train.get(sid, []))
            rng.shuffle(extra)
            picked += extra[: PER_SCENARIO - len(picked)]
        assert len(picked) == PER_SCENARIO, (sid, len(picked))
        for i, img in enumerate(picked):
            truth = sample_table(scen[sid], rng)
            truth["kenh"] = KENH[img["template"]]
            truth["ai_bat_dau"] = {"left": "ho_truoc", "right": "minh_truoc"}.get(img["first_side"])
            for n in FROM_CHAT:
                truth[n] = [] if FIELDS[n].multi else None
            rows.append({"id": f"{sid}__d{i:02d}", "kich_ban": sid, "nhom": scen[sid].nhom,
                         "tinh_cach": list(PERSONAS)[i % len(PERSONAS)], "anh": img,
                         "tin_mo_dau": rng.choice(OPENINGS), "bang_that": truth,
                         "tai_khoan": {k: truth[k] for k in KNOWN_AT_START}, "doc_tu_anh": list(FROM_CHAT)})
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    by_split = {}
    for r in rows:
        by_split[r["anh"]["split"]] = by_split.get(r["anh"]["split"], 0) + 1
    print(f"{len(rows)} cases -> {OUT.relative_to(ROOT)}; images by split {by_split}")


if __name__ == "__main__":
    main()
