# harness_specs.yaml — schema reference

The spec file supplies harness metadata that KiCad can't hold on a wire. It lives next to
the `.kicad_pcb` (the plugin auto-loads that exact filename) or is passed with `--specs`.
Loading needs PyYAML; without it the CSV still generates from board/defaults only.

## Top-level keys

```yaml
numbering: group          # global | cable | net | srcdst | group   (default: global)
cable_delimiter: "."      # separator in group-bus net names "W5.L1"  (default: ".")
defaults: { ... }         # applied to every wire
classes: { ... }          # keyed by KiCad NET CLASS name  -> wire type
cables:  { ... }          # keyed by CABLE id (declares multi-conductor cables)
nets:    { ... }          # keyed by KiCad NET name -> per-net override (highest precedence)
```

## Recognized wire fields

`cable`, `wire_no`, `gauge`, `color`, `length_mm`, `prefix`, `conductor`.
**Any other key passes through as an extra CSV column** (e.g. `insulation`, `voltage`,
`shield`, `jacket`).

## Precedence (low → high)

1. `defaults`
2. `classes` (matched net class; composite `"X,Default"` is split, `Default` dropped)
3. board values — net-class **color swatch**, **track width**→gauge, **routed length** (fill-empty only)
4. `cables.<id>` cable-level fields (fill-empty)
5. `cables.<id>.cores.<coreId>` per-conductor (override)
6. `nets.<netName>` per-net override

"Fill-empty" means a value only applies if nothing more specific already set it, so anything
you type explicitly wins over anything derived.

## Numbering schemes (`numbering:`)

- `global` — `1, 2, 3` (optional width/prefix in code)
- `cable`  — `W1-001, W2-001` (per-cable count)
- `net`    — one shared number per net/potential (IEC equipotential)
- `srcdst` — `X1:1--M1:U` (from endpoints)
- `group`  — count within `prefix` (falls back to `cable`): all `prefix: M` wires → `M-001, M-002…`

Explicit `wire_no` (in `nets:`) always wins. Cabled conductors get an intrinsic
`wire_no = <cable>-<core>` (e.g. `W5-L1`) and are skipped by the scheme.

## classes: — wire type from net class

```yaml
classes:
  "14AWG_BN": { cable: W1, gauge: "14 AWG", color: BN, prefix: C }
  "16AWG_MOTOR": { cable: WM, prefix: M }   # leave gauge/color out -> take from board
```
Keys must match KiCad net class names exactly. Leaving `gauge`/`color` unset lets the board's
net-class track width / color swatch fill them.

## cables: — multi-conductor cables

A net named `<CABLE>.<core>` (from a KiCad **named group bus**, e.g. `W5{L1 L2 L3}`) is
treated as a cable core **only if `<CABLE>` is declared here** (opt-in; prevents `3.3V` being
read as cable `3`).

```yaml
cables:
  W5:
    gauge: "1.5 mm2"     # one gauge for the whole cable (fills each core)
    shield: "yes"        # cable-level fact -> extra column on every core
    jacket: "PVC"
    conductors: 4        # optional integer count -> extra column (spares etc.)
    cores:               # per-conductor detail, keyed by core id (after the dot)
      L1: { color: BN }
      L2: { color: BK }
      L3: { color: GY }
      PE: { color: GNYE }
```
- `cores` (map) = per-conductor overrides. `conductors` (scalar) = a declared count column.
- Label the actual wires `W5.L1` etc. in the schematic — the **bus line is cosmetic**; the
  wire labels name the nets.

## nets: — per-net override

```yaml
nets:
  "/START": { wire_no: "201", insulation: "PTFE" }   # highest precedence; 'insulation' -> extra column
```
Use for standalone wires. For cabled conductors, prefer `cables.<W>.cores.<id>`.

## Minimal working example

See `examples/classes.specs.yaml`.
