# harness_engine

Generate wire-harness manufacturing docs (point-to-point wire list + WireViz diagram/BOM)
from a KiCad design. The schematic/board stays the single source of truth; the docs are
generated, never hand-maintained.

## Docs

- **`CLAUDE.md`** — architecture, conventions, testing, and the tested-vs-unverified matrix.
  Start here (also the Claude Code context file).
- **`docs/SPEC_SCHEMA.md`** — full `harness_specs.yaml` reference.
- **`docs/FREECAD_ROADMAP.md`** — the planned 3D / cut-length / formboard expansion.
- **`kicad_plugin/README.md`** — installing and using the pcbnew plugin.

## Two ways to run

**Board route** (pcbnew Action Plugin) — needs footprints; the only route that yields real
cut lengths. Copy `kicad_plugin/` and `harness/` into your KiCad plugin directory
(Tools → External Plugins → Open Plugin Directory), Refresh, then
Tools → External Plugins → **Generate harness docs**. Outputs land next to the board.

**Netlist route** (CLI) — no footprints needed; everything except length:

```
kicad-cli sch export netlist --format kicadxml -o design.net.xml design.kicad_sch
python -m harness design.net.xml --specs harness_specs.yaml --numbering group --wireviz out.yaml
```

Headless board run (KiCad's Python, from the repo root):

```
<kicad-python> -m kicad_plugin path/to/board.kicad_pcb
```

## Install

```
pip install -r requirements.txt        # just PyYAML
```
(The CSV path works without PyYAML; WireViz + spec-file loading need it. KiCad's bundled
Python often lacks it — YAML imports are lazy so the CSV still runs.)

## Tests

```
for t in tests/test_*.py; do python3 "$t"; done
```

## Quick mental model

`ingest/ (KiCad) -> engine (Connectivity + harness_specs.yaml) -> emit (CSV / WireViz)`.
Wire type comes from KiCad **net classes**; multi-conductor cables from **named group buses**
(`W5{L1 L2 L3}` -> nets `W5.L1…`); cut length from **routed track length**. See `CLAUDE.md`.
