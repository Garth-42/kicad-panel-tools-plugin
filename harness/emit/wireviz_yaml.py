"""Emit WireViz YAML -> harness diagram + BOM.

Refinements over the v1 sketch:
  * connector `type` comes from the component value (not the designator), and the
    designator stays the YAML key, matching WireViz conventions;
  * `pins` lists the real pin identifiers (U, V, A1, ...), so named harness pins
    survive instead of being renumbered;
  * `colors` and `wirelabels` are emitted only when they cover every wire in the
    cable (WireViz requires their length to equal wirecount);
  * cable `length` + `length_unit: mm` are set when the routed lengths agree,
    surfacing the pcbnew-measured cut length in the diagram;
  * connector manufacturer/MPN fields feed WireViz's auto-BOM when available;
  * one connection set per wire -- robust when a cable's wires fan out to
    different connectors (WireViz connects index-wise within a set).

Pass `components` (ref -> Component) to enrich types and BOM; without it the
emitter still produces a valid diagram using designators as types.
"""
from __future__ import annotations
from ..model import Harness

# Component field names we'll look at for BOM enrichment (case-insensitive).
_MPN_KEYS = ("mpn", "manufacturer_part_number", "part_number", "pn")
_MFR_KEYS = ("manufacturer", "mfr", "mfg")


def _field(component, keys):
    if component is None:
        return ""
    lower = {k.lower(): v for k, v in (component.fields or {}).items()}
    for k in keys:
        if lower.get(k):
            return lower[k]
    return ""


def _pin_id(pin):
    """WireViz coerces numeric-looking connection pin refs to int (expand()),
    while connector `pins` entries stay as authored — emit numeric pins as int
    on BOTH sides so the lookup matches ('J1:1 not found' otherwise)."""
    p = str(pin)
    return int(p) if p.isdigit() else p


def build_wireviz(harness: Harness, components: dict | None = None) -> dict:
    components = components or {}

    # --- connectors: gather the real pins each designator uses ---------------
    pins_by_ref: dict[str, list] = {}
    for w in harness.wires:
        for node in (w.a, w.b):
            lst = pins_by_ref.setdefault(node.ref, [])
            if _pin_id(node.pin) not in lst:
                lst.append(_pin_id(node.pin))

    connectors: dict[str, dict] = {}
    for ref, pins in pins_by_ref.items():
        comp = components.get(ref)
        entry = {
            "type": (getattr(comp, "value", "") or ref),
            "pins": list(pins),
        }
        mpn, mfr = _field(comp, _MPN_KEYS), _field(comp, _MFR_KEYS)
        if mpn:
            entry["mpn"] = mpn
        if mfr:
            entry["manufacturer"] = mfr
        connectors[ref] = entry

    # --- cables + connections -------------------------------------------------
    cables: dict[str, dict] = {}
    connections: list = []
    for cable_name, wires in harness.cables().items():
        cname = cable_name if cable_name != "(loose)" else "W_loose"
        wirecount = len(wires)
        entry: dict = {"wirecount": wirecount}

        gauges = {w.spec.gauge for w in wires if w.spec.gauge}
        if len(gauges) == 1:
            entry["gauge"] = next(iter(gauges))

        colors = [w.spec.color for w in wires]
        if all(colors):                       # length must equal wirecount
            entry["colors"] = colors

        labels = [w.spec.wire_no for w in wires]
        if all(labels):
            entry["wirelabels"] = labels

        lengths = {w.spec.length_mm for w in wires if w.spec.length_mm}
        if len(lengths) == 1:                 # one length for the whole bundle
            try:
                entry["length"] = float(next(iter(lengths)))
                entry["length_unit"] = "mm"
            except ValueError:
                pass

        cables[cname] = entry

        for i, w in enumerate(wires, start=1):
            connections.append([
                {w.a.ref: [_pin_id(w.a.pin)]},
                {cname: [i]},
                {w.b.ref: [_pin_id(w.b.pin)]},
            ])

    return {"connectors": connectors, "cables": cables, "connections": connections}


def write_wireviz(harness: Harness, path: str, components: dict | None = None) -> None:
    from ..yamlio import import_yaml  # lazy; falls back to vendored copy
    yaml = import_yaml()
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(build_wireviz(harness, components), fh,
                       sort_keys=False, allow_unicode=True)
