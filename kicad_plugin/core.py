"""Core of the harness-docs plugin, kept free of any KiCad-GUI dependency so it
can be unit-tested with a mock board. The ActionPlugin (__init__.py) and the
standalone runner (__main__.py) are thin wrappers around generate_harness_docs()."""
from __future__ import annotations
import os
from dataclasses import dataclass, field

from harness.ingest import KicadBoardSource
from harness.specs import SpecStore
from harness.engine import build_harness
from harness.numbering import SCHEMES
from harness.emit import write_csv
from harness.persist import WireNumberStore, collect_numbers, WIRE_NUMBERS_NAME
from harness.review import (apply_review, load_review, review_numbers,
                            review_path, write_review)

DEFAULT_SPECS_NAME = "harness_specs.yaml"  # looked for next to the board


@dataclass
class Result:
    wire_count: int = 0
    outputs: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    review_path: str = ""


def _board_stem_and_dir(board, out_dir, stem):
    """Derive output directory + filename stem from the board file if not given."""
    if out_dir is None or stem is None:
        fname = ""
        get = getattr(board, "GetFileName", None)
        if callable(get):
            fname = get() or ""
        if fname:
            out_dir = out_dir or os.path.dirname(fname)
            stem = stem or os.path.splitext(os.path.basename(fname))[0]
    return (out_dir or os.getcwd()), (stem or "harness")


def generate_harness_docs(board, *, pcbnew_module=None, specs_path=None,
                          out_dir=None, stem=None, emit_wireviz=True,
                          render_wireviz=True) -> Result:
    res = Result()
    out_dir, stem = _board_stem_and_dir(board, out_dir, stem)

    # 1) connectivity + routed lengths from the board
    source = KicadBoardSource.from_board(board, pcbnew_module)
    conn = source.load()

    # 2) specs: prefer an explicit path, else <board_dir>/harness_specs.yaml if present.
    #    Missing PyYAML or missing file just means "defaults" -- CSV still works.
    specs = SpecStore()
    if specs_path is None:
        candidate = os.path.join(out_dir, DEFAULT_SPECS_NAME)
        specs_path = candidate if os.path.exists(candidate) else None
    if specs_path:
        try:
            specs = SpecStore.from_file(specs_path)
        except Exception as e:  # e.g. PyYAML absent, or malformed file
            res.warnings.append(f"specs '{os.path.basename(specs_path)}' not loaded: {e}")

    # 3) build (numbering scheme can be set via "numbering:" in the spec file).
    #    Wire numbers persist in <board_dir>/wire_numbers.json so they stay
    #    attached to the same wire across re-exports; commit it with the board.
    scheme = (getattr(specs, "numbering", "") or "global")
    numberer = SCHEMES.get(scheme, SCHEMES["global"])()
    review_csv = review_path(out_dir, stem)
    res.review_path = review_csv
    review_rows, review_warns = load_review(review_csv)
    res.warnings.extend(review_warns)

    store = WireNumberStore(os.path.join(out_dir, WIRE_NUMBERS_NAME))
    known = store.load()
    known.update(review_numbers(review_rows))  # review CSV is the editable front door
    harness, warns = build_harness(conn, specs, numberer=numberer,
                                   known_numbers=known)
    res.warnings.extend(warns)
    res.warnings.extend(apply_review(harness, review_rows))
    res.wire_count = len(harness.wires)
    store.save(collect_numbers(harness))
    if store.warning:
        res.warnings.append(store.warning)
    else:
        res.outputs.append(store.path)

    # 4) outputs, written next to the board
    csv_path = os.path.join(out_dir, f"{stem}_wirelist.csv")
    write_csv(harness, csv_path)
    res.outputs.append(csv_path)

    write_review(harness, review_csv, review_rows)
    res.outputs.append(review_csv)

    if emit_wireviz:
        try:
            from harness.emit import write_wireviz
            wv_path = os.path.join(out_dir, f"{stem}_harness.yaml")
            write_wireviz(harness, wv_path, components=conn.components)
            res.outputs.append(wv_path)
            if render_wireviz:
                try:
                    from harness.wireviz import render_wireviz as _render_wireviz
                    res.outputs.extend(_render_wireviz(wv_path))
                except Exception as e:
                    # Graphviz is an external executable, so KiCad installations
                    # without it still get the YAML without a noisy warning.
                    if "Graphviz" not in str(e) and "dot" not in str(e):
                        res.warnings.append(f"WireViz render skipped: {e}")
        except Exception as e:  # PyYAML absent -> skip, don't fail the CSV
            res.warnings.append(f"WireViz YAML skipped: {e}")

    # 5) panel wiring diagram (SVG) from board geometry; skipped when the
    #    board has nothing drawable (e.g. mocked boards without geometry)
    try:
        from harness.emit import write_panel_svg
        geo = source.load_geometry()
        if geo.footprints or geo.tracks:
            svg_path = os.path.join(out_dir, f"{stem}_panel.svg")
            write_panel_svg(harness, geo, svg_path)
            res.outputs.append(svg_path)
    except Exception as e:
        res.warnings.append(f"panel diagram skipped: {e}")

    return res
