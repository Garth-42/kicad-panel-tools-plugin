# Harness docs — KiCad pcbnew Action Plugin

Adds **Tools → External Plugins → Generate harness docs** to the PCB editor.
It reads the open board, extracts connectivity and **routed track lengths**, and
writes `<board>_wirelist.csv` (and `<board>_harness.yaml` for WireViz) next to
the board file.

## Install (cross-platform, no symlinks needed)

1. In pcbnew: **Tools → External Plugins → Open Plugin Directory**. That opens the
   exact folder KiCad scans (paths differ per OS/version; let KiCad tell you).
2. Copy **both** folders — `kicad_plugin/` and `harness/` — from this repo into
   that directory, side by side. (The plugin imports `harness` as a sibling.)
3. Back in pcbnew: **Tools → External Plugins → Refresh**. The command appears.

Dev alternative: keep the repo wherever you like and symlink just `kicad_plugin`
into the plugin directory — the plugin resolves the repo root via realpath, so
`harness` is still importable.

## PyYAML note

The **CSV always works** — it needs no third-party packages. Reading a
`harness_specs.yaml` and emitting **WireViz YAML** need PyYAML in *KiCad's* Python.
Check in the scripting console with `import yaml`; if it's missing you can install
it into KiCad's interpreter, or just use the CSV (net-class → wire-type mapping
then lives in the CSV post-step instead).

## Workflow

1. **Schematic:** draw it, and assign each wire's net a **net class named for its
   wire type** (e.g. `14AWG_BN`). Assign footprints (connectors are natural).
   **Update PCB from Schematic** (F8).
2. **PCB:** place footprints and **route tracks between the connected pads at real
   scale** — the routed length becomes the wire cut length.
3. *(optional)* Drop a `harness_specs.yaml` next to the board mapping net classes
   to gauge/color/cable (see `examples/classes.specs.yaml`).
4. **Tools → External Plugins → Generate harness docs.** A dialog reports the wire
   count and output paths.

## Headless test (KiCad's Python)

    <kicad-python> -m kicad_plugin path/to/board.kicad_pcb

Run from the repo root so `kicad_plugin` and `harness` are both importable.
`<kicad-python>` is the interpreter that can `import pcbnew` (bundled with KiCad).
