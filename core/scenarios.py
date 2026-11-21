"""Load and validate the scenario library (design doc 5.3). Files are never modified here.

Checks: unique `id`, valid `nhom`, every field and value exists in core.schema, probabilities in (0, 1], single-select
fields sum to at most 1, `kho_phan_biet_voi` points to an existing id. Every problem is reported with file and line;
a file with a problem is left out of the library so the rest still loads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .schema import FIELDS, GROUPS

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "scenarios"
REQUIRED = ("id", "ten", "nhom", "mo_ta", "truong", "dau_hieu", "viec_can_kiem_tra")


@dataclass
class Scenario:
    id: str
    ten: str
    nhom: str
    mo_ta: str
    truong: dict[str, dict[str, float]]
    dau_hieu: list[str]
    viec_can_kiem_tra: list[str]
    kho_phan_biet_voi: str | None = None
    file: str = ""
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Issue:
    file: str
    line: int
    msg: str

    def __str__(self):
        return f"{self.file}:{self.line}: {self.msg}"


def _node_get(node, key):
    """(key_node, value_node) of a YAML mapping node, or (None, None)."""
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            if k.value == key:
                return k, v
    return None, None


def _line(n) -> int:
    return n.start_mark.line + 1 if n is not None else 1


def _check_file(path: Path) -> tuple[dict | None, list[Issue]]:
    rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    text = path.read_text(encoding="utf-8")
    try:
        node = yaml.compose(text)
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        return None, [Issue(rel, mark.line + 1 if mark else 1, f"YAML lỗi cú pháp: {e}")]
    if not isinstance(data, dict):
        return None, [Issue(rel, 1, "file không phải một mapping YAML")]
    issues = [Issue(rel, 1, f"thiếu khóa `{k}`") for k in REQUIRED if k not in data]
    if data.get("nhom") not in GROUPS:
        issues.append(Issue(rel, _line(_node_get(node, "nhom")[1]), f"nhom `{data.get('nhom')}` không thuộc {GROUPS}"))
    _, tnode = _node_get(node, "truong")
    for fname, probs in (data.get("truong") or {}).items():
        kn, vn = _node_get(tnode, fname)
        if fname not in FIELDS:
            issues.append(Issue(rel, _line(kn), f"trường `{fname}` không có trong schema"))
            continue
        f = FIELDS[fname]
        if not isinstance(probs, dict) or not probs:
            issues.append(Issue(rel, _line(kn), f"`{fname}` phải là mapping giá trị: xác suất"))
            continue
        for val, p in probs.items():
            vk, _ = _node_get(vn, val)
            if val not in f.values:
                issues.append(Issue(rel, _line(vk), f"`{fname}`: giá trị `{val}` không có trong schema"))
            if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 < p <= 1:
                issues.append(Issue(rel, _line(vk), f"`{fname}.{val}`: xác suất {p!r} ngoài (0, 1]"))
        if not f.multi:
            s = sum(p for p in probs.values() if isinstance(p, (int, float)))
            if s > 1 + 1e-9:
                issues.append(Issue(rel, _line(kn), f"`{fname}` chọn một nhưng tổng xác suất {s:.3f} > 1"))
    return data, issues


def load(directory: Path = SCENARIO_DIR) -> tuple[dict[str, Scenario], list[Issue]]:
    """All valid scenarios by id, plus every problem found (bad files are skipped, never edited)."""
    scenarios, issues, seen = {}, [], {}
    files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    parsed = []
    for p in files:
        data, iss = _check_file(p)
        issues += iss
        if data is None:
            continue
        rel = iss[0].file if iss else (str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p))
        sid = data.get("id")
        if sid in seen:
            issues.append(Issue(rel, _line(_node_get(yaml.compose(p.read_text(encoding="utf-8")), "id")[1]),
                                f"id `{sid}` trùng với {seen[sid]}"))
            continue
        seen[sid] = rel
        parsed.append((p, rel, data, not iss))
    for p, rel, data, ok in parsed:
        ref = data.get("kho_phan_biet_voi")
        if ref is not None and ref not in seen:
            node = yaml.compose(p.read_text(encoding="utf-8"))
            issues.append(Issue(rel, _line(_node_get(node, "kho_phan_biet_voi")[1]),
                                f"kho_phan_biet_voi `{ref}` không trỏ tới id nào"))
            ok = False
        if not ok:
            continue
        scenarios[data["id"]] = Scenario(
            id=data["id"], ten=data["ten"], nhom=data["nhom"], mo_ta=" ".join(str(data["mo_ta"]).split()),
            truong={k: {vk: float(vv) for vk, vv in v.items()} for k, v in data["truong"].items()},
            dau_hieu=list(data["dau_hieu"]), viec_can_kiem_tra=list(data["viec_can_kiem_tra"]),
            kho_phan_biet_voi=ref, file=rel, raw=data)
    return scenarios, issues


if __name__ == "__main__":
    sc, iss = load()
    print(f"{len(sc)} kịch bản hợp lệ: " + ", ".join(sorted(sc)))
    for i in iss:
        print("LỖI", i)
