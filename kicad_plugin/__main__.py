"""Standalone / headless runner, so you can test without clicking in the GUI:

    <kicad-python> -m kicad_plugin path/to/board.kicad_pcb

Use KiCad's bundled Python (the one that can `import pcbnew`). Run from the repo
root so `kicad_plugin` and `harness` are both importable.
"""
import argparse
import sys

from harness.numbering import SCHEMES

from .core import generate_harness_docs


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m kicad_plugin",
        description="Headless 'Generate harness docs' run against a board file.")
    p.add_argument("board", help="path to a .kicad_pcb")
    p.add_argument("--numbering", choices=list(SCHEMES), default=None,
                   help="wire-numbering scheme (default: the spec file's"
                        " 'numbering:', else global)")
    p.add_argument("--renumber", action="store_true",
                   help="discard persisted wire numbers (store + review wire_no"
                        " column) and reassign everything with the chosen scheme")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    import pcbnew
    board = pcbnew.LoadBoard(args.board)
    res = generate_harness_docs(board, pcbnew_module=pcbnew,
                                scheme=args.numbering, renumber=args.renumber)
    print(f"{res.wire_count} wires -> {', '.join(res.outputs)}")
    for w in res.warnings:
        print("warning:", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
