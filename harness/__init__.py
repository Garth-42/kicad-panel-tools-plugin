"""KiCad-agnostic wire-harness documentation engine.

Layers (dependencies point downward only):

    cli  ->  emit/*        (outputs: CSV wire list, WireViz YAML)
         ->  engine        (assembles the Harness model)
         ->  specs         (per-net harness metadata: gauge/color/length/cable/no)
         ->  ingest/*      (connectivity source: netlist today, IPC later)
         ->  model         (pure data classes; no I/O, no KiCad knowledge)

The `ingest` package is the swap point. `KicadNetlistSource` works on today's
KiCad 9/10 (via `kicad-cli sch export netlist` or an eeschema BOM/netlist export).
`KicadIpcSource` is a stub for when the schematic IPC API ships; the engine and
everything above it never change.
"""
__version__ = "0.1.0"
