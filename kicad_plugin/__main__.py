"""Standalone / headless runner, so you can test without clicking in the GUI:

    <kicad-python> -m kicad_plugin path/to/board.kicad_pcb

Use KiCad's bundled Python (the one that can `import pcbnew`). Run from the repo
root so `kicad_plugin` and `harness` are both importable.
"""
import sys
from .core import generate_harness_docs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m kicad_plugin <board.kicad_pcb>")
        return 2
    import pcbnew
    board = pcbnew.LoadBoard(argv[0])
    res = generate_harness_docs(board, pcbnew_module=pcbnew)
    print(f"{res.wire_count} wires -> {', '.join(res.outputs)}")
    for w in res.warnings:
        print("warning:", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
