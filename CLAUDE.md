# CLAUDE.md — harness_engine

Context for working on this project in Claude Code. Read this first.

## What this is

A KiCad-agnostic engine that turns an electrical design into **wire-harness
manufacturing documentation** (a point-to-point wire list, plus WireViz YAML for
a diagram + BOM). It grew out of frustration with QElectroTech; the design goal is
that the **schematic/board is the single source of truth** and the docs are
generated, never hand-maintained.

It runs two ways:
- **Board route** (richest): a pcbnew Action Plugin reads the open KiCad board.
  Only this route can produce real **cut lengths** (from routed track length).
- **Netlist route** (no footprints needed): a CLI parses an exported netlist.
  Everything except length.

## Architecture — one spine, swappable front ends

Dependencies point downward only. The whole design rests on a neutral data model
(`model.py`) that knows nothing about KiCad; everything else is an adapter.

```
cli.py / kicad_plugin/         front ends (invoke the pipeline)
  -> emit/           wirelist_csv.py, wireviz_yaml.py     (outputs)
  -> engine.py       build_harness(Connectivity, SpecStore) -> Harness
  -> specs.py        SpecStore: per-net/class/cable metadata + precedence
  -> ingest/         ConnectivitySource.load() -> Connectivity   <-- SWAP POINT
  -> model.py        pure dataclasses; no I/O, no KiCad knowledge
  -> numbering.py    wire-numbering strategies
  -> cables.py       parse "W5.L1" -> (cable, conductor)
```

**The ingest interface (`ingest/base.py: ConnectivitySource.load() -> Connectivity`)
is the extension seam.** Adding a new data source (or, later, FreeCAD) means adding
one adapter here and nothing above changes.

Current ingest adapters:
- `KicadNetlistSource` — parses `kicad-cli sch export netlist --format kicadxml`. Works today.
- `KicadBoardSource` — reads a live/loaded pcbnew board (footprints/pads/tracks/nets).
  Works today; the ONLY source of routed lengths.
- `KicadIpcSource` — **stub**. Placeholder for the schematic IPC API (not in KiCad 9/10).

## Data model (`model.py`)

- `Node(ref, pin, pinfunction)` — one pad/pin on a component.
- `Component(ref, value, fields)` — a placed part; `fields` = custom footprint fields.
- `Net(code, name, nodes, netclass, length_mm, color, track_width_mm)` — an electrical
  potential. `length_mm/color/track_width_mm` are only populated by the board adapter.
- `Connectivity(components, nets)` — everything an ingest source must provide.
- `WireSpec(cable, wire_no, gauge, color, length_mm, prefix, conductor, extra)` — resolved
  per-wire metadata. `extra` is an open dict for arbitrary passthrough fields.
- `Wire(net, a, b, spec, netclass)` — a point-to-point conductor.
- `Harness(wires)` — result; `.cables()` groups wires by cable name.

## KiCad conventions (how the design carries harness data)

KiCad has no place to type wire attributes onto a wire, so we encode them via things
KiCad *does* have:

| Harness concept        | KiCad mechanism                        | Read by |
|------------------------|----------------------------------------|---------|
| Wire type (gauge, color) | **net class NAME** -> `classes:` map | both routes |
| Wire color (optional)  | net class **color swatch**             | board route (unverified) |
| Wire diameter/gauge    | net class **track width**              | board route (unverified) |
| Cut length             | **routed track length**                | board route |
| Cable identity + core  | **named group bus** `W5{L1 L2 L3}` -> nets `W5.L1` | both routes |
| Connector part data    | **footprint custom fields**            | board route |

**Net class names come back composite**, e.g. `"16AWG_MOTOR,Default"` — KiCad lists all
memberships incl. the implicit `Default`. `SpecStore.resolve` splits on comma and drops
`Default`. (This was a real bug found via the `netclass` CSV column — keep that column.)

