# Setting up your KiCad project

KiCad has no field for "this wire is 14 AWG brown". The exporter therefore
reads harness data from things KiCad *does* have — and that means a few naming
conventions in your schematic. This page is the contract: follow it and the
docs generate themselves.

## 1. Connectors are just components

Draw every harness endpoint (connector, terminal block, device) as a symbol
with a reference designator (`J1`, `X1`, `-M1`, …) and give it a footprint.
Pin numbers/names on the symbol become the pin ids in the wire list
(`from_ref`/`from_pin` → `to_ref`/`to_pin`) and in the WireViz diagram.

**BOM data:** add custom fields to the symbol/footprint and they flow into the
WireViz auto-BOM. Recognized (case-insensitive):

- part number: `MPN`, `Manufacturer_Part_Number`, `Part_Number`, `PN`
- manufacturer: `Manufacturer`, `Mfr`, `Mfg`

Any *other* net-level data you need travels via the spec file instead (see
below).

## 2. Wire type = net class name

Create one net class per **wire type** you stock, named so you recognize it —
e.g. `14AWG_BN`, `16AWG_MOTOR`, `SHIELD_GN`. (**File → Schematic Setup →
Project → Net Classes**; assign nets to classes there by pattern, or from a
label's properties.)

Then map each class to real wire data in `harness_specs.yaml`:

```yaml
classes:
  "14AWG_BN":    { cable: W1, gauge: "14 AWG", color: BN, prefix: C }
  "16AWG_MOTOR": { cable: WM, prefix: M }   # gauge/color left out on purpose
```

Class names in the YAML must match the KiCad net-class names **exactly**.

**Let the board fill the gaps:** on the board route, if you leave `gauge` or
`color` out of a class entry, the exporter reads the net class's **track
width** (as mm) and **color swatch** from the board instead. Anything you type
in the YAML always wins over board-derived values.

> KiCad reports class membership as a composite like `"14AWG_BN,Default"` —
> that's normal, the exporter handles it (and ignores the implicit `Default`
> class entirely).

## 3. Multi-conductor cables = named group buses

To model a physical multi-core cable (one jacket, several conductors), use a
KiCad **named group bus**:

1. Draw a bus and label it `W5{L1 L2 L3 PE}` — cable `W5` with cores `L1`,
   `L2`, `L3`, `PE`.
2. Unfold members to your connector pins. The wires must carry labels
   `W5.L1`, `W5.L2`, … — **the wire labels are what name the nets; the bus
   line itself is cosmetic**. (This is the most common gotcha.)
3. Declare the cable in `harness_specs.yaml` — cables are **opt-in**, which is
   what keeps a power net like `3.3V` from being misread as cable "3":

```yaml
cables:
  W5:
    gauge: "1.5 mm2"      # one gauge for the whole cable
    shield: "yes"         # any extra key becomes a CSV column on every core
    jacket: "PVC"
    cores:                # per-conductor detail, keyed by core id
      L1: { color: BN }
      L2: { color: BK }
      L3: { color: GY }
      PE: { color: GNYE }
```

Each core arrives in the wire list with the shared cable id, its own
conductor id and color, and an intrinsic wire number `W5-L1`, `W5-L2`, …

## 4. Cut lengths = routed tracks (board route only)

Lay out the board as a 1:1 physical plan of your panel/harness: place the
connector footprints where the real parts sit and **route a track between the
connected pads at real scale**. The summed routed length of each net becomes
that wire's `length_mm` — the cut length.

- Unrouted nets simply get a blank length; everything else still works.
- A net with more than 2 endpoints (e.g. a shared ground) is expanded as a
  star and warned about; per-leg lengths stay blank, since the summed track
  length spans the whole net.

## 5. Per-net overrides and defaults

For one-off wires, override by net name (highest precedence); set global
fallbacks under `defaults` (lowest — it never masks anything):

```yaml
defaults:
  gauge: "20 AWG"
nets:
  "/START": { wire_no: "201", insulation: "PTFE" }
```

Full schema, precedence rules, and numbering schemes:
**[harness_specs.yaml reference](SPEC_SCHEMA.md)**.
