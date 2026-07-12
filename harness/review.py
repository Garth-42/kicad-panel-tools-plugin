"""Editable wire review table support.

The review CSV is a user-facing companion to the generated wire list.  It is
keyed by the same stable wire ids as wire_numbers.json, so users can edit wire
numbers (and notes/metadata) without copying KiCad-generated net names into
harness_specs.yaml.
"""
from __future__ import annotations
import csv
import os

from .persist import wire_key

REVIEW_SUFFIX = "_wire_review.csv"
GENERATED_COLUMNS = [
    "key", "wire_no", "from_ref", "from_pin", "to_ref", "to_pin", "net",
    "netclass", "cable", "conductor", "gauge", "color", "length_mm", "notes",
]
EDITABLE_COLUMNS = {"wire_no", "cable", "conductor", "gauge", "color", "notes"}


def review_path(out_dir: str, stem: str) -> str:
    return os.path.join(out_dir, f"{stem}{REVIEW_SUFFIX}")


def wire_keys(harness) -> dict:
    """Return {id(wire): stable_key} for every wire in a harness."""
    per_net: dict = {}
    for w in harness.wires:
        per_net.setdefault(w.net, []).append(w)
    out: dict = {}
    for net_name, wires in per_net.items():
        for w in wires:
            out[id(w)] = wire_key(net_name, w.b if len(wires) > 1 else None)
    return out


def load_review(path: str) -> tuple[dict, list[str]]:
    """Load an existing review table as {key: row}; fail soft with warnings."""
    if not path or not os.path.exists(path):
        return {}, []
    warnings: list[str] = []
    rows: dict = {}
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            for row_num, row in enumerate(csv.DictReader(fh), start=2):
                key = (row.get("key") or "").strip()
                if not key:
                    warnings.append(f"review row {row_num} has no key; skipped")
                    continue
                if key in rows:
                    warnings.append(f"review key {key!r} appears more than once; last row wins")
                rows[key] = {k: (v or "") for k, v in row.items() if k is not None}
    except Exception as e:
        warnings.append(f"wire review table '{os.path.basename(path)}' not loaded: {e}")
        return {}, warnings
    return rows, warnings


def review_numbers(review_rows: dict) -> dict:
    return {k: str(v.get("wire_no", "")).strip()
            for k, v in review_rows.items() if str(v.get("wire_no", "")).strip()}


def apply_review(harness, review_rows: dict) -> list[str]:
    """Apply editable review-table fields to matching wires."""
    warnings: list[str] = []
    keys = wire_keys(harness)
    seen = set()
    used_numbers: dict = {}
    for w in harness.wires:
        key = keys[id(w)]
        row = review_rows.get(key)
        if not row:
            continue
        seen.add(key)
        for field in ("wire_no", "cable", "conductor", "gauge", "color"):
            value = str(row.get(field, "")).strip()
            if value:
                setattr(w.spec, field, value)
        note = str(row.get("notes", "")).strip()
        if note:
            w.spec.extra = dict(w.spec.extra or {})
            w.spec.extra["notes"] = note
        if w.spec.wire_no:
            used_numbers.setdefault(w.spec.wire_no, []).append(key)
    for number, owners in sorted(used_numbers.items()):
        if len(owners) > 1:
            warnings.append(f"duplicate wire number {number!r} in review/table result: {', '.join(owners)}")
    stale = sorted(set(review_rows) - seen)
    for key in stale:
        warnings.append(f"review key {key!r} no longer exists in this design")
    return warnings


def write_review(harness, path: str, previous_rows: dict | None = None) -> None:
    """Write a merged review table, preserving editable/custom columns by key."""
    previous_rows = previous_rows or {}
    keys = wire_keys(harness)
    custom_cols = []
    for row in previous_rows.values():
        for col in row:
            if col not in GENERATED_COLUMNS and col not in custom_cols:
                custom_cols.append(col)
    columns = GENERATED_COLUMNS + custom_cols
    rows = []
    for w in harness.wires:
        key = keys[id(w)]
        previous = previous_rows.get(key, {})
        row = {
            "key": key,
            "wire_no": previous.get("wire_no") or w.spec.wire_no,
            "from_ref": w.a.ref, "from_pin": w.a.pin,
            "to_ref": w.b.ref, "to_pin": w.b.pin,
            "net": w.net, "netclass": w.netclass,
            "cable": previous.get("cable") or w.spec.cable,
            "conductor": previous.get("conductor") or w.spec.conductor,
            "gauge": previous.get("gauge") or w.spec.gauge,
            "color": previous.get("color") or w.spec.color,
            "length_mm": w.spec.length_mm,
            "notes": previous.get("notes") or (w.spec.extra or {}).get("notes", ""),
        }
        for col in custom_cols:
            row[col] = previous.get(col, "")
        rows.append(row)
    rows.sort(key=lambda r: (r["cable"], r["wire_no"], r["from_ref"], r["from_pin"]))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=columns)
        wr.writeheader(); wr.writerows(rows)