**Multi-conductor cables**: a net named `<CABLE>.<core>` (from a KiCad *named group bus*)
is treated as a cable core **only if `<CABLE>` is declared under `cables:`** — this opt-in
prevents power nets like `3.3V` being misread as cable `3`. A group bus `W5{L1 L2 L3}`
produces nets `W5.L1/W5.L2/W5.L3`; the wire *labels* are what name the nets (the bus line
itself is cosmetic — a common gotcha). Cores share the cable id, get distinct `conductor`
ids, per-core colors from `cables.<W>.cores.<id>`, and an intrinsic `wire_no` = `W5-L1`.

## Spec file (`harness_specs.yaml`)

Lives next to the `.kicad_pcb` (plugin auto-loads that exact filename). Full schema and
examples in `docs/SPEC_SCHEMA.md`; `examples/classes.specs.yaml` is a working sample.

Precedence, low to high: `defaults` < net `classes` < board values (color/width/length,
fill-empty only) < `cables` cable-level (fill-empty) < `cables.<W>.cores` per-core (override)
< `nets` per-net override. Numbering scheme via top-level `numbering:` (global | cable |
net | srcdst | group). `group` numbers within a `prefix` (falls back to `cable`).

## Testing

No real KiCad in CI. `tests/mock_pcbnew.py` is a faithful stand-in for the pcbnew API
surface the adapter touches; everything else is tested by constructing `Connectivity`
directly. Run all:

```
for t in tests/test_*.py; do python3 "$t"; done
```

Each test prints `OK ...` on success and asserts. Keep them dependency-light (stdlib +
PyYAML). When adding a feature, add/extend a test that builds a `Connectivity` and asserts
on the resulting CSV/harness.

## Tested vs. unverified (IMPORTANT before trusting board output)

Verified on the user's real KiCad (macOS, KiCad from `Python.framework/3.9`):
- footprint/pad/net -> Connectivity mapping
- net class composite string reading + `classes:` mapping
- group-bus cable naming `W5.L1` -> cable/conductor grouping, per-core colors
- CSV + WireViz files written; PyYAML present in that KiCad's Python

Tested only against mock/synthetic:
- engine precedence, all numbering schemes, WireViz structure, multi-conductor,
  extras/cable passthrough, plugin core, graceful no-PyYAML fallback

**UNVERIFIED on real hardware — the accessors to check first if board values are blank**
(all in `ingest/pcbnew_board.py`, written defensively with `_first(...)` fallbacks):
- net class **color**: `GetPcbColor()` / `GetSchematicColor()` -> COLOR4D -> hex
- net class **track width**: `GetTrackWidth()` (nm) -> mm
- **routed length**: `GetLength()` summed over tracks per net (needs tracks routed)

If a board value comes out empty, run pcbnew's Scripting Console and probe the net class
object methods, then fix the accessor name in `_netclass_color` / `_netclass_width_mm`.

## Known gaps / next work

- **Length** requires routed tracks; unrouted nets yield blank `length_mm`.
- `>2`-endpoint nets (e.g. shared GND) expand as a **star** from node[0] (warned). Revisit
  if daisy-chain/explicit routing is needed.
- WireViz emitter is solid on structure but not run through actual WireViz here.
- Wire numbers are reassigned each run; no persistence yet (see roadmap: stable-ID store).
- Plugin uses the numbering scheme from the spec file; no in-dialog picker.

## Roadmap

- **Wire-number persistence**: `wire_numbers.json` keyed by stable net id so `M-001` stays
  attached to the same physical wire across re-exports.
- **FreeCAD / 3D (major)**: see `docs/FREECAD_ROADMAP.md`. FreeCAD becomes a third view on
  the same connectivity spine, contributing true 3D routed lengths and, later, a flattened
  formboard. This is the main planned expansion — read that doc before starting it.

## Conventions for changes

- Keep `model.py` free of I/O and KiCad specifics.
- New data sources = new `ConnectivitySource` in `ingest/`; don't leak source specifics upward.
- Additive dataclass fields (defaults) to avoid breaking existing adapters.
- YAML imports stay **lazy** (KiCad's bundled Python often lacks PyYAML); the CSV path must
  work without it.
- Prefer "fill-empty" merges so explicit user values always win over derived/board ones.
