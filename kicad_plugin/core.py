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

DEFAULT_SPECS_NAME = "harness_specs.yaml"  # looked for next to the board


@dataclass
class Result:
    wire_count: int = 0
    outputs: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


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
                          out_dir=None, stem=None, emit_wireviz=True) -> Result:
    res = Result()
    out_dir, stem = _board_stem_and_dir(board, out_dir, stem)

    # 1) connectivity + routed lengths from the board
    conn = KicadBoardSource.from_board(board, pcbnew_module).load()

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
    store = WireNumberStore(os.path.join(out_dir, WIRE_NUMBERS_NAME))
    harness, warns = build_harness(conn, specs, numberer=numberer,
                                   known_numbers=store.load())
    res.warnings.extend(warns)
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

    if emit_wireviz:
        try:
            from harness.emit import write_wireviz
            wv_path = os.path.join(out_dir, f"{stem}_harness.yaml")
            write_wireviz(harness, wv_path, components=conn.components)
            res.outputs.append(wv_path)
        except Exception as e:  # PyYAML absent -> skip, don't fail the CSV
            res.warnings.append(f"WireViz YAML skipped: {e}")

    return res
