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
    scheme: str = ""       # numbering scheme this run actually used


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


def _build_numbered_harness(board, pcbnew_module, specs_path, out_dir, stem, res,
                            reclaim_net_name_numbers=False, scheme=None,
                            renumber=False):
    """`scheme` overrides the spec file's `numbering:` for this run only;
    `renumber` discards persisted numbers (store + review `wire_no`) so the
    scheme reassigns everything from scratch. Explicit `nets:` numbers and
    intrinsic cable-core labels still win — they aren't persistence."""
    source = KicadBoardSource.from_board(board, pcbnew_module)
    conn = source.load()

    specs = SpecStore()
    if specs_path is None:
        candidate = os.path.join(out_dir, DEFAULT_SPECS_NAME)
        specs_path = candidate if os.path.exists(candidate) else None
    if specs_path:
        try:
            specs = SpecStore.from_file(specs_path)
        except Exception as e:
            res.warnings.append(f"specs '{os.path.basename(specs_path)}' not loaded: {e}")

    spec_scheme = (getattr(specs, "numbering", "") or "global")
    if scheme is not None and scheme not in SCHEMES:
        res.warnings.append(f"unknown numbering scheme {scheme!r}; "
                            f"using {spec_scheme!r}")
        scheme = None
    res.scheme = scheme or (spec_scheme if spec_scheme in SCHEMES else "global")
    if scheme and scheme != spec_scheme:
        specs_name = os.path.basename(specs_path) if specs_path else DEFAULT_SPECS_NAME
        res.warnings.append(
            f"numbering scheme '{scheme}' picked for this run only; set "
            f"'numbering: {scheme}' in {specs_name} to make it permanent")
    numberer = SCHEMES[res.scheme]()
    review_csv = review_path(out_dir, stem)
    res.review_path = review_csv
    review_rows, review_warns = load_review(review_csv)
    res.warnings.extend(review_warns)
    if renumber:
        # A renumber must not resurrect old numbers via the review table; every
        # other edited column (notes, gauge, custom ones, ...) is kept.
        review_rows = {k: dict(row, wire_no="") for k, row in review_rows.items()}

    store = WireNumberStore(os.path.join(out_dir, WIRE_NUMBERS_NAME))
    known = {} if renumber else store.load()
    known.update(review_numbers(review_rows))
    if reclaim_net_name_numbers:
        # After "apply wire numbers to net names", the store is keyed by the
        # pre-rename net names, so a renamed net would look brand new and get a
        # fresh number (P-001 -> 001 -> ... on every apply). A net whose name IS
        # a previously assigned number is that wire: let it keep its number.
        assigned = set(known.values())
        for net in conn.nets:
            name = getattr(net, "name", "") or ""
            stripped = name[1:] if name.startswith("/") else name
            if name not in known and stripped in assigned:
                known[name] = stripped
    harness, warns = build_harness(conn, specs, numberer=numberer,
                                   known_numbers=known)
    res.warnings.extend(warns)
    res.warnings.extend(apply_review(harness, review_rows))
    res.wire_count = len(harness.wires)
    # On a renumber the store is rewritten, not merged: keeping entries for
    # absent nets would let a retired number collide with a freshly issued one
    # the day that net returns.
    store.save(collect_numbers(harness), keep_existing=not renumber)
    if store.warning:
        res.warnings.append(store.warning)
    else:
        res.outputs.append(store.path)
    return source, conn, harness, review_rows


def _wire_number_net_names(harness) -> tuple[dict[str, str], list[str]]:
    by_net: dict[str, set[str]] = {}
    for w in harness.wires:
        if getattr(w.spec, "cable", ""):
            # Cable cores are identified BY their net name (<CABLE>.<core> from
            # the group bus) and already carry an intrinsic number; renaming
            # the net would destroy the cable grouping on the next run.
            continue
        number = str(w.spec.wire_no or "").strip()
        if number:
            by_net.setdefault(w.net, set()).add(number)
    names: dict[str, str] = {}
    warnings: list[str] = []
    for net, numbers in sorted(by_net.items()):
        if len(numbers) != 1:
            warnings.append(
                f"net {net!r} has multiple wire numbers ({', '.join(sorted(numbers))}); not renamed")
            continue
        number = next(iter(numbers))
        names[net] = f"/{number}" if net.startswith("/") else number
    return names, warnings


def _mapping_lookup(mapping, key):
    """Return mapping[key] across Python dicts and KiCad SWIG map wrappers."""
    if mapping is None:
        return None
    get = getattr(mapping, "get", None)
    if callable(get):
        try:
            return get(key)
        except Exception:
            pass
    try:
        return mapping[key]
    except Exception:
        return None


