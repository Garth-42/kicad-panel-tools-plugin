# Exporting the wire list and diagram

## From the PCB editor (board route)

With the plugin [installed](installation.md) and your board open, the intended
loop is **number first, export second**:

**1. Tools → External Plugins → Generate wire numbers**

An interactive dialog opens *before anything is generated or written*: a
numbering-scheme dropdown, a table of every wire with its proposed number, and
a **Generate** button. Pick a scheme and Generate to renumber, type directly
into `wire_no`/`notes` cells to override (typed numbers stay pinned through
further Generate rounds; clear a cell to unpin it), and repeat until the
numbers are right. Nothing touches the board or any file until you click
**Apply & Finish**, which writes `wire_numbers.json` + the review CSV and
renames the board nets to the approved numbers. **Cancel** discards the whole
session.

To see the applied numbers on the board itself, enable
**Preferences → PCB Editor → Display Options → Net Names → Show on tracks and
pads** — every routed track and pad then shows its wire number on the canvas.
(A multi-endpoint net like GND expands into several wires with different
numbers, so that net keeps its name; those numbers live in the table and the
exports only.)

**2. Tools → External Plugins → Generate harness docs**

A dialog reports the wire count, output paths, and any warnings. Next to your
`.kicad_pcb` you get:

| File | What it is |
|---|---|
| `<board>_wirelist.csv` | the point-to-point wire list (see columns below) |
| `<board>_wire_review.csv` | editable review table — edit `wire_no` / `notes`, save, regenerate |
| `<board>_harness.yaml` | WireViz input — render it into a diagram + BOM |
| `<board>_panel.svg`    | panel wiring diagram — see [Drawing the panel](panel-layout.md) |
| `wire_numbers.json`    | the wire-number store — **commit it with your design** |

The plugin auto-loads `harness_specs.yaml` if it sits next to the board.
Running the export without numbering first also works — numbers are then
assigned by the spec file's `numbering:` scheme on the fly.

## From the command line (netlist route)

```
kicad-cli sch export netlist --format kicadxml -o design.net.xml design.kicad_sch
python -m harness design.net.xml --specs harness_specs.yaml \
    --csv design_wirelist.csv --wireviz design_harness.yaml
```

Useful flags: `--numbering global|cable|net|srcdst|group` (overrides the spec
file's choice; without it the spec file's `numbering:` is used),
`--renumber` (discard persisted numbers and reassign from scratch — see below),
`--numbers PATH` (relocate the wire-number store), `--review PATH` (load and
rewrite an editable review CSV), `--no-persist` (don't read/write the JSON
store), `--no-autonumber`.

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


## Editable wire review table

The board plugin also writes `<board>_wire_review.csv`. The **Generate wire
numbers** dialog edits the same table interactively, so the CSV is mostly for
spreadsheet users and version control. In pcbnew, the export result dialog has
**Open Review CSV** and **Open Folder** buttons.

Typical loop:

1. Run **Tools → External Plugins → Generate harness docs**.
2. Open `<board>_wire_review.csv`.
3. Edit `wire_no` and `notes` as needed.
4. Save the CSV.
5. Run the plugin again; matching rows are applied by the stable `key` column and
   the review CSV is rewritten with current endpoints, nets, classes and lengths.

The generated `key` column is the same stable identity used for
`wire_numbers.json`: the wire's two endpoints, sorted — `ref:pin<->ref:pin`,
e.g. `J5:3<->X1:1`. A wire *is* its two endpoints, so the key survives net
renames (applying wire numbers to net names) and schematic re-syncs — keys in
older files used net names and are still matched, then migrated on the next
rewrite. Keep the `key` column intact. Endpoint, net, netclass and length
columns are refreshed from the board on each run; editable columns such as
`wire_no` and `notes` are preserved for keys that still exist. Stale keys are
reported as warnings so you can decide whether to remove old rows.

## Rendering the WireViz diagram

**Generate harness docs** always emits the WireViz YAML and rendered docs. A
PCM-only install writes SVG, HTML, and BOM outputs via the bundled renderer. If
Graphviz `dot` is available, the plugin also writes PNG output and can use the
upstream `wireviz` renderer when it is available. The CLI route can do the same
with `--render-wireviz`:

```
python -m harness design.net.xml --wireviz design_harness.yaml --render-wireviz
```

This produces `design_harness.png`, `.svg`, `.html` (a shareable page with
the diagram and BOM), and `.bom.tsv`. Connector types come from component
values; `MPN`/`Manufacturer` footprint fields feed the BOM; cable blocks show
wire count, gauge, per-core colors, wire labels, and the measured length.

![Rendered example](assets/example_harness.png)

## Wire numbers that don't change under you

Wire numbers are assigned by the scheme you pick (`numbering:` in the spec
file, or `--numbering`), can be adjusted in the editable review CSV, and are
then **persisted** in `wire_numbers.json` next to the board/netlist. On every
re-export:

- existing wires keep their numbers, no matter how the design was reordered;
- new wires get fresh numbers that never collide with existing ones;
- a wire that disappears keeps its entry, so it gets the same number back if
  it returns.

Explicit numbers (`nets: {"/START": {wire_no: "201"}}`) and intrinsic cable
labels (`W5-L1`) always win over the store. For normal manual changes, prefer
editing `<board>_wire_review.csv`; the plugin applies those numbers and then
updates `wire_numbers.json`. Commit `wire_numbers.json` to version control —
it's what makes the numbers on your printed labels stay true across revisions.

## Trying out a different numbering rule

The persistence above deliberately means that changing the numbering scheme
does **nothing** by itself — existing numbers always win. The place to iterate
on the rule is the **Generate wire numbers** dialog:

1. Run **Tools → External Plugins → Generate wire numbers**.
2. Pick a scheme from the **Numbering scheme** dropdown and click **Generate**;
   the table renumbers from scratch with that scheme. Repeat with other schemes
   until the numbers look right — nothing is written between rounds, and
   numbers you typed by hand stay pinned.
3. Click **Apply & Finish** to commit (or **Cancel** to walk away untouched).
4. Put the winning scheme in the spec file (`numbering: <scheme>`) — a picked
   scheme applies to that session only, and the warnings pane reminds you.

The CLI equivalent is `--numbering <scheme> --renumber`.

Committing a renumber rewrites `wire_numbers.json` from scratch (including
dropping entries for wires currently absent from the design) and replaces the
review table's `wire_no` column; other review edits — `notes`, gauge/color
overrides, custom columns — survive. Explicit `nets:` numbers and intrinsic
cable-core labels are unaffected. Do this tuning **before** printing labels:
after a renumber, anything already printed no longer matches.
