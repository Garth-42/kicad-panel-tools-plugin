"""Command-line front end. Wraps: ingest -> engine -> emit."""
from __future__ import annotations
import argparse, os, sys
from .ingest import KicadNetlistSource
from .specs import SpecStore
from .engine import build_harness
from .emit import write_csv, write_wireviz
from .numbering import SCHEMES
from .persist import WireNumberStore, collect_numbers, WIRE_NUMBERS_NAME


def main(argv=None):
    p = argparse.ArgumentParser(prog="harness", description="KiCad -> wire-harness docs.")
    p.add_argument("netlist", help="KiCad netlist XML (kicad-cli sch export netlist --format kicadxml)")
    p.add_argument("--specs", help="YAML of per-net wire specs (gauge/color/length/cable/no)")
    p.add_argument("--csv", default="wirelist.csv", help="output wire-list CSV")
    p.add_argument("--wireviz", help="also emit a WireViz YAML to this path")
    p.add_argument("--numbering", choices=list(SCHEMES), default="global",
                   help="wire-numbering scheme: global | cable | net (IEC equipotential) | srcdst")
    p.add_argument("--no-autonumber", action="store_true", help="do not auto-assign wire numbers")
    p.add_argument("--numbers", metavar="JSON",
                   help=f"wire-number store (default: {WIRE_NUMBERS_NAME} next to the netlist)")
    p.add_argument("--no-persist", action="store_true",
                   help="do not load/save the wire-number store")
    args = p.parse_args(argv)

    conn = KicadNetlistSource(args.netlist).load()
    specs = SpecStore.from_file(args.specs) if args.specs else SpecStore()
    numberer = SCHEMES[args.numbering]()

    store = None
    known: dict = {}
    if not args.no_persist and not args.no_autonumber:
        store = WireNumberStore(args.numbers or os.path.join(
            os.path.dirname(os.path.abspath(args.netlist)), WIRE_NUMBERS_NAME))
        known = store.load()

    harness, warnings = build_harness(conn, specs,
                                      auto_number=not args.no_autonumber,
                                      numberer=numberer,
                                      known_numbers=known)
    if store is not None:
        store.save(collect_numbers(harness))
        if store.warning:
            warnings.append(store.warning)
        else:
            print(f"wire numbers persisted -> {store.path}")

    write_csv(harness, args.csv)
    print(f"{len(harness.wires)} wires -> {args.csv}")
    if args.wireviz:
        write_wireviz(harness, args.wireviz, components=conn.components)
        print(f"WireViz YAML -> {args.wireviz}  (render: wireviz {args.wireviz})")
    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
