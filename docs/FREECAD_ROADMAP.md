# FreeCAD integration roadmap

Status: **planned**, not started. This is the major expansion. It turns the wire-list
engine into an ECAD→MCAD digital thread: a 3D model of the harness that shares the same
connectivity, contributes the one thing 2D can't (true 3D **cut length**), and eventually
produces a flattened **formboard** drawing. Read `../CLAUDE.md` first.

## 0. Guiding principle

FreeCAD is a **third view on the same connectivity spine** — a sibling to the schematic
(logical) and the board (physical-2D) views. It does **not** own connectivity (that's the
netlist) and it does **not** own wire attributes (that's the spec file + engine). It owns
**3D geometry**: where connectors sit in space and how conductors route between them. From
that geometry it gives back two things the rest of the pipeline can't compute: true routed
lengths and, later, a formboard.

Do not try to make FreeCAD the source of truth for wiring. Wiring is always derived from
`netlist + placement`. This keeps the three views from ever disagreeing (see §3).

## 1. Existing substrate (this is integration, not greenfield)

- **KiCad StepUp** (official KiCad ext): already bridges KiCad↔FreeCAD — aligns 3D STEP
  models to footprints, pushes/pulls positions both directions, runs collision checks,
  exports STEP. This is the model-to-component tie mechanism to extend to harness connectors.
- **FreeCAD Cables Workbench** (alpha, FreeCAD ≥1.0): models cables as flexible 3D objects
  (WireFlex), cable profiles (wire count, diameters), materials, "attach wire to terminal",
  and custom connector/device libraries. This is the 3D-routing substrate to drive.
- **FreeCAD 1.0+ Assembly** + Python API: mature 3D CAD, scriptable (unlike KiCad's
  schematic side). `Part`/`Sketcher`/`Assembly`, and spline paths with `Shape.Length` for
  measured lengths.
- **WireViz** (already an emit target) auto-lays-out (no manual placement) — good for the
  topological diagram, wrong for a hand-placed formboard. **Splice CAD** (manual node editor,
  Python lib, multi-core cables) is the closest off-the-shelf alternative if we don't build
  our own formboard view.

## 2. How it plugs into the engine

Two new pieces, both respecting the existing seam:

1. **Ingest (optional):** connectivity still comes from KiCad. FreeCAD does not replace the
   ingest; it *consumes* the harness (which pins connect) to seed 3D routing.
2. **Enrich (new concept):** FreeCAD produces a small neutral artifact
   (`freecad_lengths.json`, later `harness_graph.json`) that the engine reads to fill/override
   geometry-derived fields. Add an enrich step in the engine that merges these by stable key.

Length precedence becomes: schematic (none) < board 2D track length < **FreeCAD 3D length**.
All three keyed identically (by net name / stable wire id), so the highest-fidelity source
that's present wins.

### Concrete: Phase-1 enrich adapter

Add `ingest/freecad_lengths.py` (or an `enrich/` module) exposing:

```python
class FreecadLengthSource:
    """Reads freecad_lengths.json and returns {net_name: length_mm}."""
    def load(self) -> dict[str, float]: ...
```

Engine change (small): after building wires, if a length map is provided, set
`wire.spec.length_mm` from it (override board length) keyed by `wire.net`. This is a handful
of lines and reuses the existing "fill/override" pattern.

`freecad_lengths.json` schema:

```json
{
  "version": 1,
  "unit": "mm",
  "lengths": { "/W5.L1": 812.4, "/W5.L2": 812.4, "/START": 240.0 },
  "generated_by": "freecad-harness-export 0.1"
}
```

That single file, produced by a FreeCAD-side macro/workbench script, delivers real cut
lengths through the entire existing pipeline with almost no engine change. **This is the MVP.**

## 3. The three data flows (the model that keeps views in sync)

1. **Connectivity** — from the netlist. Never positional, never changes when parts move.
   In 3D it appears as a "which pins must join" list = a 3D ratsnest.
2. **Placement** — one shared store keyed by stable component id; the 2D board view and the
   3D view are both *projections* of it. Give each degree of freedom **one owner** to avoid
   two-master conflicts: the 2D/panel view owns position-along-rail + which rail + in-plane
   rotation; the 3D view owns depth off the panel + out-of-plane orientation + the mounting
   plane. Because they edit disjoint DOF, edits in either propagate without contradiction.
3. **Wiring** — never stored as authored geometry; **regenerated** as a function of
   `netlist + placement`. Moving a part invalidates and recomputes routes on both views.
   The only thing persisted is a hand-tuned route, keyed by wire id and re-fit to moved
   endpoints (flag if endpoints moved beyond a tolerance).

`placement.json` schema (stable-id keyed, survives netlist changes):

```json
{
  "version": 1,
  "components": {
    "J5": { "rail": "DIN1", "pos_along_rail_mm": 120.0, "rot_deg": 0,
            "z_mm": 0.0, "orientation": [0,0,0], "model": "conn_3pos.step" }
  }
}
```

Sync = keyed regeneration, not overwrite: on re-export, diff by id — surviving ids keep
their placement, new nets/parts appear unplaced (fresh ratsnest), removed ones drop.

## 4. Connector-model library (the real work)

The hard, unglamorous prerequisite: each schematic connector `ref` needs an associated 3D
model **with defined pin/cavity exit points** (position + direction each conductor leaves the
connector). This is the MCAD analog of footprint libraries and is what makes routing and
length meaningful. Plan:

- A mapping `connector_models.yaml`: `ref` or footprint/value -> STEP model + per-pin exit
  frames. Extend the StepUp footprint→STEP idea to carry pin exit data.
- Start with a handful of hand-authored connectors (the ones in the test harness), grow as
  needed. Do not block Phase 1 on a complete library — a connector can start as a labeled
  point with pin exit vectors.

## 5. Harness graph (Phase 2 — formboard)

Once conductors route in 3D, extract a graph and flatten it to a 1:1 nailboard drawing.

`harness_graph.json` schema:

```json
{
  "version": 1,
  "unit": "mm",
  "nodes": [
    { "id": "J5", "kind": "connector", "ref": "J5" },
    { "id": "BR1", "kind": "branch" },
    { "id": "SP1", "kind": "splice" }
  ],
  "edges": [
    { "id": "seg1", "from": "J5", "to": "BR1", "length_mm": 300.0,
      "wires": ["/W5.L1", "/W5.L2", "/W5.L3"] },
    { "id": "seg2", "from": "BR1", "to": "J6", "length_mm": 512.4,
      "wires": ["/W5.L1"] }
  ]
}
```

Notes for the implementer:
- Nodes = connectors + branch points + splices; **every node needs a stable id** (connector
  refs are naturally stable; branch/splice ids must be assigned and persisted in the FreeCAD
  model so the flatten diff doesn't churn).
- Edge `length_mm` comes from `Shape.Length` on the 3D route edge — this is the same number
  that feeds `freecad_lengths.json` (a harness_graph supersedes the flat lengths file).
- **Flatten** = walk the tree from a root connector, lay each segment as a 2D edge whose
  **length equals the 3D segment length** (length-preserving is the whole point), choose
  branch angles for readability (not true 3D angles), annotate with wire/cable data the
  engine already owns, render SVG/DXF (DXF for the physical nail-board).
- Add a `emit/formboard_svg.py` (and/or DXF) that consumes `Harness` + `harness_graph.json`.
- One-way: 3D authoritative for geometry; formboard is generated. Persist 2D readability
  tweaks (branch splay, label offsets) keyed by node/edge id; do not push them back to 3D.

## 6. Validation (Phase 3)

With 3D present: bend-radius checks against wire spec, clash/interference (StepUp collision),
connector mating/backshell fit, bundle diameter from summed core cross-sections, heatshrink
length from branch geometry. These become additional DRC-style reports off the graph.

## 7. Interfaces to define up front (so the engine stays ready)

Even before FreeCAD work starts, these are cheap to add and de-risk the integration:
- `FreecadLengthSource` + engine enrich hook (Phase 1) — small, do this first.
- `harness_graph.json` / `placement.json` schemas frozen as above (versioned).
- A stable-id contract: the sorted endpoint pair `ref:pin<->ref:pin` for wires (net names
  proved unstable — the plugin itself renames nets, orphaning anything keyed by them);
  `ref` for connectors; assigned+persisted ids for branches/splices. Everything that
  crosses a tool boundary is keyed by these.

## 8. Open questions / hard parts (be honest with the user)

- Connector-model library maintenance is the main ongoing cost.
- A *pretty* formboard auto-layout (no overlaps, sensible angles) is genuinely hard — the
  expensive part of commercial tools. Length-preserving tree-walk is the tractable MVP.
- ECAD↔MCAD "always in sync" between two running apps is fragile; the robust version is one
  shared placement store + cheap regeneration on save/focus, not a live umbilical. If the 2D
  panel view can live *inside* FreeCAD (TechDraw projection / driving sketch), sync becomes
  free by construction — consider that instead of a KiCad-hosted 2D panel.
- Cables Workbench is alpha; its reroute-on-move isn't perfect.
- Robust splice/branch detection from arbitrary 3D routes needs conventions (mark splices
  explicitly, or merge routes within a tolerance).

## 9. Suggested first PR

1. Freeze `freecad_lengths.json` schema (§2).
2. Add `FreecadLengthSource` + the engine enrich hook + a test that overrides board length
   from a lengths file (construct `Connectivity`, no FreeCAD needed to test the merge).
3. Write a minimal FreeCAD macro that, given routed spline objects tagged by net name, dumps
   `freecad_lengths.json` via `Shape.Length`. Verify against one real routed cable.

That delivers true 3D cut lengths through the existing CSV/WireViz with minimal new surface,
and establishes the keyed-enrich pattern everything else builds on.
