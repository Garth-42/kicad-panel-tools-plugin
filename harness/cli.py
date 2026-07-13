"""Command-line front end. Wraps: ingest -> engine -> emit."""
from __future__ import annotations
import argparse, os, sys
from .ingest import KicadNetlistSource
from .specs import SpecStore
from .engine import build_harness
from .emit import write_csv, write_wireviz
from .numbering import SCHEMES
from .persist import WireNumberStore, collect_numbers, legacy_keys, WIRE_NUMBERS_NAME
from .review import apply_review, load_review, review_numbers, write_review


def main(argv=None):
    p = argparse.ArgumentParser(prog="harness", description="KiCad -> wire-harness docs.")
    p.add_argument("netlist", help="KiCad netlist XML (kicad-cli sch export netlist --format kicadxml)")
    p.add_argument("--specs", help="YAML of per-net wire specs (gauge/color/length/cable/no)")
    p.add_argument("--csv", default="wirelist.csv", help="output wire-list CSV")
    p.add_argument("--wireviz", help="also emit a WireViz YAML to this path")
    p.add_argument("--render-wireviz", action="store_true",
                   help="render WireViz PNG/SVG/HTML/BOM outputs after writing YAML")
    p.add_argument("--numbering", choices=list(SCHEMES), default=None,
                   help="wire-numbering scheme: global | cable | net (IEC equipotential)"
                        " | srcdst | group (default: the spec file's 'numbering:', else global)")
    p.add_argument("--no-autonumber", action="store_true", help="do not auto-assign wire numbers")
    p.add_argument("--numbers", metavar="JSON",
                   help=f"wire-number store (default: {WIRE_NUMBERS_NAME} next to the netlist)")
    p.add_argument("--no-persist", action="store_true",
                   help="do not load/save the wire-number store")
    p.add_argument("--renumber", action="store_true",
                   help="discard persisted wire numbers (store + review wire_no column)"
                        " and reassign everything with the chosen scheme")
    p.add_argument("--review", metavar="CSV",
                   help="editable wire review CSV to load and rewrite")
    args = p.parse_args(argv)

    conn = KicadNetlistSource(args.netlist).load()
    specs = SpecStore.from_file(args.specs) if args.specs else SpecStore()
    spec_scheme = specs.numbering if specs.numbering in SCHEMES else ""
    numberer = SCHEMES[args.numbering or spec_scheme or "global"]()

    review_rows, review_warnings = load_review(args.review) if args.review else ({}, [])
    if args.renumber:
        # Fresh numbers must not be resurrected via the review table; the
        # other edited columns (notes, gauge, ...) are kept.
        review_rows = {k: dict(row, wire_no="") for k, row in review_rows.items()}

    store = None
    known: dict = {}
    if not args.no_persist and not args.no_autonumber:
        store = WireNumberStore(args.numbers or os.path.join(
            os.path.dirname(os.path.abspath(args.netlist)), WIRE_NUMBERS_NAME))
        if not args.renumber:
            known = store.load()
    known.update(review_numbers(review_rows))

    harness, warnings = build_harness(conn, specs,
                                      auto_number=not args.no_autonumber,
                                      numberer=numberer,
                                      known_numbers=known)
    warnings.extend(review_warnings)
    warnings.extend(apply_review(harness, review_rows))

    if store is not None:
        # A renumber rewrites the store instead of merging, dropping entries
        # for absent nets (a kept one could collide with a fresh number later).
        # Legacy net-name entries for wires being saved are dropped — those
        # wires now live under their endpoint keys.
        store.save(collect_numbers(harness), keep_existing=not args.renumber,
                   drop=legacy_keys(harness))
        if store.warning:
            warnings.append(store.warning)
        else:
            print(f"wire numbers persisted -> {store.path}")

    write_csv(harness, args.csv)
    print(f"{len(harness.wires)} wires -> {args.csv}")
    if args.review:
        write_review(harness, args.review, review_rows)
        print(f"wire review table -> {args.review}")
    if args.wireviz:
        write_wireviz(harness, args.wireviz, components=conn.components)
        print(f"WireViz YAML -> {args.wireviz}")
        if args.render_wireviz:
            from .wireviz import render_wireviz
            for out in render_wireviz(args.wireviz):
                print(f"WireViz render -> {out}")
    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
