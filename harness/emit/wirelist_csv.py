"""Emit the point-to-point wire list a harness manufacturer wants."""
from __future__ import annotations
import csv
from ..model import Harness

BASE_COLUMNS = ["cable", "conductor", "wire_no", "gauge", "color", "netclass",
                "from_ref", "from_pin", "to_ref", "to_pin", "net", "length_mm"]


def write_csv(harness: Harness, path: str) -> None:
    # Any 'extra' keys (conductors, shield, ...) become extra columns.
    extra_keys = sorted({k for w in harness.wires for k in (w.spec.extra or {})})
    columns = BASE_COLUMNS + extra_keys
    rows = []
    for w in harness.wires:
        row = {
            "cable": w.spec.cable, "conductor": w.spec.conductor,
            "wire_no": w.spec.wire_no,
            "gauge": w.spec.gauge, "color": w.spec.color,
            "netclass": w.netclass,
            "from_ref": w.a.ref, "from_pin": w.a.pin,
            "to_ref": w.b.ref, "to_pin": w.b.pin,
            "net": w.net, "length_mm": w.spec.length_mm,
        }
        for k in extra_keys:
            row[k] = w.spec.extra.get(k, "")
        rows.append(row)
    rows.sort(key=lambda r: (r["cable"], r["wire_no"]))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=columns)
        wr.writeheader(); wr.writerows(rows)
