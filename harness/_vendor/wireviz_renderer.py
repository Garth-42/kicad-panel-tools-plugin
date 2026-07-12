"""Tiny vendored WireViz-compatible renderer fallback.

This is not the full upstream WireViz project. It renders the subset emitted by
``harness.emit.wireviz_yaml`` so the KiCad plugin can create diagram/BOM files
without installing the WireViz Python package. Graphviz ``dot`` is still needed
for PNG/SVG images.
"""
from __future__ import annotations

import csv
import html
import os
import shutil
import subprocess


def _q(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def _pin_label(pin):
    return str(pin)


def _edge_rows(data):
    connectors = data.get("connectors", {}) or {}
    cables = data.get("cables", {}) or {}
    for cs in data.get("connections", []) or []:
        if len(cs) != 3:
            continue
        left, cable, right = cs
        l_ref, l_pins = next(iter(left.items()))
        c_ref, c_idxs = next(iter(cable.items()))
        r_ref, r_pins = next(iter(right.items()))
        idx = c_idxs[0]
        cable_data = cables.get(c_ref, {}) or {}
        labels = cable_data.get("wirelabels") or []
        colors = cable_data.get("colors") or []
        label = labels[idx - 1] if isinstance(idx, int) and idx <= len(labels) else str(idx)
        color = colors[idx - 1] if isinstance(idx, int) and idx <= len(colors) else ""
        yield {
            "left": l_ref,
            "left_pin": _pin_label(l_pins[0]),
            "cable": c_ref,
            "index": idx,
            "right": r_ref,
            "right_pin": _pin_label(r_pins[0]),
            "label": label,
            "color": color,
            "left_type": (connectors.get(l_ref, {}) or {}).get("type", l_ref),
            "right_type": (connectors.get(r_ref, {}) or {}).get("type", r_ref),
        }


def _dot(data):
    lines = [
        "graph harness {",
        "  graph [rankdir=LR];",
        "  node [shape=box, style=rounded, fontname=Helvetica];",
        "  edge [fontname=Helvetica];",
    ]
    for ref, connector in (data.get("connectors", {}) or {}).items():
        label = f"{ref}\\n{(connector or {}).get('type', ref)}"
        lines.append(f"  {_q(ref)} [label={_q(label)}];")
    for row in _edge_rows(data):
        label = f"{row['cable']}:{row['label']} ({row['left_pin']}↔{row['right_pin']})"
        lines.append(f"  {_q(row['left'])} -- {_q(row['right'])} [label={_q(label)}];")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _write_bom(data, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["qty", "designators", "type", "manufacturer", "mpn"])
        for ref, connector in (data.get("connectors", {}) or {}).items():
            connector = connector or {}
            writer.writerow([1, ref, connector.get("type", ref), connector.get("manufacturer", ""), connector.get("mpn", "")])
        for ref, cable in (data.get("cables", {}) or {}).items():
            cable = cable or {}
            desc = f"{cable.get('wirecount', '')} core cable".strip()
            writer.writerow([1, ref, desc, "", ""])


def _write_html(data, svg_path, bom_path, html_path):
    svg = open(svg_path, encoding="utf-8").read() if os.path.exists(svg_path) else ""
    bom = open(bom_path, encoding="utf-8").read() if os.path.exists(bom_path) else ""
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset='utf-8'><title>Harness</title>")
        fh.write("<h1>Harness diagram</h1>")
        fh.write(svg)
        fh.write("<h2>BOM</h2><pre>")
        fh.write(html.escape(bom))
        fh.write("</pre>")


def render(data, yaml_path):
    dot = shutil.which("dot")
    if not dot:
        raise RuntimeError("Graphviz 'dot' not found; install Graphviz to render WireViz diagrams")
    stem, _ = os.path.splitext(yaml_path)
    dot_path = stem + ".gv"
    svg_path = stem + ".svg"
    png_path = stem + ".png"
    bom_path = stem + ".bom.tsv"
    html_path = stem + ".html"
    with open(dot_path, "w", encoding="utf-8") as fh:
        fh.write(_dot(data))
    for fmt, out in (("svg", svg_path), ("png", png_path)):
        proc = subprocess.run([dot, f"-T{fmt}", dot_path, "-o", out], capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip() or f"dot failed rendering {fmt}")
    _write_bom(data, bom_path)
    _write_html(data, svg_path, bom_path, html_path)
    return [png_path, svg_path, html_path, bom_path]
