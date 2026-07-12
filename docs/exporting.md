# Exporting the wire list and diagram

## From the PCB editor (board route)

With the plugin [installed](installation.md) and your board open:

**Tools → External Plugins → Generate harness docs**

A dialog reports the wire count, output paths, and any warnings. Next to your
`.kicad_pcb` you get:

| File | What it is |
|---|---|
| `<board>_wirelist.csv` | the point-to-point wire list (see columns below) |
| `<board>_harness.yaml` | WireViz input — render it into a diagram + BOM |
| `<board>_panel.svg`    | panel wiring diagram — see [Drawing the panel](panel-layout.md) |
| `wire_numbers.json`    | the wire-number store — **commit it with your design** |

The plugin auto-loads `harness_specs.yaml` if it sits next to the board.

## From the command line (netlist route)

```
kicad-cli sch export netlist --format kicadxml -o design.net.xml design.kicad_sch
python -m harness design.net.xml --specs harness_specs.yaml \
    --csv design_wirelist.csv --wireviz design_harness.yaml
```

Useful flags: `--numbering global|cable|net|srcdst|group` (overrides the spec
file's choice), `--numbers PATH` (relocate the wire-number store),
`--no-persist` (don't read/write it), `--no-autonumber`.

There's also a headless board run, using KiCad's own Python:

```
<kicad-python> -m kicad_plugin path/to/board.kicad_pcb
```

## The CSV

One row per conductor, sorted by cable then wire number:

```
cable,conductor,wire_no,gauge,color,netclass,from_ref,from_pin,to_ref,to_pin,net,length_mm
W5,L1,W5-L1,1.5 mm2,BN,Default,J6,3,J5,3,/W5.L1,15.7
WM,,M-001,1.31 mm,,"16AWG_MOTOR,Default",J1,3,J2,3,Net-(J1-Pin_3),49.4
```

- `cable`/`conductor` — from a declared group-bus cable (`W5.L1`) or a
  `classes:` mapping.
- `gauge`/`color` — from the spec file, or derived from the net class's track
  width / color swatch when the YAML leaves them unset.
- `netclass` — the raw KiCad class membership, kept for debugging.
- `length_mm` — summed routed track length (board route, 2-endpoint nets).
- **Any extra key** you put in the spec file (`shield`, `jacket`,
  `insulation`, …) appears as an additional column.

## Rendering the WireViz diagram

On any machine with [WireViz](https://github.com/wireviz/WireViz) and
Graphviz installed:

```
wireviz design_harness.yaml
```

This produces `design_harness.png`, `.svg`, `.html` (a shareable page with
the diagram and BOM), and `.bom.tsv`. Connector types come from component
values; `MPN`/`Manufacturer` footprint fields feed the BOM; cable blocks show
wire count, gauge, per-core colors, wire labels, and the measured length.

![Rendered example](assets/example_harness.png)

## Wire numbers that don't change under you

Wire numbers are assigned by the scheme you pick (`numbering:` in the spec
file, or `--numbering`), and then **persisted** in `wire_numbers.json` next to
the board/netlist. On every re-export:

- existing wires keep their numbers, no matter how the design was reordered;
- new wires get fresh numbers that never collide with existing ones;
- a wire that disappears keeps its entry, so it gets the same number back if
  it returns.

Explicit numbers (`nets: {"/START": {wire_no: "201"}}`) and intrinsic cable
labels (`W5-L1`) always win over the store. Commit `wire_numbers.json` to
version control — it's what makes the numbers on your printed labels stay
true across revisions.
