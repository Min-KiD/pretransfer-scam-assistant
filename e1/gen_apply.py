"""Turn the eye-checked review of the 'gen' set into ground truth.

Input:  data/E1b/gen/intended/<id>.json (what the prompt asked for), data/E1b/gen/calls.jsonl (cost),
        e1/gen_review.json (written by hand after opening every image), keyed by image id:
          {"drop": "reason"}                      image removed (no string left that can be read for sure)
          {"fix": {type: {intended_raw: shown_raw}}, "remove": {type: [intended_raw, ...]},
           "add": {type: [shown_raw, ...]}, "ambiguous": {type: [intended_raw, ...]}, "note": "..."}
          all keys optional; {} = every string matches; "ambiguous" = kept, but I/l look identical in that font
Output: data/E1b/gen/gt/<id>.json, data/E1b/gen/manifest.jsonl, data/E1b/gen/review_summary.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from e1.gen_nb import MODEL
from e1.scenarios import NORMALIZERS

TYPES = ("account", "phone", "link", "amount")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", default="data/E1b/gen")
    ap.add_argument("--review", default="e1/gen_review.json")
    args = ap.parse_args()
    gen = Path(args.gen)
    review = json.loads(Path(args.review).read_text(encoding="utf-8"))
    (gen / "gt").mkdir(exist_ok=True)
    for old in (gen / "gt").glob("*.json"):
        old.unlink()
    intended = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((gen / "intended").glob("*.json"))}
    images = {p.stem: p for p in (gen / "images").iterdir()}
    missing = sorted(set(images) - set(review))
    if missing:
        raise SystemExit(f"not reviewed yet: {missing}")
    stats = dict(fixed_images=0, fixed_strings=0, dropped_strings=0, added_strings=0, dropped_images=0,
                 ambiguous_strings=0)
    manifest, dropped = [], {}
    for iid in sorted(images):
        rv, gt = review[iid], intended[iid]
        if "drop" in rv:
            stats["dropped_images"] += 1
            dropped[iid] = rv["drop"]
            continue
        changed = False
        for t in TYPES:
            fix, rem = rv.get("fix", {}).get(t, {}), set(rv.get("remove", {}).get(t, []))
            amb = set(rv.get("ambiguous", {}).get(t, []))
            stats["ambiguous_strings"] += len(amb)
            unknown = (set(fix) | rem | amb) - {e["raw"] for e in gt["strings"][t]}
            if unknown:
                raise SystemExit(f"{iid} {t}: review names strings that are not in the intended answer: {unknown}")
            out = []
            for e in gt["strings"][t]:
                if e["raw"] in rem:
                    stats["dropped_strings"] += 1
                    changed = True
                    continue
                if e["raw"] in fix:
                    e = {"raw": fix[e["raw"]], "norm": NORMALIZERS[t](fix[e["raw"]]), "intended": e["raw"]}
                    stats["fixed_strings"] += 1
                    changed = True
                out.append(e)
            for raw in rv.get("add", {}).get(t, []):
                out.append({"raw": raw, "norm": NORMALIZERS[t](raw), "added_in_review": True})
                stats["added_strings"] += 1
                changed = True
            gt["strings"][t] = out
        if not any(gt["strings"][t] for t in TYPES):
            stats["dropped_images"] += 1
            dropped[iid] = "no string left after review"
            continue
        stats["fixed_images"] += changed
        gt["review_note"] = rv.get("note", "")
        (gen / "gt" / f"{iid}.json").write_text(json.dumps(gt, ensure_ascii=False, indent=1), encoding="utf-8")
        manifest.append({"image_id": iid, "base_id": gt["base_id"], "style": gt["style"], "variant": gt["variant"],
                         "scenario": gt["scenario"], "path": f"images/{images[iid].name}"})
    with open(gen / "manifest.jsonl", "w", encoding="utf-8") as f:
        for m in manifest:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    calls = [json.loads(l) for l in open(gen / "calls.jsonl", encoding="utf-8")]
    summary = dict(model=MODEL, generated=len(images), calls=len(calls), usd=round(sum(c["usd"] for c in calls), 3),
                   kept=len(manifest), dropped=dropped, **stats)
    (gen / "review_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
