#!/usr/bin/env python3
"""Build the folder that goes to Google Drive: ../drive_upload/pretransfer-data/

  README.md   what each set is, with file counts taken from the folder itself
  preview/    one contact sheet per image set + a few full-size samples with their labels,
              to see what the data looks like without downloading it
  data/       the datasets only: images, labels, manifests, sources

The working copy `data/` (ignored by git) stays on our machines and also holds experiment outputs: per-image model
outputs, cost and call logs. Those are NOT exported (see EXCLUDE), and neither is data/app (each machine's SQLite).

  python3 scripts/export_data.py [--out DIR]      needs Pillow and rsync; rerun any time, only changes are copied
Teammates: download `data/` from Drive and put it at the repo root.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
TILE_W, TILE_H, CAPTION_H = 260, 520, 18

# key, folder under data/, what it is, images picked for the sheet (None = evenly spaced), tiles, columns
SETS = [
    ("E1", "E1", "30 chats rendered from HTML (Zalo, Messenger, SMS look) x 6 variants: orig, dark, crop, jpeg40, "
     "half, blur. Labels are exact.", [f"{s}_00__{v}" for s in ("zalo", "messenger", "sms")
                                       for v in ("orig", "dark", "crop", "jpeg40", "half", "blur")], 18, 6),
    ("E1b_hard", "E1b", "Harder versions: chuplai = photo of a screen, nen2 = saved twice as JPEG, nho33 = shrunk to "
     "33%, dai = long chat.", [f"{s}_00__{v}" for s in ("zalo", "messenger", "sms")
                               for v in ("chuplai", "nen2", "nho33")]
     + ["zalo_L00__dai", "messenger_L01__dai", "sms_L02__dai"], 12, 6),
    ("gen", "E1b/gen", "Screenshots made by an image model. `intended` = the strings we asked for, `gt` = labels "
     "checked by eye.", None, 12, 6),
    ("gen_ref", "E1b/gen_ref", "Screenshots made by an image model from a real screenshot as reference (`ref` in "
     "manifest.jsonl), with new made-up strings. `intended` = the strings we asked for.", None, 12, 6),
    ("web_real", "E1b/real", "Real scam chats/SMS published by police and news sites; each gt has the source URL. "
     "Evaluation only: never train on them, never republish.", None, 18, 6),
    ("E4_train", "E4/train", "Training screenshots for the image-to-JSON model: 7 app templates, 13 scenarios, "
     "random damage (crop, JPEG, photo, long, stitched) and publisher marks. `gt` = labels with boxes, `target` = "
     "the exact JSON the model must output.", None, 24, 8),
    ("E4_val", "E4/val", "Same recipe as E4/train, separate random stream.", None, 8, 8),
    ("E4_val_la", "E4/val_la", "Held out: WhatsApp template and two scam scenarios that never appear in "
     "E4/train.", None, 8, 8),
]
OTHER = [  # folder under data/, what it is
    ("E6", "cases.jsonl: simulated user stories with the true scenario, one JSON per line, for the small text "
     "classifier (M3)."),
    ("narr/real", "Scam cases from news and police reports: source URL, verbatim quote, summary, a first-person "
     "retelling from just before the transfer, scenario label."),
]
# Experiment outputs and logs: kept in the working copy only.
EXCLUDE = ["/app/", "__pycache__/", "runs/", "web_runs/", "ocr/", "open/", "env.json", "calls.jsonl", "*cost.json",
           "render_log.jsonl", "failures.jsonl", "review_summary.json"]


def images_of(folder: Path) -> list[Path]:
    return sorted(p for p in (folder / "images").iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))


def pick(imgs: list[Path], wanted, n: int) -> list[Path]:
    if wanted:
        by_stem = {p.stem: p for p in imgs}
        return [by_stem[w] for w in wanted if w in by_stem][:n]
    step = max(1, len(imgs) // n)
    return imgs[::step][:n]


def contact_sheet(paths: list[Path], cols: int, dest: Path):
    rows = -(-len(paths) // cols)
    sheet = Image.new("RGB", (cols * TILE_W, rows * (TILE_H + CAPTION_H)), "#777")
    draw = ImageDraw.Draw(sheet)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((TILE_W - 4, TILE_H - 4))
        x, y = (i % cols) * TILE_W, (i // cols) * (TILE_H + CAPTION_H)
        sheet.paste(im, (x + (TILE_W - im.width) // 2, y + 2))
        draw.text((x + 4, y + TILE_H + 2), p.name, fill="white")
    sheet.save(dest, quality=85)


def copy_samples(folder: Path, imgs: list[Path], dest: Path):
    """Two full-size images with every label file that belongs to them."""
    dest.mkdir(parents=True, exist_ok=True)
    for p in imgs[:2]:
        shutil.copy2(p, dest / p.name)
        for sub in ("gt", "target", "intended"):
            label = folder / sub / f"{p.stem}.json"
            if label.exists():
                shutil.copy2(label, dest / f"{p.stem}.{sub}.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO.parent / "drive_upload" / "pretransfer-data"))
    out = Path(ap.parse_args().out)
    data, preview = REPO / "data", out / "preview"
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsync", "-a", "--delete", "--delete-excluded", *[f"--exclude={e}" for e in EXCLUDE],
                    f"{data}/", f"{out / 'data'}/"], check=True)
    shutil.rmtree(preview, ignore_errors=True)
    (preview / "samples").mkdir(parents=True)

    rows = []
    for i, (key, sub, what, wanted, n, cols) in enumerate(SETS, 1):
        folder = data / sub
        imgs = images_of(folder)
        chosen = pick(imgs, wanted, n)
        sheet = f"{i:02d}_{key}.jpg"
        contact_sheet(chosen, cols, preview / sheet)
        copy_samples(folder, pick(imgs, None, 2), preview / "samples" / key)
        rows.append(f"| `data/{sub}/` | {len(imgs)} images | {what} | `preview/{sheet}`, `preview/samples/{key}/` |")
    for sub, what in OTHER:
        folder = data / sub
        files = sorted(p for p in folder.iterdir() if p.is_file())
        dest = preview / "samples" / sub.replace("/", "_")
        dest.mkdir(parents=True)
        jsons = [f for f in files if f.suffix == ".json" and f.name != "cost.json"]
        size = f"{len(jsons)} cases"
        for p in files:
            if p.suffix == ".jsonl":
                lines = p.read_text(encoding="utf-8").splitlines()
                size = f"{len(lines)} lines"
                (dest / f"{p.stem}.first3.json").write_text(
                    json.dumps([json.loads(x) for x in lines[:3]], ensure_ascii=False, indent=1), encoding="utf-8")
        for p in jsons[:2]:
            shutil.copy2(p, dest / p.name)
        rows.append(f"| `data/{sub}/` | {size} | {what} | `preview/samples/{dest.name}/` |")

    total = sum(1 for p in (out / "data").rglob("*") if p.is_file())
    (out / "README.md").write_text("\n".join([
        "# Pretransfer Scam Assistant: data", "",
        "Code: https://github.com/Min-KiD/pretransfer-scam-assistant", "",
        "- `preview/`: look here first. One contact sheet per image set, plus two full-size samples per set with "
        "their label files.",
        f"- `data/`: the datasets ({total} files): images, labels, manifests. Download it and put it at the repo "
        "root. Model outputs and experiment logs are not shared here; results are summarised in the repo.", "",
        "No real user data. Account numbers, phone numbers and names in generated sets are made up. The real "
        "screenshots and cases come from published police and news pages.", "",
        "| Folder | Size | What it is | Preview |", "|---|---|---|---|", *rows, "",
        "Made by `scripts/export_data.py`.", ""]), encoding="utf-8")
    print(subprocess.run(["du", "-sh", str(out / "data"), str(preview)], capture_output=True, text=True).stdout)


if __name__ == "__main__":
    main()