def _rename_net_object(obj, new_name) -> bool:
    """Rename a NETINFO-like object via its net-name setter.

    Only net-specific setter names may be tried here. In real pcbnew,
    PAD.SetName() is a legacy alias for SetNumber() — the PAD NUMBER — so a
    generic SetName fallback rewrites pad numbers instead of net names, and
    KiCad then silently DROPS a pad on save when its new number collides with
    a sibling pad's (e.g. "002" vs "2"). Never widen this list with SetName.
    """
    for method in ("SetNetname", "SetNetName"):
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                fn(new_name)
                return True
            except Exception:
                continue
    return False


def _apply_board_net_names(board, renames: dict[str, str]) -> tuple[int, list[str]]:
    changed = 0
    warnings: list[str] = []
    for old_name, new_name in renames.items():
        if old_name == new_name:
            continue
        touched = False
        nets_by_name = getattr(board, "GetNetsByName", None)
        if callable(nets_by_name):
            try:
                netinfo = _mapping_lookup(nets_by_name(), old_name)
                if netinfo is not None and _rename_net_object(netinfo, new_name):
                    touched = True
            except Exception:
                pass
        # Pads and tracks derive their net name from the shared NETINFO object,
        # so renaming that one object is both sufficient and the only safe move
        # — the items themselves must never be "renamed" (see _rename_net_object).
        for fp in (getattr(board, "GetFootprints", lambda: [])() or []):
            pads = getattr(fp, "Pads", None) or getattr(fp, "GetPads", None)
            for pad in (pads() if callable(pads) else []):
                get_name = getattr(pad, "GetNetname", None)
                if callable(get_name) and get_name() == old_name:
                    net = getattr(pad, "GetNet", lambda: None)()
                    touched = _rename_net_object(net, new_name) or touched
        for trk in (getattr(board, "GetTracks", lambda: [])() or []):
            get_name = getattr(trk, "GetNetname", None)
            if callable(get_name) and get_name() == old_name:
                net = getattr(trk, "GetNet", lambda: None)()
                touched = _rename_net_object(net, new_name) or touched
        if touched:
            changed += 1
        else:
            warnings.append(f"net {old_name!r} could not be renamed to {new_name!r}")
    for method in ("BuildListOfNets", "SynchronizeNetsAndNetClasses"):
        fn = getattr(board, method, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
    return changed, warnings


def apply_wire_names_to_board(board, *, pcbnew_module=None, specs_path=None,
                              out_dir=None, stem=None, scheme=None,
                              renumber=False) -> Result:
    res = Result()
    out_dir, stem = _board_stem_and_dir(board, out_dir, stem)
    _source, _conn, harness, review_rows = _build_numbered_harness(
        board, pcbnew_module, specs_path, out_dir, stem, res,
        reclaim_net_name_numbers=True, scheme=scheme, renumber=renumber)
    write_review(harness, res.review_path, review_rows)
    if res.review_path not in res.outputs:
        res.outputs.append(res.review_path)
    renames, rename_warnings = _wire_number_net_names(harness)
    res.warnings.extend(rename_warnings)
    changed, apply_warnings = _apply_board_net_names(board, renames)
    res.warnings.extend(apply_warnings)
    if pcbnew_module is not None:
        refresh = getattr(pcbnew_module, "Refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass
    res.outputs.append(f"{changed} board net name(s) updated")
    return res

def generate_harness_docs(board, *, pcbnew_module=None, specs_path=None,
                          out_dir=None, stem=None, emit_wireviz=True,
                          render_wireviz=True, scheme=None,
                          renumber=False) -> Result:
    res = Result()
    out_dir, stem = _board_stem_and_dir(board, out_dir, stem)

    source, conn, harness, review_rows = _build_numbered_harness(
        board, pcbnew_module, specs_path, out_dir, stem, res,
        scheme=scheme, renumber=renumber)

    # 4) outputs, written next to the board
    csv_path = os.path.join(out_dir, f"{stem}_wirelist.csv")
    write_csv(harness, csv_path)
    res.outputs.append(csv_path)

    write_review(harness, res.review_path, review_rows)
    res.outputs.append(res.review_path)

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
                    # The YAML is still written either way; say why the rendered
                    # diagram/BOM didn't appear so the default doesn't look broken.
                    if "Graphviz" in str(e) or "dot" in str(e):
                        res.warnings.append(
                            "WireViz diagram not rendered: Graphviz 'dot' not found. "
                            "Installing/importing the WireViz or Graphviz Python packages "
                            "is not enough by itself; rendering also needs the separate "
                            "Graphviz `dot` executable. Install Graphviz (graphviz.org), "
                            "restart KiCad so it receives the updated PATH, or set "
                            "KICAD_PANEL_TOOLS_DOT/GRAPHVIZ_DOT to the full `dot` path; "
                            "the WireViz YAML "
                            f"was written. Renderer detail: {e}")
                    else:
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
